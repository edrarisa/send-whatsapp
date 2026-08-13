import pytest

from src.config import ConfigPlantilla, Parametro
from src.contactos import Contacto
from src.whatsapp import construir_payload

ANA = Contacto(
    nombre="Ana",
    telefono="573001234567",
    fila=2,
    crudo={"Nombre": "ANA GOMEZ", "Email": "e@x.com", "CuponId": "abc123"},
)


def test_plantilla_sin_variables_no_lleva_componentes():
    plantilla = ConfigPlantilla(nombre="hello_world", idioma="en_US")

    assert construir_payload(ANA, plantilla) == {
        "messaging_product": "whatsapp",
        "to": "573001234567",
        "type": "template",
        "template": {"name": "hello_world", "language": {"code": "en_US"}},
    }


def test_el_nombre_normalizado_entra_como_variable_del_cuerpo():
    plantilla = ConfigPlantilla(
        nombre="bonos_popsy_v7",
        idioma="es",
        parametros_cuerpo=[Parametro(origen="nombre_normalizado")],
    )

    payload = construir_payload(ANA, plantilla)

    assert payload["template"]["components"] == [
        {"type": "body", "parameters": [{"type": "text", "text": "Ana"}]}
    ]


def test_un_parametro_puede_venir_de_una_columna_del_excel():
    plantilla = ConfigPlantilla(
        nombre="x",
        idioma="es",
        parametros_cuerpo=[Parametro(origen="columna", nombre="CuponId")],
    )

    payload = construir_payload(ANA, plantilla)

    assert payload["template"]["components"][0]["parameters"] == [
        {"type": "text", "text": "abc123"}
    ]


def test_un_parametro_puede_ser_un_valor_fijo_igual_para_todos():
    plantilla = ConfigPlantilla(
        nombre="x",
        idioma="es",
        parametros_cuerpo=[Parametro(origen="fijo", valor="PRUEBA123")],
    )

    payload = construir_payload(ANA, plantilla)

    assert payload["template"]["components"][0]["parameters"] == [
        {"type": "text", "text": "PRUEBA123"}
    ]


def test_el_boton_url_va_como_componente_aparte_con_su_indice():
    plantilla = ConfigPlantilla(
        nombre="bonos_popsy_v7",
        idioma="es",
        parametros_cuerpo=[Parametro(origen="nombre_normalizado")],
        parametro_boton_url=Parametro(origen="columna", nombre="CuponId"),
    )

    payload = construir_payload(ANA, plantilla)

    assert payload["template"]["components"][1] == {
        "type": "button",
        "sub_type": "url",
        "index": "0",
        "parameters": [{"type": "text", "text": "abc123"}],
    }


def test_la_imagen_de_cabecera_va_primero():
    plantilla = ConfigPlantilla(
        nombre="dama_week_11_noviembre",
        idioma="es_CO",
        parametros_cuerpo=[Parametro(origen="nombre_normalizado")],
        imagen_cabecera="https://ejemplo.com/banner.jpg",
    )

    componentes = construir_payload(ANA, plantilla)["template"]["components"]

    assert componentes[0] == {
        "type": "header",
        "parameters": [
            {"type": "image", "image": {"link": "https://ejemplo.com/banner.jpg"}}
        ],
    }
    assert componentes[1]["type"] == "body"


def test_una_columna_vacia_no_rompe_el_envio():
    contacto_sin_cupon = Contacto(nombre="Ana", telefono="573001112233", fila=3, crudo={})
    plantilla = ConfigPlantilla(
        nombre="x", idioma="es",
        parametros_cuerpo=[Parametro(origen="columna", nombre="CuponId")],
    )

    payload = construir_payload(contacto_sin_cupon, plantilla)

    assert payload["template"]["components"][0]["parameters"] == [
        {"type": "text", "text": ""}
    ]


from src.config import ConfigMeta
from src.whatsapp import TokenInvalido, enviar_con_reintentos, enviar_mensaje

META = ConfigMeta(token="EAAtoken", phone_number_id="111222333", version_api="v21.0")


class RespuestaFalsa:
    def __init__(self, codigo_http, cuerpo):
        self.status_code = codigo_http
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


class SesionFalsa:
    """Sustituye a requests.Session: devuelve respuestas preparadas y guarda las llamadas."""

    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    def post(self, url, json=None, headers=None, timeout=None, data=None, files=None):
        self.llamadas.append({
            "url": url, "json": json, "headers": headers, "data": data, "files": files,
        })
        return self._respuestas.pop(0)


def test_un_envio_exitoso_devuelve_el_id_del_mensaje():
    sesion = SesionFalsa([RespuestaFalsa(200, {"messages": [{"id": "wamid.ABC"}]})])

    resultado = enviar_mensaje(sesion, META, {"to": "573001234567"})

    assert resultado.ok is True
    assert resultado.message_id == "wamid.ABC"


def test_arma_bien_la_url_y_la_cabecera_de_autorizacion():
    sesion = SesionFalsa([RespuestaFalsa(200, {"messages": [{"id": "wamid.ABC"}]})])

    enviar_mensaje(sesion, META, {"to": "573001234567"})

    llamada = sesion.llamadas[0]
    assert llamada["url"] == "https://graph.facebook.com/v21.0/111222333/messages"
    assert llamada["headers"]["Authorization"] == "Bearer EAAtoken"


def test_un_destinatario_sin_whatsapp_falla_pero_no_se_reintenta():
    cuerpo = {"error": {"message": "Recipient not found", "code": 131026}}
    sesion = SesionFalsa([RespuestaFalsa(400, cuerpo)])

    resultado = enviar_mensaje(sesion, META, {})

    assert resultado.ok is False
    assert resultado.codigo == "131026"
    assert resultado.reintentable is False


