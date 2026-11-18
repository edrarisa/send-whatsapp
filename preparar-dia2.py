#!/usr/bin/env python3
"""Deja el servidor listo para la campana "Transmision virtual del dia 2 -
DAMA Week Internacional 2026" (se envia la manana del 19 de noviembre).

Se corre UNA vez, dentro del contenedor `enviador`, despues de que haya
terminado el envio anterior:

    python preparar-dia2.py

Comprueba que Meta ya aprobo la plantilla, aparta el log de la campana
anterior y apunta campana.json a la plantilla e imagen de esta campana. Se
niega a actuar si hay un envio en marcha, si la plantilla no esta aprobada o si
la campana ya estaba preparada: en esos casos no toca nada.
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone

import requests

from src.config import ConfigInvalida, cargar_config, leer_entorno
from src.registro import Registro

DATOS = os.environ.get("DATOS_DIR", "/datos")
CAMPANA = os.path.join(DATOS, "campana.json")
LOG_VIGENTE = os.path.join(DATOS, "logs", "envios.csv")
ORDENES = os.path.join(DATOS, "ordenes")

# v2: misma plantilla con "continúa" corregido (la v1 no se podia editar dos veces en 24 h)
PLANTILLA = "transmisin_virtual_da_2_dama_week_internacional_2026_v2"   # "Hola {{1}}" + link a YouTube
IDIOMA = "es"
SALUDO_POR_DEFECTO = "colega"   # para quien no trae un nombre usable en el Excel
# Viaja dentro de la imagen Docker, junto a este script: /app/dama-week-dia2.png
IMAGEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dama-week-dia2.png")
RITMO = 5
TOPE = 1200   # la lista tiene 1152: con 1100 el envio se cortaria antes de terminar
LISTA = "lista-dia2-19-11-2026.xlsx"
CONTACTOS_ESPERADOS = 1152
PRUEBA = "prueba-dia2.xlsx"
PENDIENTES_TRAS_PRUEBA = 1150   # Eduar y Gustavo estan en la prueba y en la lista


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


print("=== PREPARANDO LA CAMPANA: TRANSMISION DEL DIA 2 ===\n")

# 1. Que no haya nada corriendo.
if os.path.exists(os.path.join(ORDENES, "en_curso.json")):
    abortar("hay un envio en marcha. Espera a que termine y vuelve a correrlo.")
if os.path.exists(os.path.join(ORDENES, "solicitud.json")):
    abortar("hay un envio solicitado sin arrancar. Espera a que termine.")

with open(CAMPANA, encoding="utf-8") as archivo:
    config = json.load(archivo)

# 2. Que no se haya preparado ya. Correrlo dos veces apartaria el registro de
#    esta misma campana, y quien ya recibio (la prueba, por ejemplo) volveria a
#    recibir en la siguiente corrida.
if config.get("plantilla", {}).get("nombre") == PLANTILLA and os.path.exists(LOG_VIGENTE):
    abortar("esta campana ya estaba preparada y tiene envios registrados. "
            "No hace falta correr el script otra vez: sigue desde el panel.")

# 3. La imagen tiene que existir: si no, falta el Redeploy.
if not os.path.exists(IMAGEN):
    abortar(f"no encuentro {IMAGEN}. Falta hacer el Redeploy en Coolify.")
print(f"[1/4] Imagen encontrada: {IMAGEN} ({os.path.getsize(IMAGEN):,} bytes)")

# 4. La plantilla tiene que estar aprobada. Mientras este en revision, Meta
#    rechaza cada mensaje: mejor enterarse aqui que con 1000 errores en el log.
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

# 5. Apartar el log anterior con la fecha, para no pisar ninguno. Antes, contar
#    lo que salio en las ultimas 24 horas: el log nuevo empieza en cero, pero el
#    limite diario de Meta sigue contando lo de la campana anterior.
if os.path.exists(LOG_VIGENTE):
    recientes = Registro(LOG_VIGENTE).enviados_ultimas_24h()
    sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    destino = os.path.join(DATOS, "logs", f"envios-{sello}.csv")
    shutil.move(LOG_VIGENTE, destino)
    print(f"[3/4] Log anterior guardado en {destino}")
    print(f"        enviados en las ultimas 24 horas: {recientes}")
    if recientes:
        print("        ATENCION: Meta limita los mensajes por dia. Si al enviar aparecen "
              "fallidos por limite, relanza manana: no se repite a nadie.")
else:
    print("[3/4] No habia log vigente; se creara uno nuevo")

# 6. Apuntar la configuracion.
config["_nota"] = ("CAMPANA ACTIVA: Transmision virtual del dia 2, DAMA Week "
                   "Internacional 2026 (19 de noviembre).")
config["plantilla"]["nombre"] = PLANTILLA
config["plantilla"]["idioma"] = IDIOMA
# {{1}} es el primer nombre de la columna Nombre. La plantilla tiene una sola
# variable y botones de enlace fijo: mandar mas o menos parametros hace que
# Meta rechace el mensaje.
config["plantilla"]["parametros_cuerpo"] = [{"origen": "nombre_normalizado"}]
config["plantilla"]["imagen_cabecera"] = IMAGEN
config["plantilla"]["parametro_boton_url"] = None
config["envio"]["nombre_por_defecto"] = SALUDO_POR_DEFECTO
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
print(f"        variables : {len(final.plantilla.parametros_cuerpo)} "
      f"(primer nombre; si falta: '{final.envio.nombre_por_defecto}')")
print(f"        imagen    : {final.plantilla.imagen_cabecera}")
print(f"        ritmo     : {final.envio.segundos_entre_mensajes} s")
print(f"        tope      : {final.envio.tope_diario}")

print("\nLISTO. No vuelvas a correr este script. Ahora, desde el panel:")
print(f"  1. Sube {PRUEBA} -> debe decir 4 validos, 0 descartados. Escribe 4 y lanza.")
print("  2. Revisa en los celulares de prueba: remitente, imagen, saludo y los dos botones.")
print(f"  3. Sube {LISTA} -> {CONTACTOS_ESPERADOS} validos, 0 descartados, "
      f"{PENDIENTES_TRAS_PRUEBA} pendientes.")
print(f"  4. Escribe {PENDIENTES_TRAS_PRUEBA} y lanza.")
