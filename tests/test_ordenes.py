import pytest

from src.ordenes import (
    YaHayUnEnvio,
    cerrar,
    estado,
    hay_solicitud,
    solicitar,
    tomar,
)


def test_al_principio_no_hay_nada(tmp_path):
    assert hay_solicitud(str(tmp_path)) is False
    assert estado(str(tmp_path))["en_curso"] is None
    assert estado(str(tmp_path))["ultima"] is None


def test_solicitar_deja_constancia(tmp_path):
    solicitar(str(tmp_path), pedidos=498, ahora="2026-08-14T21:00:00+00:00")

    assert hay_solicitud(str(tmp_path)) is True
    assert estado(str(tmp_path))["solicitud"]["pedidos"] == 498


def test_no_se_puede_solicitar_dos_veces(tmp_path):
    solicitar(str(tmp_path), pedidos=10, ahora="2026-08-14T21:00:00+00:00")

    with pytest.raises(YaHayUnEnvio):
        solicitar(str(tmp_path), pedidos=10, ahora="2026-08-14T21:01:00+00:00")


def test_tomar_convierte_la_solicitud_en_curso(tmp_path):
    solicitar(str(tmp_path), pedidos=498, ahora="2026-08-14T21:00:00+00:00")

    orden = tomar(str(tmp_path), ahora="2026-08-14T21:00:05+00:00")

    assert orden["pedidos"] == 498
    assert hay_solicitud(str(tmp_path)) is False
    assert estado(str(tmp_path))["en_curso"]["pedidos"] == 498


def test_tomar_sin_solicitud_devuelve_nada(tmp_path):
    assert tomar(str(tmp_path), ahora="2026-08-14T21:00:00+00:00") is None


def test_no_se_puede_solicitar_mientras_hay_uno_en_curso(tmp_path):
    solicitar(str(tmp_path), pedidos=10, ahora="2026-08-14T21:00:00+00:00")
    tomar(str(tmp_path), ahora="2026-08-14T21:00:05+00:00")

    with pytest.raises(YaHayUnEnvio):
        solicitar(str(tmp_path), pedidos=10, ahora="2026-08-14T21:01:00+00:00")


def test_cerrar_archiva_el_resultado(tmp_path):
    solicitar(str(tmp_path), pedidos=10, ahora="2026-08-14T21:00:00+00:00")
    tomar(str(tmp_path), ahora="2026-08-14T21:00:05+00:00")

    cerrar(str(tmp_path), exito=True, detalle="Enviados: 10  Fallidos: 0",
           ahora="2026-08-14T21:10:00+00:00")

    resultado = estado(str(tmp_path))
    assert resultado["en_curso"] is None
    assert resultado["ultima"]["exito"] is True
    assert "Enviados: 10" in resultado["ultima"]["detalle"]


def test_tras_cerrar_se_puede_volver_a_solicitar(tmp_path):
    solicitar(str(tmp_path), pedidos=10, ahora="2026-08-14T21:00:00+00:00")
    tomar(str(tmp_path), ahora="2026-08-14T21:00:05+00:00")
    cerrar(str(tmp_path), exito=True, detalle="ok", ahora="2026-08-14T21:10:00+00:00")

    solicitar(str(tmp_path), pedidos=5, ahora="2026-08-14T22:00:00+00:00")

    assert hay_solicitud(str(tmp_path)) is True


def test_un_fallo_tambien_queda_registrado(tmp_path):
    solicitar(str(tmp_path), pedidos=10, ahora="2026-08-14T21:00:00+00:00")
    tomar(str(tmp_path), ahora="2026-08-14T21:00:05+00:00")

    cerrar(str(tmp_path), exito=False, detalle="TOKEN RECHAZADO",
           ahora="2026-08-14T21:00:30+00:00")

    assert estado(str(tmp_path))["ultima"]["exito"] is False
    assert "TOKEN" in estado(str(tmp_path))["ultima"]["detalle"]
