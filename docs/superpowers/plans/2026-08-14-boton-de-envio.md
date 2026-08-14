# Botón de envío en el panel — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un botón en el panel que lance el envío y una vista del progreso, sin que el panel llegue a tener nunca el token de WhatsApp.

**Architecture:** El panel escribe un archivo de solicitud en el volumen compartido. Un vigilante que corre dentro del contenedor `enviador` —el único que tiene el token— lo detecta y ejecuta `enviar.py`. Toda la comunicación entre los dos servicios pasa por archivos en `/datos`, sin red entre ellos.

**Tech Stack:** Lo que ya hay. Ninguna dependencia nueva.

---

## Por qué por archivos y no por HTTP

Si el panel llamara a una API del enviador, el enviador tendría que exponer un
puerto y autenticar peticiones: más superficie y más cosas que asegurar. Un
archivo en un volumen que ambos ya montan no necesita ni puerto ni credenciales,
y deja una traza legible de lo que se pidió y cuándo.

**La propiedad que se conserva:** el panel no tiene `WHATSAPP_TOKEN`. Aunque lo
comprometan, lo más que consigue el atacante es disparar *tu* campaña a *tu*
lista. No puede escribir a otros números ni cambiar el mensaje.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---------|-----------------|
| `src/ordenes.py` | Crear, tomar y cerrar la solicitud de envío. Sin Flask. |
| `src/progreso.py` | Cuántos van enviados, pendientes y fallidos. Sin Flask. |
| `vigilante.py` | Bucle en el `enviador`: ve la solicitud y ejecuta el envío. |
| `src/panel.py` | Dos rutas nuevas: pedir envío y ver estado. |
| `src/plantillas_html/subir.html` | Se añade la sección de envío. |

Estados de una orden:

```
(nada)  --panel pide-->  solicitud.json
                              |
                    vigilante la toma
                              v
                        en_curso.json  --termina-->  ultima.json
```

---

## Task 1: El archivo de solicitud

**Files:**
- Create: `src/ordenes.py`
- Test: `tests/test_ordenes.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_ordenes.py`:

```python
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
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_ordenes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.ordenes'`

- [ ] **Step 3: Implementar lo mínimo**

Crear `src/ordenes.py`:

```python
"""Como el panel le pide al enviador que arranque.

Los dos servicios comparten el volumen /datos pero no se hablan por red. Una
orden es un archivo: el panel lo crea, el vigilante lo toma y lo archiva. Asi
el panel no necesita el token ni el enviador necesita exponer un puerto.
"""

import json
import os
from datetime import datetime, timezone

SOLICITUD = "solicitud.json"
EN_CURSO = "en_curso.json"
ULTIMA = "ultima.json"


class YaHayUnEnvio(Exception):
    """Hay una orden pendiente o en marcha. No se encolan."""


def _ruta(carpeta, nombre):
    return os.path.join(carpeta, nombre)


def _leer(carpeta, nombre):
    ruta = _ruta(carpeta, nombre)
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, encoding="utf-8") as archivo:
            return json.load(archivo)
    except (json.JSONDecodeError, OSError):
        return None


def _escribir(carpeta, nombre, datos):
    os.makedirs(carpeta, exist_ok=True)
    with open(_ruta(carpeta, nombre), "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)


def _ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hay_solicitud(carpeta):
    return os.path.exists(_ruta(carpeta, SOLICITUD))


def solicitar(carpeta, pedidos, ahora=None):
    """El panel pide un envio. Falla si ya hay uno pendiente o en marcha."""
    if hay_solicitud(carpeta) or _leer(carpeta, EN_CURSO):
        raise YaHayUnEnvio("Ya hay un envio pendiente o en marcha.")

    _escribir(carpeta, SOLICITUD, {
        "pedidos": pedidos,
        "solicitada": ahora or _ahora(),
    })


def tomar(carpeta, ahora=None):
    """El vigilante coge la solicitud y la marca en curso. None si no hay."""
    datos = _leer(carpeta, SOLICITUD)
    if datos is None:
        return None

    datos["iniciada"] = ahora or _ahora()
    _escribir(carpeta, EN_CURSO, datos)
    os.unlink(_ruta(carpeta, SOLICITUD))
    return datos


def cerrar(carpeta, exito, detalle, ahora=None):
    """Termina el envio en curso y archiva como quedo."""
    datos = _leer(carpeta, EN_CURSO) or {}
    datos.update({
        "exito": bool(exito),
        "detalle": detalle,
        "terminada": ahora or _ahora(),
    })
    _escribir(carpeta, ULTIMA, datos)

    ruta = _ruta(carpeta, EN_CURSO)
    if os.path.exists(ruta):
        os.unlink(ruta)


def estado(carpeta):
    """Las tres piezas de una vez, para pintar la pagina."""
    return {
        "solicitud": _leer(carpeta, SOLICITUD),
        "en_curso": _leer(carpeta, EN_CURSO),
        "ultima": _leer(carpeta, ULTIMA),
    }
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_ordenes.py -q`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/ordenes.py tests/test_ordenes.py
git commit -m "feat: ordenes de envio por archivo entre panel y enviador"
```

---

## Task 2: El resumen del progreso

**Files:**
- Create: `src/progreso.py`
- Test: `tests/test_progreso.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_progreso.py`:

```python
import io

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
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_progreso.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.progreso'`

