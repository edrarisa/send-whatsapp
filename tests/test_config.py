import json

import pytest

from src.config import ConfigInvalida, cargar_config

ENTORNO_COMPLETO = {
    "WHATSAPP_TOKEN": "EAAtoken",
    "WHATSAPP_PHONE_NUMBER_ID": "111222333",
    "GRAPH_API_VERSION": "v21.0",
}


def _escribir(tmp_path, datos, nombre="campana.json"):
    ruta = tmp_path / nombre
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return str(ruta)


def test_carga_una_campana_minima_y_rellena_los_valores_por_defecto(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {"excel": {"ruta": str(tmp_path / "prueba.xlsx")},
             "plantilla": {"nombre": "bonos_popsy_v7", "idioma": "es"}}

    config = cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert config.meta.token == "EAAtoken"
    assert config.meta.phone_number_id == "111222333"
    assert config.plantilla.nombre == "bonos_popsy_v7"
    assert config.envio.segundos_entre_mensajes == 1.5     # valor por defecto
    assert config.envio.tope_diario == 900                 # valor por defecto
    assert config.excel.columna_nombre == "Nombre"         # valor por defecto


def test_falla_claro_si_falta_el_token(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {"excel": {"ruta": str(tmp_path / "prueba.xlsx")},
             "plantilla": {"nombre": "x", "idioma": "es"}}

    with pytest.raises(ConfigInvalida) as error:
        cargar_config(_escribir(tmp_path, datos), {"WHATSAPP_PHONE_NUMBER_ID": "1"})

    assert "WHATSAPP_TOKEN" in str(error.value)


def test_falla_claro_si_el_excel_no_existe(tmp_path):
    datos = {"excel": {"ruta": str(tmp_path / "no-existe.xlsx")},
             "plantilla": {"nombre": "x", "idioma": "es"}}

    with pytest.raises(ConfigInvalida) as error:
        cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert "no-existe.xlsx" in str(error.value)


def test_falla_claro_si_la_plantilla_no_tiene_idioma(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {"excel": {"ruta": str(tmp_path / "prueba.xlsx")},
             "plantilla": {"nombre": "x"}}

    with pytest.raises(ConfigInvalida) as error:
        cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert "idioma" in str(error.value)


def test_falla_claro_si_un_parametro_tiene_un_origen_desconocido(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {
        "excel": {"ruta": str(tmp_path / "prueba.xlsx")},
        "plantilla": {"nombre": "x", "idioma": "es",
                      "parametros_cuerpo": [{"origen": "inventado"}]},
    }

    with pytest.raises(ConfigInvalida) as error:
        cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert "inventado" in str(error.value)


from src.config import leer_entorno


def test_sin_archivo_env_usa_las_variables_del_sistema(tmp_path):
    # Es el caso de un contenedor: no hay .env, los secretos llegan inyectados.
    entorno = leer_entorno({"WHATSAPP_TOKEN": "del-sistema"},
                           ruta_env=str(tmp_path / "no-existe.env"))

    assert entorno["WHATSAPP_TOKEN"] == "del-sistema"


def test_lee_el_archivo_env_cuando_existe(tmp_path):
    ruta = tmp_path / ".env"
    ruta.write_text("WHATSAPP_TOKEN=del-archivo\n", encoding="utf-8")

    entorno = leer_entorno({}, ruta_env=str(ruta))

    assert entorno["WHATSAPP_TOKEN"] == "del-archivo"


def test_la_variable_del_sistema_le_gana_al_archivo(tmp_path):
    # En un servidor gestionado, lo que inyecta el panel manda sobre un .env
    # que se haya quedado olvidado en la imagen.
    ruta = tmp_path / ".env"
    ruta.write_text("WHATSAPP_TOKEN=del-archivo\n", encoding="utf-8")

    entorno = leer_entorno({"WHATSAPP_TOKEN": "del-sistema"}, ruta_env=str(ruta))

    assert entorno["WHATSAPP_TOKEN"] == "del-sistema"


def test_combina_ambas_fuentes(tmp_path):
    ruta = tmp_path / ".env"
    ruta.write_text("WHATSAPP_TOKEN=abc\nGRAPH_API_VERSION=v20.0\n", encoding="utf-8")

    entorno = leer_entorno({"WHATSAPP_PHONE_NUMBER_ID": "123"}, ruta_env=str(ruta))

    assert entorno["WHATSAPP_TOKEN"] == "abc"
    assert entorno["WHATSAPP_PHONE_NUMBER_ID"] == "123"
    assert entorno["GRAPH_API_VERSION"] == "v20.0"


def test_ignora_las_variables_vacias_del_sistema(tmp_path):
    # Coolify y docker-compose exportan variables sin valor como cadena vacia;
    # si no se filtran, pisan al .env con nada.
    ruta = tmp_path / ".env"
    ruta.write_text("WHATSAPP_TOKEN=del-archivo\n", encoding="utf-8")

    entorno = leer_entorno({"WHATSAPP_TOKEN": ""}, ruta_env=str(ruta))

    assert entorno["WHATSAPP_TOKEN"] == "del-archivo"


def test_falla_claro_si_la_imagen_de_cabecera_no_existe(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {
        "excel": {"ruta": str(tmp_path / "prueba.xlsx")},
        "plantilla": {"nombre": "x", "idioma": "es",
                      "imagen_cabecera": str(tmp_path / "no-esta.jpg")},
    }

    with pytest.raises(ConfigInvalida) as error:
        cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert "no-esta.jpg" in str(error.value)


def test_una_url_de_imagen_no_se_valida_contra_el_disco(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {
        "excel": {"ruta": str(tmp_path / "prueba.xlsx")},
        "plantilla": {"nombre": "x", "idioma": "es",
                      "imagen_cabecera": "https://ejemplo.com/banner.jpg"},
    }

    config = cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert config.plantilla.imagen_cabecera == "https://ejemplo.com/banner.jpg"


def test_falla_claro_si_un_parametro_de_columna_no_dice_cual(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {
        "excel": {"ruta": str(tmp_path / "prueba.xlsx")},
        "plantilla": {"nombre": "x", "idioma": "es",
                      "parametros_cuerpo": [{"origen": "columna"}]},
    }

    with pytest.raises(ConfigInvalida) as error:
        cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert "columna" in str(error.value)
