#!/usr/bin/env python3
"""Deja el servidor listo para la campana del dia del evento.

Se corre UNA vez, dentro del contenedor `enviador`, despues de que haya
terminado el envio anterior:

    python preparar-diaevento.py

Hace tres cosas: aparta el log de la campana anterior, apunta campana.json a
la plantilla e imagen del dia del evento, y comprueba que todo cuadre. Se
niega a actuar si hay un envio en marcha.
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone

CAMPANA = "/datos/campana.json"
LOG_VIGENTE = "/datos/logs/envios.csv"
ORDENES = "/datos/ordenes"

PLANTILLA = "conversatorio_hoy_19_agosto_2026"
IMAGEN = "/app/Conectate-hoy-whatsapp.jpg"
RITMO = 5
TOPE = 1100


def abortar(mensaje):
    print(f"\nABORTADO: {mensaje}")
    sys.exit(1)


print("=== PREPARANDO LA CAMPANA DEL DIA DEL EVENTO ===\n")

# 1. Que no haya nada corriendo.
en_curso = os.path.join(ORDENES, "en_curso.json")
if os.path.exists(en_curso):
    abortar("hay un envio en marcha. Espera a que termine y vuelve a correrlo.")

solicitud = os.path.join(ORDENES, "solicitud.json")
if os.path.exists(solicitud):
    abortar("hay un envio solicitado sin arrancar. Espera a que termine.")

# 2. La imagen tiene que existir: si no, falta el Redeploy.
if not os.path.exists(IMAGEN):
    abortar(f"no encuentro {IMAGEN}. Falta hacer el Redeploy en Coolify.")
print(f"[1/3] Imagen encontrada: {IMAGEN} ({os.path.getsize(IMAGEN):,} bytes)")

# 3. Apartar el log anterior con la fecha, para no pisar ninguno.
if os.path.exists(LOG_VIGENTE):
    sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    destino = f"/datos/logs/envios-{sello}.csv"
    shutil.move(LOG_VIGENTE, destino)
    print(f"[2/3] Log anterior guardado en {destino}")
else:
    print("[2/3] No habia log vigente; se creara uno nuevo")

# 4. Apuntar la configuracion.
with open(CAMPANA, encoding="utf-8") as archivo:
    config = json.load(archivo)

config["plantilla"]["nombre"] = PLANTILLA
config["plantilla"]["imagen_cabecera"] = IMAGEN
config["envio"]["segundos_entre_mensajes"] = RITMO
config["envio"]["tope_diario"] = TOPE

with open(CAMPANA, "w", encoding="utf-8") as archivo:
    json.dump(config, archivo, ensure_ascii=False, indent=2)

print("[3/3] Configuracion actualizada:")
print(f"        plantilla : {config['plantilla']['nombre']}")
print(f"        imagen    : {config['plantilla']['imagen_cabecera']}")
print(f"        ritmo     : {config['envio']['segundos_entre_mensajes']} s")
print(f"        tope       : {config['envio']['tope_diario']}")

print("\nLISTO. Ahora, desde el panel:")
print("  1. Sube diaevento-listo.xlsx  -> debe decir 1015 validos, 5 descartados")
print("  2. Escribe el numero de pendientes y lanza")
