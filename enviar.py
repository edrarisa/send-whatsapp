"""Envio masivo de plantillas de WhatsApp desde un Excel.

    python enviar.py --dry-run
    python enviar.py --solo 57XXXXXXXXXX
    python enviar.py --limite 5
    python enviar.py
"""

import argparse
import json
import random
import sys
import time

import requests
from dotenv import dotenv_values

from src.config import ConfigInvalida, cargar_config
from src.contactos import leer_contactos
from src.marcado import ExcelBloqueado, marcar_excel
from src.registro import ENVIADO, FALLO, Registro
from src.whatsapp import (
    ImagenNoSubida,
    TokenInvalido,
    construir_payload,
    enviar_con_reintentos,
    referencia_imagen,
    subir_imagen,
)


def parsear_argumentos(argv=None):
    parser = argparse.ArgumentParser(description="Envio masivo de plantillas de WhatsApp.")
    parser.add_argument("--config", default="campana.json",
                        help="Archivo de campana (por defecto: campana.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra los payloads y NO envia nada")
    parser.add_argument("--limite", type=int, default=None,
                        help="Envia solo a los primeros N contactos")
    parser.add_argument("--solo", default=None,
                        help="Envia solo a este numero (formato 57XXXXXXXXXX)")
    parser.add_argument("--marcar", action="store_true",
                        help="Solo actualiza las columnas de estado del Excel, no envia")
    return parser.parse_args(argv)


def main(argv=None):
    args = parsear_argumentos(argv)

    try:
        entorno = {**dotenv_values(".env")}
        config = cargar_config(args.config, entorno)
    except ConfigInvalida as error:
        print(f"ERROR DE CONFIGURACION: {error}")
        return 1

    try:
        validos, descartes = leer_contactos(
            config.excel.ruta,
            hoja=config.excel.hoja,
            columna_nombre=config.excel.columna_nombre,
            columna_telefono=config.excel.columna_telefono,
            nombre_por_defecto=config.envio.nombre_por_defecto,
        )
    except (ValueError, OSError) as error:
        print(f"ERROR LEYENDO EL EXCEL: {error}")
        return 1

    print(f"Excel: {config.excel.ruta}")
    print(f"  {len(validos)} contactos validos, {len(descartes)} descartados")
    if descartes:
        print("  Motivos:", _contar_motivos(descartes))

    registro = Registro(config.envio.ruta_log)

    if args.marcar:
        return _marcar(config, registro)

    ya_enviados = registro.telefonos_enviados()

    pendientes = [c for c in validos if c.telefono not in ya_enviados]
    if ya_enviados:
        print(f"  {len(validos) - len(pendientes)} ya estaban enviados segun el log, se saltan")

    if args.solo:
        pendientes = [c for c in pendientes if c.telefono == args.solo]
        if not pendientes:
            print(f"El numero {args.solo} no esta en la lista de pendientes.")
            return 1

    if args.limite is not None:
        pendientes = pendientes[: args.limite]

    # El tope es sobre una ventana movil de 24h, no sobre esta corrida: si el
    # script ya se ejecuto hoy, lo que envio entonces sigue consumiendo cupo.
    if not args.dry_run:
        gastado = registro.enviados_ultimas_24h()
        cupo = config.envio.tope_diario - gastado
        if gastado:
            print(f"  Cupo 24h: {gastado} de {config.envio.tope_diario} ya usados, quedan {cupo}")
        if cupo <= 0:
            print(f"\nTope de {config.envio.tope_diario} mensajes / 24h alcanzado.")
            print("Vuelve a correrlo mas tarde y seguira con los que faltan.")
            return 0
        if len(pendientes) > cupo:
            print(f"  Se recortan {len(pendientes) - cupo} para la proxima corrida")
            pendientes = pendientes[:cupo]

    print(f"\nPlantilla: {config.plantilla.nombre} ({config.plantilla.idioma})")
    print(f"A enviar ahora: {len(pendientes)}")
    print(f"Ritmo: {config.envio.segundos_entre_mensajes}s entre mensajes\n")

    if not pendientes:
        print("Nada por enviar.")
        return 0

    if args.dry_run:
        return _simular(pendientes, config)

    return _enviar(pendientes, config, registro)


