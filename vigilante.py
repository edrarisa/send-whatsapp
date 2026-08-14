"""Vigila las ordenes del panel y ejecuta el envio.

Corre dentro del contenedor `enviador`, que es el unico que tiene el token.
El panel deja una solicitud en el volumen compartido y este bucle la recoge.
Asi el panel puede pedir un envio sin llegar a manejar credenciales.
"""

import os
import subprocess
import sys
import time

from src.ordenes import cerrar, tomar

CARPETA_ORDENES = os.environ.get("RUTA_ORDENES", "/datos/ordenes")
CONFIG = os.environ.get("RUTA_CAMPANA", "/datos/campana.json")
INTERVALO = float(os.environ.get("INTERVALO_VIGILANTE", "5"))

# Cuanto texto de la corrida se guarda como detalle. El log completo vive en
# el CSV; aqui basta el final, que es donde esta el resumen.
MAXIMO_DETALLE = 4000


def ejecutar_envio(config):
    """Lanza enviar.py y devuelve (codigo de salida, salida combinada)."""
    proceso = subprocess.run(
        [sys.executable, "enviar.py", "--config", config],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    salida = (proceso.stdout or "") + (proceso.stderr or "")
    return proceso.returncode, salida[-MAXIMO_DETALLE:]


def atender_una_vez(carpeta, config, ejecutor=ejecutar_envio):
    """Si hay una solicitud, la ejecuta. Devuelve si atendio algo."""
    orden = tomar(carpeta)
    if orden is None:
        return False

    try:
        codigo, salida = ejecutor(config)
        cerrar(carpeta, exito=(codigo == 0), detalle=salida)
    except Exception as error:
        # Pase lo que pase, la orden no puede quedarse en_curso: bloquearia
        # todos los envios siguientes.
        cerrar(carpeta, exito=False, detalle=f"El envio no pudo ejecutarse: {error}")

    return True


def main():
    print(f"Vigilante en marcha. Ordenes en {CARPETA_ORDENES}, cada {INTERVALO}s.",
          flush=True)
    os.makedirs(CARPETA_ORDENES, exist_ok=True)

    while True:
        try:
            if atender_una_vez(CARPETA_ORDENES, CONFIG):
                print("Orden atendida.", flush=True)
        except Exception as error:
            # Un fallo inesperado no debe matar el bucle.
            print(f"Error en el vigilante: {error}", flush=True)
        time.sleep(INTERVALO)


if __name__ == "__main__":
    main()