def test_el_limite_de_tasa_si_es_reintentable():
    sesion = SesionFalsa([RespuestaFalsa(429, {"error": {"message": "rate", "code": 4}})])

    resultado = enviar_mensaje(sesion, META, {})

    assert resultado.reintentable is True


def test_reintenta_hasta_que_funciona():
    sesion = SesionFalsa([
        RespuestaFalsa(429, {"error": {"message": "rate", "code": 4}}),
        RespuestaFalsa(200, {"messages": [{"id": "wamid.OK"}]}),
    ])

    resultado = enviar_con_reintentos(sesion, META, {}, intentos=3, espera_inicial=0)

    assert resultado.ok is True
    assert len(sesion.llamadas) == 2


def test_no_reintenta_un_error_permanente():
    cuerpo = {"error": {"message": "template not found", "code": 132001}}
    sesion = SesionFalsa([RespuestaFalsa(400, cuerpo)])

    resultado = enviar_con_reintentos(sesion, META, {}, intentos=3, espera_inicial=0)

    assert resultado.ok is False
    assert len(sesion.llamadas) == 1


def test_un_token_invalido_aborta_todo_el_proceso():
    cuerpo = {"error": {"message": "Invalid OAuth token", "code": 190}}
    sesion = SesionFalsa([RespuestaFalsa(401, cuerpo)])

    with pytest.raises(TokenInvalido):
        enviar_con_reintentos(sesion, META, {}, intentos=3, espera_inicial=0)


# --- Imagen de cabecera ------------------------------------------------------
# Meta acepta la imagen de dos formas: una URL publica que descarga en CADA
# mensaje, o un ID de medio que se sube una vez y se reutiliza. Preferimos el
# ID: 820 mensajes con URL son 820 descargas contra el servidor de origen.

from src.whatsapp import ImagenNoSubida, referencia_imagen, subir_imagen


def test_una_url_se_usa_tal_cual_como_link():
    assert referencia_imagen("https://ejemplo.com/banner.jpg") == {
        "link": "https://ejemplo.com/banner.jpg"
    }


def test_un_archivo_local_no_es_una_referencia_directa():
    # Hay que subirlo primero; quien llama se encarga.
    assert referencia_imagen("banner.jpg") is None
    assert referencia_imagen(None) is None


def test_el_payload_acepta_una_imagen_por_id():
    plantilla = ConfigPlantilla(
        nombre="conversatorio_datos_agosto_2026",
        idioma="es",
        parametros_cuerpo=[Parametro(origen="nombre_normalizado")],
        imagen_cabecera="banner.jpg",
    )

    payload = construir_payload(ANA, plantilla, imagen={"id": "123456"})

    assert payload["template"]["components"][0] == {
        "type": "header",
        "parameters": [{"type": "image", "image": {"id": "123456"}}],
    }


def test_subir_imagen_devuelve_el_id_de_meta(tmp_path):
    archivo = tmp_path / "banner.jpg"
    archivo.write_bytes(b"\xff\xd8\xff" + b"x" * 100)      # cabecera JPEG falsa
    sesion = SesionFalsa([RespuestaFalsa(200, {"id": "987654321"})])

    assert subir_imagen(sesion, META, str(archivo)) == "987654321"


def test_subir_imagen_apunta_al_endpoint_de_medios(tmp_path):
    archivo = tmp_path / "banner.jpg"
    archivo.write_bytes(b"\xff\xd8\xff" + b"x" * 100)
    sesion = SesionFalsa([RespuestaFalsa(200, {"id": "987654321"})])

    subir_imagen(sesion, META, str(archivo))

    llamada = sesion.llamadas[0]
    assert llamada["url"] == "https://graph.facebook.com/v21.0/111222333/media"
    assert llamada["data"] == {"messaging_product": "whatsapp"}
    assert llamada["headers"]["Authorization"] == "Bearer EAAtoken"
    assert llamada["json"] is None                      # va como multipart, no JSON


def test_subir_imagen_avisa_si_el_archivo_no_existe(tmp_path):
    sesion = SesionFalsa([])

    with pytest.raises(ImagenNoSubida) as error:
        subir_imagen(sesion, META, str(tmp_path / "no-existe.jpg"))

    assert "no-existe.jpg" in str(error.value)


def test_subir_imagen_rechaza_formatos_que_meta_no_acepta(tmp_path):
    archivo = tmp_path / "banner.bmp"
    archivo.write_bytes(b"BM" + b"x" * 100)
    sesion = SesionFalsa([])

    with pytest.raises(ImagenNoSubida) as error:
        subir_imagen(sesion, META, str(archivo))

    assert ".bmp" in str(error.value)


def test_subir_imagen_rechaza_archivos_de_mas_de_5_mb(tmp_path):
    archivo = tmp_path / "enorme.jpg"
    archivo.write_bytes(b"\xff\xd8\xff" + b"x" * (5 * 1024 * 1024))
    sesion = SesionFalsa([])

    with pytest.raises(ImagenNoSubida) as error:
        subir_imagen(sesion, META, str(archivo))

    assert "5 MB" in str(error.value)


def test_subir_imagen_reporta_el_error_de_meta(tmp_path):
    archivo = tmp_path / "banner.jpg"
    archivo.write_bytes(b"\xff\xd8\xff" + b"x" * 100)
    cuerpo = {"error": {"message": "Invalid file type", "code": 100}}
    sesion = SesionFalsa([RespuestaFalsa(400, cuerpo)])

    with pytest.raises(ImagenNoSubida) as error:
        subir_imagen(sesion, META, str(archivo))

    assert "Invalid file type" in str(error.value)
