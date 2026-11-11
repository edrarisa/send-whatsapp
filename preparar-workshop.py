#!/usr/bin/env python3
"""Deja el servidor listo para la campana del Workshop DAMA Week (20 nov 2026).

Se corre UNA vez, dentro del contenedor `enviador`, despues de que haya
terminado el envio anterior:

    python preparar-workshop.py

Comprueba que Meta ya aprobo la plantilla, aparta el log de la campana
anterior y apunta campana.json a la plantilla e imagen del workshop. Se niega a
actuar si hay un envio en marcha o si la plantilla no esta aprobada: en ese
caso no toca nada.
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone

import requests

from src.config import ConfigInvalida, cargar_config, leer_entorno

DATOS = os.environ.get("DATOS_DIR", "/datos")
CAMPANA = os.path.join(DATOS, "campana.json")
LOG_VIGENTE = os.path.join(DATOS, "logs", "envios.csv")
ORDENES = os.path.join(DATOS, "ordenes")

PLANTILLA = "dama_week_internacional_2026_v2"   # "Hola {{1}}." + el texto del workshop
IDIOMA = "es"
SALUDO_POR_DEFECTO = "colega"   # para quien no trae un nombre usable en el Excel
# Viaja dentro de la imagen Docker, junto a este script: /app/workshop-dama.png
IMAGEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workshop-dama.png")
RITMO = 5
TOPE = 1100
CONTACTOS_ESPERADOS = 1072


def abortar(mensaje):
    print(f"\nABORTADO: {mensaje}")
    print("No se cambio nada.")
    sys.exit(1)


def graph(entorno, ruta, **params):
    version = (entorno.get("GRAPH_API_VERSION") or "v21.0").strip()
    respuesta = requests.get(
        f"https://graph.facebook.com/{version}/{ruta}",
        params=params,
        headers={"Authorization": f"Bearer {entorno.get('WHATSAPP_TOKEN', '').strip()}"},
        timeout=30,
    )
    if respuesta.status_code != 200:
        abortar(f"Meta respondio {respuesta.status_code} al consultar {ruta}: {respuesta.text[:300]}")
    return respuesta.json()


print("=== PREPARANDO LA CAMPANA DEL WORKSHOP ===\n")

# 1. Que no haya nada corriendo.
if os.path.exists(os.path.join(ORDENES, "en_curso.json")):
    abortar("hay un envio en marcha. Espera a que termine y vuelve a correrlo.")
if os.path.exists(os.path.join(ORDENES, "solicitud.json")):
    abortar("hay un envio solicitado sin arrancar. Espera a que termine.")

# 2. La imagen tiene que existir: si no, falta el Redeploy.
if not os.path.exists(IMAGEN):
    abortar(f"no encuentro {IMAGEN}. Falta hacer el Redeploy en Coolify.")
print(f"[1/4] Imagen encontrada: {IMAGEN} ({os.path.getsize(IMAGEN):,} bytes)")

# 3. La plantilla tiene que estar aprobada. Mientras este en revision, Meta
#    rechaza cada mensaje: mejor enterarse aqui que con 1072 errores en el log.
entorno = leer_entorno()
waba = (entorno.get("WHATSAPP_WABA_ID") or "").strip()
if not waba:
    abortar("falta la variable WHATSAPP_WABA_ID; sin ella no puedo comprobar la plantilla.")

encontradas = [
    p for p in graph(entorno, f"{waba}/message_templates",
                     name=PLANTILLA, fields="name,status,language")["data"]
    if p.get("name") == PLANTILLA and p.get("language") == IDIOMA
]
if not encontradas:
    abortar(f"Meta no tiene la plantilla '{PLANTILLA}' ({IDIOMA}) en la cuenta {waba}.")
estado = encontradas[0].get("status")
if estado != "APPROVED":
    abortar(f"la plantilla '{PLANTILLA}' esta en estado {estado}. Hay que esperar a que diga APPROVED.")

remitente = graph(entorno, (entorno.get("WHATSAPP_PHONE_NUMBER_ID") or "").strip(),
                  fields="display_phone_number,verified_name")
print(f"[2/4] Plantilla {PLANTILLA} APROBADA")
print(f"        remitente: {remitente.get('display_phone_number')} "
      f"({remitente.get('verified_name')})")

# 4. Apartar el log anterior con la fecha, para no pisar ninguno.
if os.path.exists(LOG_VIGENTE):
    sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    destino = os.path.join(DATOS, "logs", f"envios-{sello}.csv")
    shutil.move(LOG_VIGENTE, destino)
    print(f"[3/4] Log anterior guardado en {destino}")
else:
    print("[3/4] No habia log vigente; se creara uno nuevo")

# 5. Apuntar la configuracion.
with open(CAMPANA, encoding="utf-8") as archivo:
    config = json.load(archivo)

config["_nota"] = "CAMPANA ACTIVA: Workshop DAMA Week Internacional, 20 de noviembre de 2026."
config["plantilla"]["nombre"] = PLANTILLA
config["plantilla"]["idioma"] = IDIOMA
# {{1}} es el primer nombre de la columna Nombre. La plantilla tiene una sola
# variable: mandar mas o menos parametros hace que Meta rechace el mensaje.
config["plantilla"]["parametros_cuerpo"] = [{"origen": "nombre_normalizado"}]
config["envio"]["nombre_por_defecto"] = SALUDO_POR_DEFECTO
config["plantilla"]["imagen_cabecera"] = IMAGEN
config["plantilla"]["parametro_boton_url"] = None
config["envio"]["segundos_entre_mensajes"] = RITMO
config["envio"]["tope_diario"] = TOPE
# El mismo log que se acaba de apartar y el que lee el panel (PANEL_LOG).
config["envio"]["ruta_log"] = LOG_VIGENTE

with open(CAMPANA, "w", encoding="utf-8") as archivo:
    json.dump(config, archivo, ensure_ascii=False, indent=2)

try:
    final = cargar_config(CAMPANA, entorno)
except ConfigInvalida as error:
    print(f"\nATENCION: campana.json quedo escrito pero no valida: {error}")
    sys.exit(1)

print("[4/4] Configuracion actualizada:")
print(f"        plantilla : {final.plantilla.nombre} ({final.plantilla.idioma})")
print(f"        variables : {len(final.plantilla.parametros_cuerpo)} (primer nombre; si falta: '{final.envio.nombre_por_defecto}')")
print(f"        imagen    : {final.plantilla.imagen_cabecera}")
print(f"        ritmo     : {final.envio.segundos_entre_mensajes} s")
print(f"        tope      : {final.envio.tope_diario}")

print("\nLISTO. Ahora:")
print(f"  1. Desde el panel, sube workshop-listo.xlsx -> debe decir {CONTACTOS_ESPERADOS} validos, 0 descartados")
print("  2. Prueba con UN numero que este en esa lista (--solo no envia a numeros de fuera):")
print("       python enviar.py --config /datos/campana.json --solo 57XXXXXXXXXX")
print("     Mira en el celular como se ve la imagen antes de seguir.")
print("  3. En el panel, escribe el numero de pendientes y lanza")
