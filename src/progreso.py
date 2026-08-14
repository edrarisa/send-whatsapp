"""Como va el envio. Lee el log y la lista; no envia nada."""

import os

from src.contactos import leer_contactos
from src.registro import ENVIADO, FALLO, Registro

MAXIMO_ERRORES = 20

VACIO = {"total": 0, "enviados": 0, "pendientes": 0, "fallidos": 0, "errores": []}


def resumen(ruta_log, ruta_excel):
    """Cuantos van enviados, pendientes y fallidos, y los ultimos errores.

    Deliberadamente NO devuelve telefonos: la pagina que muestra esto no debe
    convertirse en una forma de descargar la lista de contactos.
    """
    if not os.path.exists(ruta_excel):
        return dict(VACIO)

    try:
        validos, _ = leer_contactos(ruta_excel)
    except Exception:
        return dict(VACIO)

    resultados = Registro(ruta_log).resultados()

    enviados = 0
    fallidos = 0
    errores = []

    for contacto in validos:
        estado = (resultados.get(contacto.telefono) or ("", "", ""))[0]
        if estado == ENVIADO:
            enviados += 1
        elif estado == FALLO:
            fallidos += 1
            if len(errores) < MAXIMO_ERRORES:
                errores.append({
                    "nombre": contacto.nombre,
                    "error": resultados[contacto.telefono][2],
                })

    return {
        "total": len(validos),
        "enviados": enviados,
        "fallidos": fallidos,
        "pendientes": len(validos) - enviados,
        "errores": errores,
    }
