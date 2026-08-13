"""Carga y valida la configuracion. Falla temprano y con un mensaje util."""

import json
import os
from dataclasses import dataclass, field

ORIGENES_VALIDOS = ("nombre_normalizado", "columna", "fijo")


class ConfigInvalida(Exception):
    """La configuracion esta incompleta o mal formada."""


@dataclass(frozen=True)
class ConfigMeta:
    token: str
    phone_number_id: str
    version_api: str = "v21.0"


@dataclass(frozen=True)
class ConfigExcel:
    ruta: str
    hoja: str = None
    columna_nombre: str = "Nombre"
    columna_telefono: str = "Teléfono"


@dataclass(frozen=True)
class Parametro:
    """De donde sale el valor de una variable de la plantilla."""

    origen: str           # "nombre_normalizado" | "columna" | "fijo"
    nombre: str = ""      # nombre de la columna, si origen == "columna"
    valor: str = ""       # texto literal, si origen == "fijo"


@dataclass(frozen=True)
class ConfigPlantilla:
    nombre: str
    idioma: str
    parametros_cuerpo: list = field(default_factory=list)
    imagen_cabecera: str = None            # URL publica de la imagen, o None
    parametro_boton_url: Parametro = None  # solo si la plantilla lo pide


@dataclass(frozen=True)
class ConfigEnvio:
    segundos_entre_mensajes: float = 1.5
    jitter: float = 0.2
    tope_diario: int = 900
    nombre_por_defecto: str = "Hola"
    ruta_log: str = "logs/envios.csv"


@dataclass(frozen=True)
class Config:
    meta: ConfigMeta
    excel: ConfigExcel
    plantilla: ConfigPlantilla
    envio: ConfigEnvio


def cargar_config(ruta_campana, entorno):
    """Lee el JSON de campana y las variables de entorno. Devuelve un Config.

    `entorno` es un diccionario (normalmente os.environ) para poder probarlo sin
    tocar el sistema.
    """
    meta = _leer_meta(entorno)

    try:
        with open(ruta_campana, encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except FileNotFoundError:
        raise ConfigInvalida(f"No encuentro el archivo de campana: {ruta_campana}")
    except json.JSONDecodeError as error:
        raise ConfigInvalida(f"El JSON de campana esta mal formado: {error}")

    return Config(
        meta=meta,
        excel=_leer_excel(datos.get("excel", {})),
        plantilla=_leer_plantilla(datos.get("plantilla", {})),
        envio=_leer_envio(datos.get("envio", {})),
    )


def _leer_meta(entorno):
    token = (entorno.get("WHATSAPP_TOKEN") or "").strip()
    if not token:
        raise ConfigInvalida(
            "Falta WHATSAPP_TOKEN en el .env. "
            "Se genera en Business Settings > Usuarios del sistema > Generar token."
        )

    phone_number_id = (entorno.get("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
    if not phone_number_id:
        raise ConfigInvalida(
            "Falta WHATSAPP_PHONE_NUMBER_ID en el .env. "
            "Es el ID interno de Meta, no el numero telefonico."
        )

    return ConfigMeta(
        token=token,
        phone_number_id=phone_number_id,
        version_api=(entorno.get("GRAPH_API_VERSION") or "v21.0").strip(),
    )


def _leer_excel(datos):
    ruta = (datos.get("ruta") or "").strip()
    if not ruta:
        raise ConfigInvalida("Falta 'excel.ruta' en el archivo de campana.")
    if not os.path.exists(ruta):
        raise ConfigInvalida(f"No encuentro el Excel: {ruta}")

    return ConfigExcel(
        ruta=ruta,
        hoja=datos.get("hoja") or None,
        columna_nombre=datos.get("columna_nombre") or "Nombre",
        columna_telefono=datos.get("columna_telefono") or "Teléfono",
    )


def _leer_plantilla(datos):
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise ConfigInvalida("Falta 'plantilla.nombre' en el archivo de campana.")

    idioma = (datos.get("idioma") or "").strip()
    if not idioma:
        raise ConfigInvalida(
            "Falta 'plantilla.idioma'. Debe coincidir exacto con el de Meta "
            "(por ejemplo 'es' y 'es_CO' no son intercambiables)."
        )

    parametros = [_leer_parametro(p) for p in datos.get("parametros_cuerpo") or []]

    boton = datos.get("parametro_boton_url")
    return ConfigPlantilla(
        nombre=nombre,
        idioma=idioma,
        parametros_cuerpo=parametros,
        imagen_cabecera=datos.get("imagen_cabecera") or None,
        parametro_boton_url=_leer_parametro(boton) if boton else None,
    )


def _leer_parametro(datos):
    origen = (datos.get("origen") or "").strip()
    if origen not in ORIGENES_VALIDOS:
        raise ConfigInvalida(
            f"Origen de parametro desconocido: '{origen}'. "
            f"Los validos son: {', '.join(ORIGENES_VALIDOS)}."
        )

    if origen == "columna" and not (datos.get("nombre") or "").strip():
        raise ConfigInvalida(
            "Un parametro con origen 'columna' necesita el campo 'nombre' "
            "con el nombre exacto de la columna del Excel."
        )

    return Parametro(
        origen=origen,
        nombre=(datos.get("nombre") or "").strip(),
        valor=str(datos.get("valor") or ""),
    )


def _leer_envio(datos):
    predeterminado = ConfigEnvio()
    return ConfigEnvio(
        segundos_entre_mensajes=float(
            datos.get("segundos_entre_mensajes", predeterminado.segundos_entre_mensajes)
        ),
        jitter=float(datos.get("jitter", predeterminado.jitter)),
        tope_diario=int(datos.get("tope_diario", predeterminado.tope_diario)),
        nombre_por_defecto=datos.get("nombre_por_defecto")
        or predeterminado.nombre_por_defecto,
        ruta_log=datos.get("ruta_log") or predeterminado.ruta_log,
    )
