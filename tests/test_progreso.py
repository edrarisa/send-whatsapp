from openpyxl import Workbook

from src.progreso import resumen
from src.registro import ENVIADO, FALLO, Registro


def _excel(tmp_path, filas):
    wb = Workbook()
    ws = wb.active
    ws.append(["Nombre", "Teléfono"])
    for fila in filas:
        ws.append(list(fila))
    ruta = tmp_path / "contactos.xlsx"
    wb.save(ruta)
    return str(ruta)


def test_sin_log_todo_esta_pendiente(tmp_path):
    excel = _excel(tmp_path, [("Ana", "+573001234567"), ("Luis", "+573009876543")])

    datos = resumen(str(tmp_path / "envios.csv"), excel)

    assert datos["total"] == 2
    assert datos["enviados"] == 0
    assert datos["pendientes"] == 2
    assert datos["fallidos"] == 0


def test_cuenta_enviados_y_pendientes(tmp_path):
    excel = _excel(tmp_path, [("Ana", "+573001234567"), ("Luis", "+573009876543")])
    log = str(tmp_path / "envios.csv")
    registro = Registro(log)
    registro.anotar("573001234567", "Ana", ENVIADO, message_id="wamid.A")
    registro.cerrar()

    datos = resumen(log, excel)

    assert datos["enviados"] == 1
    assert datos["pendientes"] == 1


def test_los_fallos_siguen_pendientes(tmp_path):
    # Un fallo no es un envio: ese contacto se reintentara en la proxima corrida.
    excel = _excel(tmp_path, [("Ana", "+573001234567")])
    log = str(tmp_path / "envios.csv")
    registro = Registro(log)
    registro.anotar("573001234567", "Ana", FALLO, codigo_error="131026",
                    mensaje_error="no tiene WhatsApp")
    registro.cerrar()

    datos = resumen(log, excel)

    assert datos["enviados"] == 0
    assert datos["fallidos"] == 1
    assert datos["pendientes"] == 1


def test_devuelve_los_ultimos_fallos_para_mostrarlos(tmp_path):
    excel = _excel(tmp_path, [("Ana", "+573001234567"), ("Luis", "+573009876543")])
    log = str(tmp_path / "envios.csv")
    registro = Registro(log)
    registro.anotar("573001234567", "Ana", FALLO, codigo_error="131026",
                    mensaje_error="no tiene WhatsApp")
    registro.cerrar()

    datos = resumen(log, excel)

    assert len(datos["errores"]) == 1
    assert datos["errores"][0]["nombre"] == "Ana"
    assert "131026" in datos["errores"][0]["error"]


def test_sin_excel_no_revienta(tmp_path):
    datos = resumen(str(tmp_path / "envios.csv"), str(tmp_path / "no-existe.xlsx"))

    assert datos["total"] == 0
    assert datos["pendientes"] == 0


def test_no_expone_telefonos_completos(tmp_path):
    # La pagina no debe mostrar numeros de personas: solo nombre y motivo.
    excel = _excel(tmp_path, [("Ana", "+573001234567")])
    log = str(tmp_path / "envios.csv")
    registro = Registro(log)
    registro.anotar("573001234567", "Ana", FALLO, codigo_error="131026",
                    mensaje_error="x")
    registro.cerrar()

    datos = resumen(log, excel)

    assert "573001234567" not in str(datos)
