"""Recibe un Excel de contactos y lo pone en su sitio, si es de fiar.

No sabe nada de HTTP: recibe bytes y una ruta de destino.
"""

import os
import tempfile
from collections import Counter
from dataclasses import dataclass, field

from src.contactos import leer_contactos

# Un .xlsx es un contenedor zip; todos empiezan por estos dos bytes. La
# extension la pone el usuario y puede mentir; la cabecera no.
CABECERA_ZIP = b"PK"

TAMANO_MAXIMO = 10 * 1024 * 1024      # 10 MB


class ArchivoRechazado(Exception):
    """El archivo no sirve. El mensaje explica por que."""


class ListaInvalida(Exception):
    """El Excel se lee, pero no sirve como lista de envio."""


@dataclass(frozen=True)
class Resumen:
    validos: int
    descartados: int
    motivos: dict = field(default_factory=dict)


def validar_archivo(nombre, contenido):
    """Comprueba nombre, tamano y contenido. Lanza ArchivoRechazado si algo falla."""
    if not nombre:
        raise ArchivoRechazado("No seleccionaste ningun archivo.")

    if not nombre.lower().endswith(".xlsx"):
        raise ArchivoRechazado(
            "El archivo debe ser .xlsx. Si lo tienes en .csv o .xls, "
            "abrelo en Excel y usa Guardar como."
        )

    if not contenido:
        raise ArchivoRechazado("El archivo esta vacio.")

    if len(contenido) > TAMANO_MAXIMO:
        megas = len(contenido) / 1024 / 1024
        raise ArchivoRechazado(f"El archivo pesa {megas:.1f} MB y el maximo son 10 MB.")

    if not contenido.startswith(CABECERA_ZIP):
        raise ArchivoRechazado(
            "El contenido no es un archivo de Excel, aunque se llame .xlsx."
        )


def guardar_lista(contenido, destino):
    """Deja `contenido` en `destino`, pero solo si es una lista usable.

    Se escribe a un temporal en la MISMA carpeta que el destino y se mueve con
    os.replace, que es atomico dentro del mismo sistema de archivos. Asi el
    destino nunca queda a medio escribir, y un archivo malo jamas reemplaza a
    la lista buena que ya estaba.
    """
    carpeta = os.path.dirname(destino) or "."
    os.makedirs(carpeta, exist_ok=True)

    descriptor, temporal = tempfile.mkstemp(suffix=".xlsx", dir=carpeta)
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(contenido)

        try:
            validos, descartes = leer_contactos(temporal)
        except ValueError as error:
            raise ListaInvalida(str(error))
        except Exception:
            raise ListaInvalida(
                "No pude leer el archivo como Excel. Puede estar danado."
            )

        if not validos:
            motivos = Counter(d.motivo for d in descartes)
            detalle = ", ".join(f"{m}: {n}" for m, n in motivos.items()) or "sin filas"
            raise ListaInvalida(
                f"Ningun contacto valido en el archivo ({detalle}). "
                "No se reemplazo la lista anterior."
            )

        os.replace(temporal, destino)
        temporal = None      # ya no hay que borrarlo: se movio
        return Resumen(
            validos=len(validos),
            descartados=len(descartes),
            motivos=dict(Counter(d.motivo for d in descartes)),
        )
    finally:
        if temporal and os.path.exists(temporal):
            os.unlink(temporal)