def _simular(pendientes, config):
    print("--- DRY RUN: no se envia nada ---\n")
    imagen = referencia_imagen(config.plantilla.imagen_cabecera)
    if config.plantilla.imagen_cabecera and imagen is None:
        imagen = {"id": "<se subiria a Meta al enviar de verdad>"}
    for contacto in pendientes:
        payload = construir_payload(contacto, config.plantilla, imagen=imagen)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print()
    print(f"Se habrian enviado {len(pendientes)} mensajes.")
    return 0


def _resolver_imagen(sesion, config):
    """Deja lista la referencia de la imagen de cabecera antes de empezar.

    Una URL se usa tal cual. Un archivo local se sube UNA vez y todos los
    mensajes reutilizan el ID, en vez de hacer que Meta lo descargue 800 veces.
    """
    valor = config.plantilla.imagen_cabecera
    if not valor:
        return None

    imagen = referencia_imagen(valor)
    if imagen:
        print(f"Imagen de cabecera: URL publica ({valor})")
        return imagen

    print(f"Subiendo la imagen de cabecera a Meta: {valor}")
    identificador = subir_imagen(sesion, config.meta, valor)
    print(f"  subida, ID de medio {identificador}")
    return {"id": identificador}


def _enviar(pendientes, config, registro):
    sesion = requests.Session()

    try:
        imagen = _resolver_imagen(sesion, config)
    except ImagenNoSubida as error:
        print(f"\nERROR CON LA IMAGEN: {error}")
        print("No se envio ningun mensaje.")
        return 1

    enviados = 0
    fallidos = 0
    total = len(pendientes)

    try:
        for indice, contacto in enumerate(pendientes, start=1):
            payload = construir_payload(contacto, config.plantilla, imagen=imagen)

            try:
                resultado = enviar_con_reintentos(sesion, config.meta, payload)
            except TokenInvalido as error:
                print(f"\nTOKEN RECHAZADO POR META: {error}")
                print("Se detiene todo. Hay que generar un token nuevo.")
                return 1

            if resultado.ok:
                enviados += 1
                registro.anotar(contacto.telefono, contacto.nombre, ENVIADO,
                                message_id=resultado.message_id)
                estado = f"OK   {resultado.message_id}"
            else:
                fallidos += 1
                registro.anotar(contacto.telefono, contacto.nombre, FALLO,
                                codigo_error=resultado.codigo,
                                mensaje_error=resultado.mensaje)
                estado = f"FALLO [{resultado.codigo}] {resultado.mensaje}"

            print(f"[{indice}/{total}] {contacto.telefono} {contacto.nombre:<15} {estado}")

            if indice < total:
                time.sleep(_pausa(config.envio))
    finally:
        registro.cerrar()

    print(f"\nEnviados: {enviados}   Fallidos: {fallidos}")
    print(f"Detalle completo en: {config.envio.ruta_log}")

    # El Excel se marca al final, nunca durante el envio: guardar un .xlsx
    # reescribe el archivo entero y un corte a medias lo dejaria corrupto.
    _marcar(config, registro)

    return 0 if fallidos == 0 else 2


def _marcar(config, registro):
    """Pinta el estado de cada contacto en el Excel. Nunca aborta la corrida."""
    try:
        marcadas = marcar_excel(
            config.excel.ruta,
            registro.resultados(),
            hoja=config.excel.hoja,
            columna_telefono=config.excel.columna_telefono,
        )
        print(f"Excel actualizado: {marcadas} filas marcadas en {config.excel.ruta}")
        print(f"  (copia de seguridad en {config.excel.ruta}.bak)")
        return 0
    except ExcelBloqueado as error:
        print(f"\nAVISO: {error}")
        return 3
    except (ValueError, OSError) as error:
        print(f"\nAVISO: no pude marcar el Excel: {error}")
        print(f"Los envios estan guardados en {config.envio.ruta_log}, no se perdio nada.")
        return 3


def _pausa(envio):
    """Espera con variacion aleatoria, para no verse como un robot exacto."""
    variacion = envio.segundos_entre_mensajes * envio.jitter
    return max(0.0, envio.segundos_entre_mensajes + random.uniform(-variacion, variacion))


def _contar_motivos(descartes):
    conteo = {}
    for descarte in descartes:
        conteo[descarte.motivo] = conteo.get(descarte.motivo, 0) + 1
    return conteo


if __name__ == "__main__":
    sys.exit(main())
