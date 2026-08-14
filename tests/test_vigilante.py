from src.ordenes import estado, solicitar
from vigilante import atender_una_vez


class EjecutorFalso:
    """Sustituye a la ejecucion real de enviar.py."""

    def __init__(self, codigo=0, salida="Enviados: 10   Fallidos: 0"):
        self.codigo = codigo
        self.salida = salida
        self.llamadas = 0

    def __call__(self, config):
        self.llamadas += 1
        return self.codigo, self.salida


def test_sin_solicitud_no_hace_nada(tmp_path):
    ejecutor = EjecutorFalso()

    atendio = atender_una_vez(str(tmp_path), "/datos/campana.json", ejecutor)

    assert atendio is False
    assert ejecutor.llamadas == 0


def test_con_solicitud_ejecuta_el_envio(tmp_path):
    solicitar(str(tmp_path), pedidos=10)
    ejecutor = EjecutorFalso()

    atendio = atender_una_vez(str(tmp_path), "/datos/campana.json", ejecutor)

    assert atendio is True
    assert ejecutor.llamadas == 1


def test_archiva_el_resultado_al_terminar(tmp_path):
    solicitar(str(tmp_path), pedidos=10)

    atender_una_vez(str(tmp_path), "/datos/campana.json",
                    EjecutorFalso(codigo=0, salida="Enviados: 10   Fallidos: 0"))

    ultima = estado(str(tmp_path))["ultima"]
    assert ultima["exito"] is True
    assert "Enviados: 10" in ultima["detalle"]
    assert estado(str(tmp_path))["en_curso"] is None


def test_un_envio_fallido_queda_marcado_como_tal(tmp_path):
    solicitar(str(tmp_path), pedidos=10)

    atender_una_vez(str(tmp_path), "/datos/campana.json",
                    EjecutorFalso(codigo=1, salida="TOKEN RECHAZADO POR META"))

    ultima = estado(str(tmp_path))["ultima"]
    assert ultima["exito"] is False
    assert "TOKEN" in ultima["detalle"]


def test_una_excepcion_del_ejecutor_no_deja_la_orden_colgada(tmp_path):
    # Si el proceso revienta, la orden no puede quedarse en_curso para siempre:
    # bloquearia todos los envios siguientes.
    solicitar(str(tmp_path), pedidos=10)

    def revienta(config):
        raise RuntimeError("algo exploto")

    atender_una_vez(str(tmp_path), "/datos/campana.json", revienta)

    resultado = estado(str(tmp_path))
    assert resultado["en_curso"] is None
    assert resultado["ultima"]["exito"] is False
    assert "algo exploto" in resultado["ultima"]["detalle"]


def test_solo_atiende_una_orden_por_vuelta(tmp_path):
    solicitar(str(tmp_path), pedidos=10)
    ejecutor = EjecutorFalso()

    atender_una_vez(str(tmp_path), "/datos/campana.json", ejecutor)
    atender_una_vez(str(tmp_path), "/datos/campana.json", ejecutor)

    assert ejecutor.llamadas == 1
