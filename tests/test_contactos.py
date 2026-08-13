import pytest

from src.contactos import normalizar_telefono


@pytest.mark.parametrize("entrada", ["3001234567", 3001234567, " 3001234567 ", "300 123 4567", "300-123-4567"])
def test_movil_colombiano_de_diez_digitos_queda_en_formato_internacional(entrada):
    assert normalizar_telefono(entrada) == ("573001234567", "")


def test_numero_que_ya_trae_el_indicativo_57_se_respeta():
    assert normalizar_telefono("573009876543") == ("573009876543", "")


def test_numero_con_signo_mas_tambien_sirve():
    assert normalizar_telefono("+57 300 987 6543") == ("573009876543", "")


@pytest.mark.parametrize("entrada", [None, "", "   "])
def test_celda_vacia_se_descarta_como_vacio(entrada):
    assert normalizar_telefono(entrada) == (None, "vacio")


@pytest.mark.parametrize("entrada", ["RODRIGUEZ", "0", "57321800000000000"])
def test_basura_evidente_se_descarta_como_basura(entrada):
    assert normalizar_telefono(entrada) == (None, "basura")


@pytest.mark.parametrize(
    "entrada",
    [
        "(1) 2288478",      # fijo viejo de Bogota
        "604 4488388",      # fijo nuevo colombiano, no tiene WhatsApp
        "50761000000",      # Panama
        "5628548443",       # Chile
        "1037578093",       # parece una cedula
        "99999991",         # relleno falso
    ],
)
def test_lo_que_no_es_movil_colombiano_se_descarta_con_su_motivo(entrada):
    assert normalizar_telefono(entrada) == (None, "no_es_movil_co")


from src.contactos import normalizar_nombre


def test_toma_solo_el_primer_nombre():
    assert normalizar_nombre("Adriana Marcela Rodríguez Rocha") == "Adriana"


def test_mayusculas_completas_quedan_capitalizadas():
    assert normalizar_nombre("ANGELA SANCHEZ") == "Angela"
    assert normalizar_nombre("LUIS") == "Luis"


@pytest.mark.parametrize("entrada", ["Andrea nan", "Andrea NaN", "nan Andrea"])
def test_el_literal_nan_de_un_export_de_pandas_se_ignora(entrada):
    assert normalizar_nombre(entrada) == "Andrea"


@pytest.mark.parametrize("entrada", [None, "", "   ", "nan", "123", "-"])
def test_sin_nombre_usable_devuelve_el_valor_por_defecto(entrada):
    assert normalizar_nombre(entrada, por_defecto="Hola") == "Hola"


def test_respeta_tildes():
    assert normalizar_nombre("ANDRÉS PRIETO") == "Andrés"


from openpyxl import Workbook

from src.contactos import Contacto, Descarte, leer_contactos


def _crear_excel(tmp_path, filas, encabezados=("Nombre", "Email", "Teléfono")):
    """Escribe un .xlsx temporal y devuelve su ruta."""
    wb = Workbook()
    ws = wb.active
    ws.append(list(encabezados))
    for fila in filas:
        ws.append(list(fila))
    ruta = tmp_path / "contactos.xlsx"
    wb.save(ruta)
    return str(ruta)


def test_lee_contactos_validos_ya_normalizados(tmp_path):
    ruta = _crear_excel(tmp_path, [
        ("ANA GOMEZ", "ana@ejemplo.com", 3001234567),
        ("LUIS", "luis@ejemplo.com", 3009876543),
    ])

    validos, descartes = leer_contactos(ruta)

    assert descartes == []
    assert [(c.nombre, c.telefono) for c in validos] == [
        ("Ana", "573001234567"),
        ("Luis", "573009876543"),
    ]


def test_guarda_la_fila_original_para_poder_reportarla(tmp_path):
    ruta = _crear_excel(tmp_path, [("ANA GOMEZ", "e@x.com", 3001234567)])

    validos, _ = leer_contactos(ruta)

    assert validos[0].fila == 2                      # fila 1 es el encabezado
    assert validos[0].crudo["Email"] == "e@x.com"


def test_separa_los_descartes_con_su_motivo(tmp_path):
    ruta = _crear_excel(tmp_path, [
        ("Adriana Bolivar", "a@x.com", None),
        ("Adriana Estrada", "b@x.com", "99999991"),
        ("DAVID nan", "c@x.com", "RODRIGUEZ"),
        ("Ana", "d@x.com", 3001234567),
    ])

    validos, descartes = leer_contactos(ruta)

    assert len(validos) == 1
    assert [(d.fila, d.motivo) for d in descartes] == [
        (2, "vacio"),
        (3, "no_es_movil_co"),
        (4, "basura"),
    ]


def test_el_mismo_telefono_repetido_se_conserva_una_sola_vez(tmp_path):
    ruta = _crear_excel(tmp_path, [
        ("Ana", "a@x.com", 3154607013),
        ("Ana Maria", "b@x.com", "3154607013"),
        ("Ana M", "c@x.com", "+57 315 460 7013"),
    ])

    validos, descartes = leer_contactos(ruta)

    assert len(validos) == 1
    assert validos[0].nombre == "Ana"                # se queda el primero
    assert [d.motivo for d in descartes] == ["duplicado", "duplicado"]


def test_ignora_filas_completamente_vacias(tmp_path):
    ruta = _crear_excel(tmp_path, [
        ("Ana", "e@x.com", 3001234567),
        (None, None, None),
    ])

    validos, descartes = leer_contactos(ruta)

    assert len(validos) == 1
    assert descartes == []


def test_avisa_claro_si_falta_una_columna(tmp_path):
    ruta = _crear_excel(tmp_path, [("Ana", "e@x.com")], encabezados=("Nombre", "Email"))

    with pytest.raises(ValueError) as error:
        leer_contactos(ruta)

    assert "Teléfono" in str(error.value)
