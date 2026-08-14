"""Como el panel le pide al enviador que arranque.

Los dos servicios comparten el volumen /datos pero no se hablan por red. Una
orden es un archivo: el panel lo crea, el vigilante lo toma y lo archiva. Asi
el panel no necesita el token ni el enviador necesita exponer un puerto.
"""

import json
import os
from datetime import datetime, timezone

SOLICITUD = "solicitud.json"
EN_CURSO = "en_curso.json"
ULTIMA = "ultima.json"


class YaHayUnEnvio(Exception):
    """Hay una orden pendiente o en marcha. No se encolan."""


def _ruta(carpeta, nombre):
    return os.path.join(carpeta, nombre)


def _leer(carpeta, nombre):
    ruta = _ruta(carpeta, nombre)
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, encoding="utf-8") as archivo:
            return json.load(archivo)
    except (json.JSONDecodeError, OSError):
        return None


def _escribir(carpeta, nombre, datos):
    os.makedirs(carpeta, exist_ok=True)
    with open(_ruta(carpeta, nombre), "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)


def _ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hay_solicitud(carpeta):
    return os.path.exists(_ruta(carpeta, SOLICITUD))


def solicitar(carpeta, pedidos, ahora=None):
    """El panel pide un envio. Falla si ya hay uno pendiente o en marcha."""
    if hay_solicitud(carpeta) or _leer(carpeta, EN_CURSO):
        raise YaHayUnEnvio("Ya hay un envio pendiente o en marcha.")

    _escribir(carpeta, SOLICITUD, {
        "pedidos": pedidos,
        "solicitada": ahora or _ahora(),
    })


def tomar(carpeta, ahora=None):
    """El vigilante coge la solicitud y la marca en curso. None si no hay."""
    datos = _leer(carpeta, SOLICITUD)
    if datos is None:
        return None

    datos["iniciada"] = ahora or _ahora()
    _escribir(carpeta, EN_CURSO, datos)
    os.unlink(_ruta(carpeta, SOLICITUD))
    return datos


def cerrar(carpeta, exito, detalle, ahora=None):
    """Termina el envio en curso y archiva como quedo."""
    datos = _leer(carpeta, EN_CURSO) or {}
    datos.update({
        "exito": bool(exito),
        "detalle": detalle,
        "terminada": ahora or _ahora(),
    })
    _escribir(carpeta, ULTIMA, datos)

    ruta = _ruta(carpeta, EN_CURSO)
    if os.path.exists(ruta):
        os.unlink(ruta)


def estado(carpeta):
    """Las tres piezas de una vez, para pintar la pagina."""
    return {
        "solicitud": _leer(carpeta, SOLICITUD),
        "en_curso": _leer(carpeta, EN_CURSO),
        "ultima": _leer(carpeta, ULTIMA),
    }
