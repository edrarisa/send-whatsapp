import io
import os

import pytest
from openpyxl import Workbook

from src.subida import (
    ArchivoRechazado,
    ListaInvalida,
    guardar_lista,
    validar_archivo,
)

# Un .xlsx es un zip: siempre empieza por los bytes "PK".
CABECERA_XLSX = b"PK\x03\x04"


def test_acepta_un_xlsx():
    validar_archivo("contactos.xlsx", CABECERA_XLSX + b"resto del archivo")


def test_acepta_la_extension_en_mayusculas():
    validar_archivo("CONTACTOS.XLSX", CABECERA_XLSX + b"resto")


def test_rechaza_otra_extension():
    with pytest.raises(ArchivoRechazado) as error:
        validar_archivo("contactos.csv", CABECERA_XLSX + b"resto")

    assert ".xlsx" in str(error.value)


def test_rechaza_un_archivo_vacio():
    with pytest.raises(ArchivoRechazado) as error:
        validar_archivo("contactos.xlsx", b"")

    assert "vacio" in str(error.value).lower()


def test_rechaza_algo_que_no_es_un_excel_aunque_se_llame_asi():
    # Un .txt o un ejecutable renombrado: la extension miente, los bytes no.
    with pytest.raises(ArchivoRechazado) as error:
        validar_archivo("contactos.xlsx", b"MZ\x90\x00 esto es un ejecutable")

    assert "no es un archivo de Excel" in str(error.value)


def test_rechaza_un_archivo_demasiado_grande():
    enorme = CABECERA_XLSX + b"x" * (10 * 1024 * 1024)

    with pytest.raises(ArchivoRechazado) as error:
        validar_archivo("contactos.xlsx", enorme)

    assert "10 MB" in str(error.value)


def test_rechaza_un_nombre_sin_archivo():
    with pytest.raises(ArchivoRechazado):
        validar_archivo("", CABECERA_XLSX + b"resto")


# --- Guardado con validacion previa ------------------------------------------


def _excel_en_bytes(filas, encabezados=("Nombre", "Email", "Teléfono")):
    """Devuelve un .xlsx completo como bytes, sin tocar el disco."""
    wb = Workbook()
    ws = wb.active
    ws.append(list(encabezados))
    for fila in filas:
        ws.append(list(fila))
    memoria = io.BytesIO()
    wb.save(memoria)
    return memoria.getvalue()


def test_guarda_una_lista_valida_y_devuelve_el_resumen(tmp_path):
    destino = str(tmp_path / "contactos.xlsx")
    datos = _excel_en_bytes([("Ana", "a@x.com", "+573001234567"),
                             ("Luis", "l@x.com", "+573009876543")])

    resumen = guardar_lista(datos, destino)

    assert os.path.exists(destino)
    assert resumen.validos == 2
    assert resumen.descartados == 0


def test_el_resumen_cuenta_los_descartes_por_motivo(tmp_path):
    destino = str(tmp_path / "contactos.xlsx")
    datos = _excel_en_bytes([("Ana", "a@x.com", "+573001234567"),
                             ("Pedro", "p@x.com", "+12288478"),
                             ("Jose", "j@x.com", "RODRIGUEZ")])

    resumen = guardar_lista(datos, destino)

    assert resumen.validos == 1
    assert resumen.descartados == 2
    assert resumen.motivos["largo_invalido"] == 1
    assert resumen.motivos["basura"] == 1


def test_un_excel_sin_ningun_contacto_valido_se_rechaza(tmp_path):
    destino = str(tmp_path / "contactos.xlsx")
    datos = _excel_en_bytes([("Pedro", "p@x.com", "+12288478")])

    with pytest.raises(ListaInvalida) as error:
        guardar_lista(datos, destino)

    assert "ningun contacto valido" in str(error.value).lower()


def test_un_excel_sin_la_columna_de_telefono_se_rechaza(tmp_path):
    destino = str(tmp_path / "contactos.xlsx")
    datos = _excel_en_bytes([("Ana", "a@x.com")], encabezados=("Nombre", "Email"))

    with pytest.raises(ListaInvalida) as error:
        guardar_lista(datos, destino)

    assert "Teléfono" in str(error.value)


def test_un_archivo_malo_no_pisa_la_lista_anterior(tmp_path):
    # Lo mas importante de todo: subir el Excel equivocado no debe costarte
    # la lista buena que ya tenias.
    destino = str(tmp_path / "contactos.xlsx")
    buena = _excel_en_bytes([("Ana", "a@x.com", "+573001234567")])
    guardar_lista(buena, destino)
    contenido_original = open(destino, "rb").read()

    mala = _excel_en_bytes([("Pedro", "p@x.com", "+12288478")])
    with pytest.raises(ListaInvalida):
        guardar_lista(mala, destino)

    assert open(destino, "rb").read() == contenido_original


def test_crea_la_carpeta_de_destino_si_no_existe(tmp_path):
    destino = str(tmp_path / "nueva" / "carpeta" / "contactos.xlsx")
    datos = _excel_en_bytes([("Ana", "a@x.com", "+573001234567")])

    guardar_lista(datos, destino)

    assert os.path.exists(destino)


def test_no_deja_archivos_temporales_tirados(tmp_path):
    destino = str(tmp_path / "contactos.xlsx")
    mala = _excel_en_bytes([("Pedro", "p@x.com", "+12288478")])

    with pytest.raises(ListaInvalida):
        guardar_lista(mala, destino)

    assert os.listdir(tmp_path) == []
