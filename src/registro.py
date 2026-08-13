"""Log de envios en CSV. Es lo que evita cobrar dos veces al mismo numero."""

import csv
import os
from datetime import datetime, timedelta, timezone

# Meta cuenta su limite sobre una ventana movil de 24 horas, no sobre el dia
# calendario ni sobre "una corrida del script".
VENTANA = timedelta(hours=24)

CAMPOS = [
    "timestamp",
    "telefono",
    "nombre",
    "estado",          # "enviado" | "fallo"
    "message_id",
    "codigo_error",
    "mensaje_error",
]

ENVIADO = "enviado"
FALLO = "fallo"


class Registro:
    """Escribe cada resultado en el momento y sabe a quien ya se le envio.

    Se escribe fila por fila con flush inmediato: si el proceso muere en el
    mensaje 400, los 399 anteriores quedan guardados y no se vuelven a enviar.
    """

    def __init__(self, ruta):
        self.ruta = ruta
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        self._archivo = None
        self._escritor = None

    def telefonos_enviados(self):
        """Los telefonos que ya recibieron el mensaje correctamente."""
        if not os.path.exists(self.ruta):
            return set()

        with open(self.ruta, encoding="utf-8", newline="") as archivo:
            return {
                fila["telefono"]
                for fila in csv.DictReader(archivo)
                if fila.get("estado") == ENVIADO and fila.get("telefono")
            }

    def enviados_ultimas_24h(self):
        """Cuantos mensajes salieron bien en la ventana movil de 24 horas.

        Sirve para no pasarse del limite de Meta cuando el script se corre
        varias veces el mismo dia (cron, reintentos manuales, dos terminales).
        """
        if not os.path.exists(self.ruta):
            return 0

        corte = datetime.now(timezone.utc) - VENTANA
        total = 0

        with open(self.ruta, encoding="utf-8", newline="") as archivo:
            for fila in csv.DictReader(archivo):
                if fila.get("estado") != ENVIADO:
                    continue
                momento = _leer_momento(fila.get("timestamp"))
                # Una fila con fecha ilegible no debe tumbar el conteo, pero
                # tampoco puede colarse gratis: la ignoramos y seguimos.
                if momento is not None and momento >= corte:
                    total += 1

        return total

    def anotar(self, telefono, nombre, estado, message_id="", codigo_error="",
               mensaje_error=""):
        self._abrir()
        self._escritor.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "telefono": telefono,
            "nombre": nombre,
            "estado": estado,
            "message_id": message_id,
            "codigo_error": codigo_error,
            "mensaje_error": mensaje_error,
        })
        self._archivo.flush()          # sin esto, una caida pierde el buffer

    def cerrar(self):
        if self._archivo:
            self._archivo.close()
            self._archivo = None
            self._escritor = None

    def _abrir(self):
        if self._escritor:
            return
        hay_que_escribir_encabezado = (
            not os.path.exists(self.ruta) or os.path.getsize(self.ruta) == 0
        )
        self._archivo = open(self.ruta, "a", encoding="utf-8", newline="")
        self._escritor = csv.DictWriter(self._archivo, fieldnames=CAMPOS)
        if hay_que_escribir_encabezado:
            self._escritor.writeheader()
            self._archivo.flush()


def _leer_momento(texto):
    """Convierte el timestamp del CSV en datetime. Devuelve None si no se puede."""
    if not texto:
        return None
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError:
        return None
    # Un log viejo pudo quedar sin zona horaria: lo tratamos como UTC.
    if momento.tzinfo is None:
        return momento.replace(tzinfo=timezone.utc)
    return momento