- [ ] **Step 3: Implementar lo mínimo**

Crear `src/progreso.py`:

```python
"""Como va el envio. Lee el log y la lista; no envia nada."""

import os

from src.contactos import leer_contactos
from src.registro import ENVIADO, FALLO, Registro

MAXIMO_ERRORES = 20


def resumen(ruta_log, ruta_excel):
    """Cuantos van enviados, pendientes y fallidos, y los ultimos errores.

    Deliberadamente NO devuelve telefonos: la pagina que muestra esto no debe
    convertirse en una forma de descargar la lista de contactos.
    """
    if not os.path.exists(ruta_excel):
        return {"total": 0, "enviados": 0, "pendientes": 0, "fallidos": 0,
                "errores": []}

    try:
        validos, _ = leer_contactos(ruta_excel)
    except Exception:
        return {"total": 0, "enviados": 0, "pendientes": 0, "fallidos": 0,
                "errores": []}

    registro = Registro(ruta_log)
    resultados = registro.resultados()

    enviados = 0
    fallidos = 0
    errores = []

    for contacto in validos:
        estado = (resultados.get(contacto.telefono) or ("", "", ""))[0]
        if estado == ENVIADO:
            enviados += 1
        elif estado == FALLO:
            fallidos += 1
            if len(errores) < MAXIMO_ERRORES:
                errores.append({
                    "nombre": contacto.nombre,
                    "error": resultados[contacto.telefono][2],
                })

    return {
        "total": len(validos),
        "enviados": enviados,
        "fallidos": fallidos,
        "pendientes": len(validos) - enviados,
        "errores": errores,
    }
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_progreso.py -q`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/progreso.py tests/test_progreso.py
git commit -m "feat: resumen del progreso sin exponer telefonos"
```

---

## Task 3: El vigilante en el enviador

**Files:**
- Create: `vigilante.py`
- Test: `tests/test_vigilante.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_vigilante.py`:

```python
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
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_vigilante.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vigilante'`

- [ ] **Step 3: Implementar lo mínimo**

Crear `vigilante.py`:

