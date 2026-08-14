import io
import os

import pytest
from openpyxl import Workbook
from werkzeug.security import generate_password_hash

from src.panel import crear_app

CLAVE = "secreta123"


@pytest.fixture
def app(tmp_path):
    return crear_app({
        "PANEL_PASSWORD_HASH": generate_password_hash(CLAVE),
        "PANEL_SECRET_KEY": "para-pruebas",
        "PANEL_DESTINO": str(tmp_path / "entrada" / "contactos.xlsx"),
        "PANEL_COOKIE_SEGURA": False,
    })


@pytest.fixture
def cliente(app):
    return app.test_client()


def _excel(filas, encabezados=("Nombre", "Email", "Teléfono")):
    wb = Workbook()
    ws = wb.active
    ws.append(list(encabezados))
    for fila in filas:
        ws.append(list(fila))
    memoria = io.BytesIO()
    wb.save(memoria)
    memoria.seek(0)
    return memoria


def _entrar(cliente, clave=CLAVE):
    return cliente.post("/login", data={"clave": clave}, follow_redirects=False)


def test_sin_sesion_la_portada_manda_al_login(cliente):
    respuesta = cliente.get("/")

    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


def test_sin_sesion_no_se_puede_subir(cliente):
    respuesta = cliente.post("/subir", data={})

    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


def test_la_clave_correcta_abre_sesion(cliente):
    respuesta = _entrar(cliente)

    assert respuesta.status_code == 302
    assert cliente.get("/").status_code == 200


def test_la_clave_incorrecta_no_abre_sesion(cliente):
    _entrar(cliente, "equivocada")

    assert cliente.get("/").status_code == 302


def test_el_mensaje_de_error_no_revela_nada(cliente):
    respuesta = cliente.post("/login", data={"clave": "equivocada"},
                             follow_redirects=True)

    texto = respuesta.get_data(as_text=True)
    assert "incorrecta" in texto.lower()
    assert CLAVE not in texto


def test_salir_cierra_la_sesion(cliente):
    _entrar(cliente)
    cliente.post("/salir")

    assert cliente.get("/").status_code == 302


def test_la_cookie_de_sesion_esta_protegida(cliente):
    respuesta = _entrar(cliente)

    cookie = respuesta.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie


def test_tras_varios_fallos_hay_que_esperar(cliente):
    for _ in range(4):
        cliente.post("/login", data={"clave": "equivocada"})

    respuesta = cliente.post("/login", data={"clave": CLAVE}, follow_redirects=True)

    # Ni con la clave correcta entra mientras dure el castigo.
    assert "espera" in respuesta.get_data(as_text=True).lower()
    assert cliente.get("/").status_code == 302


# --- Subida por HTTP ---------------------------------------------------------


def test_subir_una_lista_valida_la_deja_en_su_sitio(cliente, app):
    _entrar(cliente)

    respuesta = cliente.post(
        "/subir",
        data={"archivo": (_excel([("Ana", "a@x.com", "+573001234567")]),
                          "contactos.xlsx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert os.path.exists(app.config["PANEL_DESTINO"])
    assert "1 contactos válidos" in respuesta.get_data(as_text=True)


def test_el_resumen_muestra_los_descartes(cliente):
    _entrar(cliente)

    respuesta = cliente.post(
        "/subir",
        data={"archivo": (_excel([("Ana", "a@x.com", "+573001234567"),
                                  ("Pedro", "p@x.com", "+12288478")]),
                          "contactos.xlsx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    texto = respuesta.get_data(as_text=True)
    assert "1 contactos válidos" in texto
    assert "largo_invalido" in texto


def test_un_txt_renombrado_se_rechaza(cliente, app):
    _entrar(cliente)

    respuesta = cliente.post(
        "/subir",
        data={"archivo": (io.BytesIO(b"esto es texto plano"), "contactos.xlsx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert "no es un archivo de Excel" in respuesta.get_data(as_text=True)
    assert not os.path.exists(app.config["PANEL_DESTINO"])


def test_un_excel_malo_no_pisa_la_lista_buena(cliente, app):
    _entrar(cliente)
    cliente.post("/subir",
                 data={"archivo": (_excel([("Ana", "a@x.com", "+573001234567")]),
                                   "contactos.xlsx")},
                 content_type="multipart/form-data")
    original = open(app.config["PANEL_DESTINO"], "rb").read()

    cliente.post("/subir",
                 data={"archivo": (_excel([("Pedro", "p@x.com", "+12288478")]),
                                   "contactos.xlsx")},
                 content_type="multipart/form-data")

    assert open(app.config["PANEL_DESTINO"], "rb").read() == original


def test_el_nombre_del_archivo_no_decide_donde_se_escribe(cliente, app):
    # El destino es fijo: da igual como se llame lo que suban.
    _entrar(cliente)

    cliente.post(
        "/subir",
        data={"archivo": (_excel([("Ana", "a@x.com", "+573001234567")]),
                          "../../../etc/passwd.xlsx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert os.path.exists(app.config["PANEL_DESTINO"])


def test_la_portada_muestra_el_estado_de_la_lista(cliente):
    _entrar(cliente)
    cliente.post("/subir",
                 data={"archivo": (_excel([("Ana", "a@x.com", "+573001234567"),
                                           ("Luis", "l@x.com", "+573009876543")]),
                                   "contactos.xlsx")},
                 content_type="multipart/form-data")

    texto = cliente.get("/").get_data(as_text=True)

    assert "Contactos válidos" in texto
    assert ">2<" in texto
