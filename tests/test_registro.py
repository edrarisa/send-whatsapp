from src.registro import Registro


def test_arranca_vacio_si_no_hay_log_previo(tmp_path):
    registro = Registro(str(tmp_path / "logs" / "envios.csv"))

    assert registro.telefonos_enviados() == set()


def test_anota_un_envio_y_lo_recuerda(tmp_path):
    ruta = str(tmp_path / "envios.csv")
    registro = Registro(ruta)

    registro.anotar(telefono="573001234567", nombre="Ana", estado="enviado",
                    message_id="wamid.ABC")
    registro.cerrar()

    assert Registro(ruta).telefonos_enviados() == {"573001234567"}


def test_un_fallo_no_cuenta_como_enviado_y_se_puede_reintentar_luego(tmp_path):
    ruta = str(tmp_path / "envios.csv")
    registro = Registro(ruta)

    registro.anotar(telefono="573001112233", nombre="Ana", estado="fallo",
                    codigo_error="131026", mensaje_error="Recipient not found")
    registro.cerrar()

    assert Registro(ruta).telefonos_enviados() == set()


def test_escribe_en_el_momento_para_sobrevivir_a_una_caida(tmp_path):
    ruta = str(tmp_path / "envios.csv")
    registro = Registro(ruta)

    registro.anotar(telefono="573001234567", nombre="Ana", estado="enviado",
                    message_id="wamid.ABC")
    # sin cerrar: simulamos que el proceso se muere aqui
    contenido = open(ruta, encoding="utf-8").read()

    assert "573001234567" in contenido


def test_agrega_al_log_existente_en_vez_de_pisarlo(tmp_path):
    ruta = str(tmp_path / "envios.csv")

    primero = Registro(ruta)
    primero.anotar(telefono="573001234567", nombre="Ana", estado="enviado")
    primero.cerrar()

    segundo = Registro(ruta)
    segundo.anotar(telefono="573009876543", nombre="Luis", estado="enviado")
    segundo.cerrar()

    assert Registro(ruta).telefonos_enviados() == {"573001234567", "573009876543"}


def test_escribe_el_encabezado_una_sola_vez(tmp_path):
    ruta = str(tmp_path / "envios.csv")

    primero = Registro(ruta)
    primero.anotar(telefono="1", nombre="A", estado="enviado")
    primero.cerrar()
    segundo = Registro(ruta)
    segundo.anotar(telefono="2", nombre="B", estado="enviado")
    segundo.cerrar()

    lineas = open(ruta, encoding="utf-8").read().strip().splitlines()
    assert sum(1 for linea in lineas if linea.startswith("timestamp")) == 1