```python
"""Vigila las ordenes del panel y ejecuta el envio.

Corre dentro del contenedor `enviador`, que es el unico que tiene el token.
El panel deja una solicitud en el volumen compartido y este bucle la recoge.
"""

import os
import subprocess
import sys
import time

from src.ordenes import cerrar, tomar

CARPETA_ORDENES = os.environ.get("RUTA_ORDENES", "/datos/ordenes")
CONFIG = os.environ.get("RUTA_CAMPANA", "/datos/campana.json")
INTERVALO = float(os.environ.get("INTERVALO_VIGILANTE", "5"))

# Cuanto texto de la corrida se guarda como detalle. El log completo vive en
# el CSV; aqui basta el final, que es donde esta el resumen.
MAXIMO_DETALLE = 4000


def ejecutar_envio(config):
    """Lanza enviar.py y devuelve (codigo de salida, salida combinada)."""
    proceso = subprocess.run(
        [sys.executable, "enviar.py", "--config", config],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    salida = (proceso.stdout or "") + (proceso.stderr or "")
    return proceso.returncode, salida[-MAXIMO_DETALLE:]


def atender_una_vez(carpeta, config, ejecutor=ejecutar_envio):
    """Si hay una solicitud, la ejecuta. Devuelve si atendio algo."""
    orden = tomar(carpeta)
    if orden is None:
        return False

    try:
        codigo, salida = ejecutor(config)
        cerrar(carpeta, exito=(codigo == 0), detalle=salida)
    except Exception as error:
        # Pase lo que pase, la orden no puede quedarse en_curso: bloquearia
        # todos los envios siguientes.
        cerrar(carpeta, exito=False, detalle=f"El envio no pudo ejecutarse: {error}")

    return True


def main():
    print(f"Vigilante en marcha. Ordenes en {CARPETA_ORDENES}, cada {INTERVALO}s.",
          flush=True)
    os.makedirs(CARPETA_ORDENES, exist_ok=True)

    while True:
        try:
            if atender_una_vez(CARPETA_ORDENES, CONFIG):
                print("Orden atendida.", flush=True)
        except Exception as error:
            # Un fallo inesperado no debe matar el bucle.
            print(f"Error en el vigilante: {error}", flush=True)
        time.sleep(INTERVALO)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_vigilante.py -q`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add vigilante.py tests/test_vigilante.py
git commit -m "feat: vigilante que ejecuta las ordenes del panel"
```

---

## Task 4: El botón en el panel

**Files:**
- Modify: `src/panel.py`, `src/plantillas_html/subir.html`
- Test: `tests/test_panel.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_panel.py`:

```python
from src.ordenes import estado as estado_ordenes


