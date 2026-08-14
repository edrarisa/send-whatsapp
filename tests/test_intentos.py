from src.intentos import ControlIntentos


def test_al_principio_no_esta_bloqueado():
    control = ControlIntentos(ahora=lambda: 1000.0)

    assert control.segundos_de_espera() == 0


def test_los_primeros_fallos_no_bloquean():
    control = ControlIntentos(maximo=3, ahora=lambda: 1000.0)

    control.registrar_fallo()
    control.registrar_fallo()

    assert control.segundos_de_espera() == 0


def test_al_tercer_fallo_empieza_la_espera():
    control = ControlIntentos(maximo=3, espera_base=5, ahora=lambda: 1000.0)

    for _ in range(3):
        control.registrar_fallo()

    assert control.segundos_de_espera() == 5


def test_la_espera_se_duplica_con_cada_fallo_extra():
    reloj = {"t": 1000.0}
    control = ControlIntentos(maximo=3, espera_base=5, ahora=lambda: reloj["t"])

    for _ in range(4):
        control.registrar_fallo()

    assert control.segundos_de_espera() == 10

    control.registrar_fallo()
    assert control.segundos_de_espera() == 20


def test_la_espera_se_agota_con_el_tiempo():
    reloj = {"t": 1000.0}
    control = ControlIntentos(maximo=3, espera_base=5, ahora=lambda: reloj["t"])

    for _ in range(3):
        control.registrar_fallo()
    assert control.segundos_de_espera() == 5

    reloj["t"] = 1006.0
    assert control.segundos_de_espera() == 0


def test_un_acierto_borra_el_historial():
    control = ControlIntentos(maximo=3, espera_base=5, ahora=lambda: 1000.0)

    for _ in range(5):
        control.registrar_fallo()
    control.registrar_acierto()

    assert control.segundos_de_espera() == 0


def test_la_espera_tiene_techo():
    control = ControlIntentos(maximo=3, espera_base=5, espera_maxima=60,
                              ahora=lambda: 1000.0)

    for _ in range(20):
        control.registrar_fallo()

    assert control.segundos_de_espera() == 60
