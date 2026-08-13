"""Cliente de la Cloud API de WhatsApp. No sabe nada de Excel."""

import os
import time
from dataclasses import dataclass

# Formatos de imagen que Meta acepta como cabecera de plantilla.
TIPOS_DE_IMAGEN = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

TAMANO_MAXIMO = 5 * 1024 * 1024      # 5 MB, limite de Meta


class ImagenNoSubida(Exception):
    """No se pudo subir la imagen de cabecera a Meta."""


def referencia_imagen(valor):
    """Traduce lo configurado en `imagen_cabecera` a lo que espera la API.

    Una URL se manda tal cual como "link" y Meta la descarga en cada mensaje.
    Un archivo local devuelve None: hay que subirlo antes con subir_imagen() y
    usar el ID resultante, que se reutiliza en todos los envios.
    """
    if not valor:
        return None
    if str(valor).startswith(("http://", "https://")):
        return {"link": valor}
    return None


def resolver_parametro(parametro, contacto):
    """Devuelve el texto que va a reemplazar una variable de la plantilla."""
    if parametro.origen == "nombre_normalizado":
        return contacto.nombre
    if parametro.origen == "fijo":
        return parametro.valor
    if parametro.origen == "columna":
        valor = contacto.crudo.get(parametro.nombre)
        return "" if valor is None else str(valor).strip()
    raise ValueError(f"Origen de parametro desconocido: {parametro.origen}")


def construir_payload(contacto, plantilla, imagen=None):
    """Arma el cuerpo JSON de POST /{phone_number_id}/messages.

    `imagen` es la referencia ya resuelta ({"id": ...} o {"link": ...}). Si no
    se pasa, se deduce de la plantilla, que solo funciona cuando es una URL.
    """
    componentes = []

    cabecera = imagen or referencia_imagen(plantilla.imagen_cabecera)
    if cabecera:
        componentes.append({
            "type": "header",
            "parameters": [{"type": "image", "image": cabecera}],
        })

    if plantilla.parametros_cuerpo:
        componentes.append({
            "type": "body",
            "parameters": [
                {"type": "text", "text": resolver_parametro(p, contacto)}
                for p in plantilla.parametros_cuerpo
            ],
        })

    if plantilla.parametro_boton_url:
        componentes.append({
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [
                {"type": "text",
                 "text": resolver_parametro(plantilla.parametro_boton_url, contacto)}
            ],
        })

    template = {"name": plantilla.nombre, "language": {"code": plantilla.idioma}}
    if componentes:
        template["components"] = componentes

    return {
        "messaging_product": "whatsapp",
        "to": contacto.telefono,
        "type": "template",
        "template": template,
    }


# El token esta mal o fue revocado: no tiene sentido seguir intentando.
CODIGO_TOKEN_INVALIDO = 190

# Errores de Meta que se resuelven solos si esperamos un poco.
HTTP_REINTENTABLES = (408, 429, 500, 502, 503, 504)


class TokenInvalido(Exception):
    """El token fue rechazado. Hay que abortar la corrida completa."""


@dataclass(frozen=True)
class Resultado:
    ok: bool
    message_id: str = ""
    codigo: str = ""
    mensaje: str = ""
    reintentable: bool = False


def enviar_mensaje(sesion, meta, payload, timeout=30):
    """Hace UN intento. No reintenta, no espera. Devuelve un Resultado."""
    url = f"https://graph.facebook.com/{meta.version_api}/{meta.phone_number_id}/messages"
    cabeceras = {
        "Authorization": f"Bearer {meta.token}",
        "Content-Type": "application/json",
    }

    try:
        respuesta = sesion.post(url, json=payload, headers=cabeceras, timeout=timeout)
    except Exception as error:                      # red caida, DNS, timeout
        return Resultado(ok=False, codigo="red", mensaje=str(error), reintentable=True)

    try:
        cuerpo = respuesta.json()
    except Exception:
        cuerpo = {}

    if respuesta.status_code == 200:
        mensajes = cuerpo.get("messages") or [{}]
        return Resultado(ok=True, message_id=mensajes[0].get("id", ""))

    error = cuerpo.get("error") or {}
    codigo = error.get("code", "")

    if codigo == CODIGO_TOKEN_INVALIDO:
        raise TokenInvalido(error.get("message", "Token rechazado por Meta"))

    return Resultado(
        ok=False,
        codigo=str(codigo) if codigo != "" else str(respuesta.status_code),
        mensaje=error.get("message", "") or f"HTTP {respuesta.status_code}",
        reintentable=respuesta.status_code in HTTP_REINTENTABLES,
    )


def subir_imagen(sesion, meta, ruta, timeout=120):
    """Sube la imagen a Meta una sola vez y devuelve su ID de medio.

    Se hace asi en vez de mandar una URL porque con URL Meta descarga la imagen
    en CADA mensaje: con 820 envios serian 820 descargas contra el servidor de
    origen. El ID dura 30 dias, de sobra para una campana.
    """
    if not os.path.exists(ruta):
        raise ImagenNoSubida(f"No encuentro la imagen: {ruta}")

    extension = os.path.splitext(ruta)[1].lower()
    if extension not in TIPOS_DE_IMAGEN:
        raise ImagenNoSubida(
            f"Meta no acepta '{extension}' como cabecera de plantilla. "
            f"Usa {', '.join(sorted(TIPOS_DE_IMAGEN))}."
        )

    tamano = os.path.getsize(ruta)
    if tamano > TAMANO_MAXIMO:
        raise ImagenNoSubida(
            f"La imagen pesa {tamano / 1024 / 1024:.1f} MB y el limite son 5 MB."
        )

    url = f"https://graph.facebook.com/{meta.version_api}/{meta.phone_number_id}/media"
    cabeceras = {"Authorization": f"Bearer {meta.token}"}   # sin Content-Type: lo pone requests

    try:
        with open(ruta, "rb") as archivo:
            respuesta = sesion.post(
                url,
                data={"messaging_product": "whatsapp"},
                files={"file": (os.path.basename(ruta), archivo, TIPOS_DE_IMAGEN[extension])},
                headers=cabeceras,
                timeout=timeout,
            )
    except OSError as error:
        raise ImagenNoSubida(f"No pude leer {ruta}: {error}")

    try:
        cuerpo = respuesta.json()
    except Exception:
        cuerpo = {}

    if respuesta.status_code != 200 or "id" not in cuerpo:
        detalle = (cuerpo.get("error") or {}).get("message") or f"HTTP {respuesta.status_code}"
        raise ImagenNoSubida(f"Meta rechazo la imagen: {detalle}")

    return cuerpo["id"]


def enviar_con_reintentos(sesion, meta, payload, intentos=3, espera_inicial=2, timeout=30):
    """Reintenta con espera creciente, pero solo los errores que valen la pena."""
    espera = espera_inicial
    resultado = None

    for intento in range(intentos):
        resultado = enviar_mensaje(sesion, meta, payload, timeout=timeout)
        if resultado.ok or not resultado.reintentable:
            return resultado
        if intento < intentos - 1:
            time.sleep(espera)
            espera *= 2

    return resultado
