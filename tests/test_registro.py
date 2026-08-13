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


# --- Cupo de las ultimas 24 horas -------------------------------------------
# El limite de Meta es por ventana movil de 24h, no por "corrida". Sin esto,
# dos ejecuciones el mismo dia se pasan del tope sin darse cuenta.

from datetime import datetime, timedelta, timezone


def _escribir_log(ruta, filas):
    """Escribe un log a mano para poder controlar los timestamps."""
    with open(ruta, "w", encoding="utf-8", newline="") as archivo:
        archivo.write("timestamp,telefono,nombre,estado,message_id,codigo_error,mensaje_error\n")
        for momento, telefono, estado in filas:
            archivo.write(f"{momento.isoformat()},{telefono},X,{estado},,,\n")


def test_sin_log_previo_no_hay_nada_enviado_en_24h(tmp_path):
    assert Registro(str(tmp_path / "envios.csv")).enviados_ultimas_24h() == 0


def test_cuenta_los_enviados_dentro_de_la_ventana(tmp_path):
    ruta = str(tmp_path / "envios.csv")
    ahora = datetime.now(timezone.utc)
    _escribir_log(ruta, [
        (ahora - timedelta(hours=1), "571", "enviado"),
        (ahora - timedelta(hours=23), "572", "enviado"),
    ])

    assert Registro(ruta).enviados_ultimas_24h() == 2


def test_ignora_los_enviados_hace_mas_de_24_horas(tmp_path):
    ruta = str(tmp_path / "envios.csv")
    ahora = datetime.now(timezone.utc)
    _escribir_log(ruta, [
        (ahora - timedelta(hours=25), "571", "enviado"),
        (ahora - timedelta(days=3), "572", "enviado"),
        (ahora - timedelta(hours=2), "573", "enviado"),
    ])

    assert Registro(ruta).enviados_ultimas_24h() == 1


def test_los_fallos_no_consumen_cupo(tmp_path):
    ruta = str(tmp_path / "envios.csv")
    ahora = datetime.now(timezone.utc)
    _escribir_log(ruta, [
        (ahora - timedelta(minutes=5), "571", "enviado"),
        (ahora - timedelta(minutes=4), "572", "fallo"),
    ])

    assert Registro(ruta).enviados_ultimas_24h() == 1


def test_resultados_devuelve_el_estado_de_cada_telefono(tmp_path):
    ruta = str(tmp_path / "envios.csv")
    registro = Registro(ruta)
    registro.anotar("571", "Ana", "enviado", message_id="wamid.A")
    registro.anotar("572", "Luis", "fallo", codigo_error="131026",
                    mensaje_error="Recipient not found")
    registro.cerrar()

    resultados = Registro(ruta).resultados()

    assert resultados["571"][0] == "enviado"
    assert resultados["571"][1].startswith("20")          # el timestamp
    assert resultados["572"][0] == "fallo"
    assert "131026" in resultados["572"][2]
    assert "Recipient not found" in resultados["572"][2]


def test_resultados_se_queda_con_el_intento_mas_reciente(tmp_path):
    ruta = str(tmp_path / "envios.csv")
    registro = Registro(ruta)
    registro.anotar("571", "Ana", "fallo", codigo_error="500", mensaje_error="server")
    registro.anotar("571", "Ana", "enviado", message_id="wamid.A")
    registro.cerrar()

    assert Registro(ruta).resultados()["571"][0] == "enviado"


def test_una_fila_con_timestamp_corrupto_no_tumba_el_conteo(tmp_path):
    ruta = str(tmp_path / "envios.csv")
    ahora = datetime.now(timezone.utc)
    with open(ruta, "w", encoding="utf-8", newline="") as archivo:
        archivo.write("timestamp,telefono,nombre,estado,message_id,codigo_error,mensaje_error\n")
        archivo.write("basura-no-es-fecha,571,X,enviado,,,\n")
        archivo.write(f"{(ahora - timedelta(hours=1)).isoformat()},572,X,enviado,,,\n")

    assert Registro(ruta).enviados_ultimas_24h() == 1