def _subir_lista(cliente, filas=None):
    filas = filas or [("Ana", "a@x.com", "+573001234567"),
                      ("Luis", "l@x.com", "+573009876543")]
    return cliente.post(
        "/subir",
        data={"archivo": (_excel(filas), "contactos.xlsx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_sin_sesion_no_se_puede_pedir_un_envio(cliente):
    respuesta = cliente.post("/enviar", data={"confirmacion": "2"})

    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


def test_la_portada_muestra_el_progreso(cliente):
    _entrar(cliente)
    _subir_lista(cliente)

    texto = cliente.get("/").get_data(as_text=True)

    assert "Pendientes" in texto


def test_pedir_un_envio_deja_la_orden(cliente, app):
    _entrar(cliente)
    _subir_lista(cliente)

    cliente.post("/enviar", data={"confirmacion": "2"}, follow_redirects=True)

    assert estado_ordenes(app.config["PANEL_ORDENES"])["solicitud"] is not None


def test_la_confirmacion_tiene_que_coincidir(cliente, app):
    # Escribir un numero distinto al de pendientes no lanza nada: evita que un
    # click accidental mande mil mensajes.
    _entrar(cliente)
    _subir_lista(cliente)

    respuesta = cliente.post("/enviar", data={"confirmacion": "99"},
                             follow_redirects=True)

    assert "no coincide" in respuesta.get_data(as_text=True).lower()
    assert estado_ordenes(app.config["PANEL_ORDENES"])["solicitud"] is None


def test_no_se_puede_pedir_dos_envios_a_la_vez(cliente, app):
    _entrar(cliente)
    _subir_lista(cliente)
    cliente.post("/enviar", data={"confirmacion": "2"})

    respuesta = cliente.post("/enviar", data={"confirmacion": "2"},
                             follow_redirects=True)

    assert "ya hay un envio" in respuesta.get_data(as_text=True).lower()


def test_sin_pendientes_no_se_puede_pedir(cliente, app):
    _entrar(cliente)

    respuesta = cliente.post("/enviar", data={"confirmacion": "0"},
                             follow_redirects=True)

    assert "no hay contactos" in respuesta.get_data(as_text=True).lower()
    assert estado_ordenes(app.config["PANEL_ORDENES"])["solicitud"] is None
```

Y modificar el fixture `app` para que incluya la carpeta de órdenes:

```python
@pytest.fixture
def app(tmp_path):
    return crear_app({
        "PANEL_PASSWORD_HASH": generate_password_hash(CLAVE),
        "PANEL_SECRET_KEY": "para-pruebas",
        "PANEL_DESTINO": str(tmp_path / "entrada" / "contactos.xlsx"),
        "PANEL_LOG": str(tmp_path / "logs" / "envios.csv"),
        "PANEL_ORDENES": str(tmp_path / "ordenes"),
        "PANEL_COOKIE_SEGURA": False,
    })
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_panel.py -q`
Expected: FAIL — `KeyError: 'PANEL_ORDENES'`

- [ ] **Step 3: Añadir la configuración nueva**

En `src/panel.py`, dentro de `crear_app`, ampliar `ajustes`:

```python
    ajustes = {
        "PANEL_PASSWORD_HASH": os.environ.get("PANEL_PASSWORD_HASH", ""),
        "PANEL_SECRET_KEY": os.environ.get("PANEL_SECRET_KEY", ""),
        "PANEL_DESTINO": os.environ.get("PANEL_DESTINO", "/datos/entrada/contactos.xlsx"),
        "PANEL_LOG": os.environ.get("PANEL_LOG", "/datos/logs/envios.csv"),
        "PANEL_ORDENES": os.environ.get("PANEL_ORDENES", "/datos/ordenes"),
        "PANEL_COOKIE_SEGURA": os.environ.get("PANEL_COOKIE_SEGURA", "1") == "1",
    }
```

Y en `app.config.update(...)` añadir:

```python
        PANEL_LOG=ajustes["PANEL_LOG"],
        PANEL_ORDENES=ajustes["PANEL_ORDENES"],
```

- [ ] **Step 4: Añadir los imports**

En `src/panel.py`, junto a los demás:

```python
from src.ordenes import YaHayUnEnvio, estado as estado_ordenes, solicitar
from src.progreso import resumen
```

- [ ] **Step 5: Pasar el progreso a la plantilla**

Reemplazar la ruta `portada` por:

```python
    @app.get("/")
    def portada():
        if not hay_sesion():
            return redirect(url_for("mostrar_login"))
        return render_template(
            "subir.html",
            estado=_estado(app.config["PANEL_DESTINO"]),
            progreso=resumen(app.config["PANEL_LOG"], app.config["PANEL_DESTINO"]),
            ordenes=estado_ordenes(app.config["PANEL_ORDENES"]),
        )
```

- [ ] **Step 6: Añadir la ruta de envío**

En `src/panel.py`, antes de `@app.errorhandler(413)`:

```python
    @app.post("/enviar")
    def pedir_envio():
        if not hay_sesion():
            return redirect(url_for("mostrar_login"))

        progreso = resumen(app.config["PANEL_LOG"], app.config["PANEL_DESTINO"])
        pendientes = progreso["pendientes"]

        if pendientes == 0:
            flash("No hay contactos pendientes de envío.", "error")
            return redirect(url_for("portada"))

        # Escribir el numero exacto es la barrera contra el click accidental:
        # un envio cuesta dinero y no se puede deshacer.
        if request.form.get("confirmacion", "").strip() != str(pendientes):
            flash(
                f"La confirmación no coincide. Escribe {pendientes} para lanzar el envío.",
                "error",
            )
            return redirect(url_for("portada"))

        try:
            solicitar(app.config["PANEL_ORDENES"], pedidos=pendientes)
        except YaHayUnEnvio:
            flash("Ya hay un envío pendiente o en marcha.", "error")
            return redirect(url_for("portada"))

        flash(
            f"Envío solicitado para {pendientes} contactos. "
            "Arranca en unos segundos; recarga la página para ver el avance.",
            "ok",
        )
        return redirect(url_for("portada"))
```

- [ ] **Step 7: Añadir la sección a la plantilla**

En `src/plantillas_html/subir.html`, justo antes de `</main>`:

```html
  <section>
    <h2>Envío</h2>
    <table>
      <tr><td>Total en la lista</td><td>{{ progreso.total }}</td></tr>
      <tr><td>Enviados</td><td>{{ progreso.enviados }}</td></tr>
      <tr><td>Pendientes</td><td><b>{{ progreso.pendientes }}</b></td></tr>
      <tr><td>Fallidos</td><td>{{ progreso.fallidos }}</td></tr>
    </table>

    {% if ordenes.en_curso %}
      <p class="aviso ok" style="margin-top:1rem">
        Envío en marcha desde {{ ordenes.en_curso.iniciada }}.
        Recarga la página para ver el avance.
      </p>
    {% elif ordenes.solicitud %}
      <p class="aviso ok" style="margin-top:1rem">
        Envío solicitado. Arranca en unos segundos.
      </p>
    {% elif progreso.pendientes > 0 %}
      <form method="post" action="/enviar" style="margin-top:1rem">
        <p style="font-size:.9rem;color:#71717a">
          Para lanzar el envío, escribe <b>{{ progreso.pendientes }}</b> y confirma.
          Se enviará por tandas según el tope configurado.
        </p>
        <input type="text" name="confirmacion" inputmode="numeric"
               placeholder="{{ progreso.pendientes }}" required style="width:8rem">
        <button type="submit">Lanzar envío</button>
      </form>
    {% else %}
      <p style="margin-top:1rem">No hay contactos pendientes.</p>
    {% endif %}

    {% if ordenes.ultima %}
      <h2 style="margin-top:1.5rem">Última corrida</h2>
      <p style="font-size:.85rem;color:#71717a">
        {{ ordenes.ultima.terminada }} —
        {{ "correcta" if ordenes.ultima.exito else "con errores" }}
      </p>
      <pre style="font-size:.75rem;background:#fafafa;padding:.75rem;
                  border-radius:6px;overflow-x:auto;max-height:12rem">{{ ordenes.ultima.detalle[-1200:] }}</pre>
    {% endif %}

    {% if progreso.errores %}
      <h2 style="margin-top:1.5rem">Errores</h2>
      <table>
        {% for e in progreso.errores %}
          <tr><td>{{ e.nombre }}</td><td>{{ e.error }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </section>
```

- [ ] **Step 8: Correr las pruebas**

Run: `python -m pytest tests/test_panel.py -q`
Expected: PASS — 26 passed

- [ ] **Step 9: Correr toda la suite**

Run: `python -m pytest -q`
Expected: PASS — 174 passed

- [ ] **Step 10: Commit**

```bash
git add src/panel.py src/plantillas_html/subir.html tests/test_panel.py
git commit -m "feat: boton de envio en el panel con confirmacion escrita"
```

---

## Task 5: Cablearlo en Docker

**Files:**
- Modify: `docker-compose.yaml`, `DESPLIEGUE.md`

- [ ] **Step 1: Cambiar el comando del enviador**

En `docker-compose.yaml`, el servicio `enviador` pasa de `sleep infinity` a
correr el vigilante:

```yaml
  enviador:
    build: .
    container_name: send-whatsapp
    restart: unless-stopped

    # Antes era 'sleep infinity'. Ahora vigila las ordenes que deja el panel.
    # Seguir usando 'docker exec ... python enviar.py' sigue funcionando igual.
    command: python vigilante.py

    environment:
      TZ: America/Bogota
      WHATSAPP_TOKEN: ${WHATSAPP_TOKEN}
      WHATSAPP_PHONE_NUMBER_ID: ${WHATSAPP_PHONE_NUMBER_ID}
      WHATSAPP_WABA_ID: ${WHATSAPP_WABA_ID}
      GRAPH_API_VERSION: ${GRAPH_API_VERSION:-v21.0}
      RUTA_ORDENES: /datos/ordenes
      RUTA_CAMPANA: /datos/campana.json

    volumes:
      - datos:/datos
```

Y al servicio `panel` se le añaden las dos rutas nuevas:

```yaml
      PANEL_LOG: /datos/logs/envios.csv
      PANEL_ORDENES: /datos/ordenes
```

- [ ] **Step 2: Copiar el vigilante en la imagen**

En `Dockerfile`, la línea que copia los archivos raíz debe incluirlo:

```dockerfile
COPY enviar.py vigilante.py conftest.py ./
```

- [ ] **Step 3: Verificar que el vigilante arranca**

Run: `python -c "import vigilante; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Documentarlo**

Agregar a `DESPLIEGUE.md`, en la sección del panel, después de "Qué puede y qué no":

````markdown
### El botón de envío

El panel **no envía**: deja una solicitud en `/datos/ordenes/solicitud.json`.
El contenedor `enviador` —el único con el token— la ve en unos segundos y
ejecuta la corrida.

```
panel  --escribe-->  /datos/ordenes/solicitud.json
                              |
                     vigilante lo recoge
                              v
                        ejecuta enviar.py
```

Para lanzar hay que **escribir el número exacto de pendientes**. Un click
accidental no manda nada.

Solo se admite un envío a la vez. Si el proceso revienta, la orden se archiva
como fallida en vez de quedarse colgada bloqueando los siguientes.

Seguir lanzando por terminal funciona igual que antes:

```bash
python enviar.py --config /datos/campana.json
```
````

- [ ] **Step 5: Correr toda la suite**

Run: `python -m pytest -q`
Expected: PASS — 174 passed

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yaml Dockerfile DESPLIEGUE.md
git commit -m "feat: el enviador corre el vigilante de ordenes"
```

---

## Self-review

**Cobertura:**

| Requisito | Task |
|-----------|------|
| Botón que lanza el envío | 4 |
| El panel nunca ve el token | 1, 3, 5 (comunicación por archivos) |
| Ver cuáles se han enviado | 2, 4 |
| Relanzar y que envíe los que faltan | Ya funcionaba: el log hace el script idempotente |
| Confirmación contra clics accidentales | 4 |
| Un envío a la vez | 1, 4 |
| Una orden nunca se queda colgada | 3 |
| No exponer teléfonos en la web | 2 |

**Consistencia:** `solicitar(carpeta, pedidos, ahora)`, `tomar(carpeta, ahora)`,
`cerrar(carpeta, exito, detalle, ahora)` y `estado(carpeta)` se usan igual en
Tasks 1, 3 y 4. `resumen(ruta_log, ruta_excel)` devuelve siempre las claves
`total, enviados, pendientes, fallidos, errores`, consumidas en Tasks 2 y 4.
Las claves de configuración `PANEL_LOG` y `PANEL_ORDENES` coinciden entre
Tasks 4 y 5.

**Lo que este plan NO hace:** progreso en vivo dentro de una corrida. La página
muestra el estado al recargarla, no un contador que avanza solo. Añadir eso
exigiría JavaScript y un endpoint de sondeo; recargar basta para una corrida de
50 minutos.
