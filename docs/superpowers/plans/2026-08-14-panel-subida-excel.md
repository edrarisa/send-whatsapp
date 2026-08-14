# Panel de subida del Excel — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una página web con contraseña donde subir el `.xlsx` de contactos, que valida el archivo antes de reemplazar el vigente.

**Architecture:** Servicio Flask independiente en el mismo `docker-compose.yaml`, con la misma imagen que el enviador y compartiendo el volumen `/datos`. Tres piezas de lógica pura (control de intentos, validación de archivo, guardado con validación previa) probadas sin levantar servidor, y una capa Flask delgada encima. `panel.py` no importa `enviar.py` ni recibe el token de WhatsApp: no puede enviar mensajes.

**Tech Stack:** Flask 3.1 y Werkzeug 3.1 (ya instalados), `openpyxl` vía `src/contactos.py`, `pytest` con el cliente de pruebas de Flask. Sin JavaScript.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---------|-----------------|
| `src/panel.py` | Fábrica de la app, rutas y sesión. Delgado: la lógica vive en los módulos de abajo. |
| `src/intentos.py` | Cuenta intentos fallidos de login y calcula la espera. Sin Flask. |
| `src/subida.py` | Valida el archivo recibido y lo guarda si procede. Sin Flask. |
| `src/plantillas_html/login.html` | Formulario de contraseña. |
| `src/plantillas_html/subir.html` | Estado actual + formulario de subida. |
| `tests/test_intentos.py` | Bloqueo por fuerza bruta. |
| `tests/test_subida.py` | Validación y reemplazo del archivo. |
| `tests/test_panel.py` | Rutas, sesión y cookies, con el cliente de pruebas. |
| `docker-compose.yaml` | Se añade el servicio `panel`. |
| `requirements.txt` | Se añade `flask`. |

**Frontera clave:** `intentos.py` y `subida.py` no saben qué es una petición HTTP; `panel.py` no sabe leer Excel. Cada uno se prueba solo.

---

## Task 1: Declarar la dependencia

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Añadir Flask**

`requirements.txt` queda así:

```
openpyxl==3.1.5
requests==2.31.0
python-dotenv==1.0.0
flask==3.1.2
pytest==8.3.4
```

- [ ] **Step 2: Verificar que está instalado**

Run: `python -c "import flask; print(flask.__version__)"`
Expected: `3.1.2`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: anadir flask para el panel de subida"
```

---

## Task 2: Control de intentos fallidos

**Files:**
- Create: `src/intentos.py`
- Test: `tests/test_intentos.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_intentos.py`:

```python
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
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_intentos.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.intentos'`

- [ ] **Step 3: Implementar lo mínimo**

Crear `src/intentos.py`:

```python
"""Frena los intentos de adivinar la contrasena por fuerza bruta.

Vive en memoria a proposito: el panel lo usa una sola persona y reiniciar el
contenedor para saltarse la espera exige acceso al servidor, que es una puerta
mucho mas dificil que la que estamos protegiendo.
"""

import time


class ControlIntentos:
    """Cuenta fallos consecutivos y traduce eso en segundos de espera.

    La espera se duplica con cada fallo a partir del maximo permitido, hasta un
    techo. Un acierto borra el historial.
    """

    def __init__(self, maximo=3, espera_base=5, espera_maxima=300, ahora=None):
        self.maximo = maximo
        self.espera_base = espera_base
        self.espera_maxima = espera_maxima
        self._ahora = ahora or time.monotonic
        self._fallos = 0
        self._ultimo_fallo = 0.0

    def registrar_fallo(self):
        self._fallos += 1
        self._ultimo_fallo = self._ahora()

    def registrar_acierto(self):
        self._fallos = 0
        self._ultimo_fallo = 0.0

    def segundos_de_espera(self):
        """Cuantos segundos faltan para poder reintentar. 0 si se puede ya."""
        if self._fallos < self.maximo:
            return 0

        castigo = min(
            self.espera_base * (2 ** (self._fallos - self.maximo)),
            self.espera_maxima,
        )
        transcurrido = self._ahora() - self._ultimo_fallo
        restante = castigo - transcurrido
        return int(restante) if restante > 0 else 0
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_intentos.py -q`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/intentos.py tests/test_intentos.py
git commit -m "feat: control de intentos fallidos con espera creciente"
```

---

## Task 3: Validar el archivo recibido

**Files:**
- Create: `src/subida.py`
- Test: `tests/test_subida.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_subida.py`:

```python
import pytest

from src.subida import ArchivoRechazado, validar_archivo

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
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_subida.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.subida'`

- [ ] **Step 3: Implementar lo mínimo**

Crear `src/subida.py`:

```python
"""Recibe un Excel de contactos y lo pone en su sitio, si es de fiar.

No sabe nada de HTTP: recibe bytes y una ruta de destino.
"""

import os

# Un .xlsx es un contenedor zip; todos empiezan por estos dos bytes. La
# extension la pone el usuario y puede mentir; la cabecera no.
CABECERA_ZIP = b"PK"

TAMANO_MAXIMO = 10 * 1024 * 1024      # 10 MB


class ArchivoRechazado(Exception):
    """El archivo no sirve. El mensaje explica por que."""


def validar_archivo(nombre, contenido):
    """Comprueba nombre, tamano y contenido. Lanza ArchivoRechazado si algo falla."""
    if not nombre:
        raise ArchivoRechazado("No seleccionaste ningun archivo.")

    if not nombre.lower().endswith(".xlsx"):
        raise ArchivoRechazado(
            "El archivo debe ser .xlsx. Si lo tienes en .csv o .xls, "
            "abrelo en Excel y usa Guardar como."
        )

    if not contenido:
        raise ArchivoRechazado("El archivo esta vacio.")

    if len(contenido) > TAMANO_MAXIMO:
        megas = len(contenido) / 1024 / 1024
        raise ArchivoRechazado(f"El archivo pesa {megas:.1f} MB y el maximo son 10 MB.")

    if not contenido.startswith(CABECERA_ZIP):
        raise ArchivoRechazado(
            "El contenido no es un archivo de Excel, aunque se llame .xlsx."
        )
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_subida.py -q`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/subida.py tests/test_subida.py
git commit -m "feat: validar el Excel subido por extension, tamano y bytes"
```

---

## Task 4: Guardar la lista solo si es usable

**Files:**
- Modify: `src/subida.py`
- Test: `tests/test_subida.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_subida.py`:

```python
import os

from openpyxl import Workbook

from src.subida import ListaInvalida, guardar_lista


def _excel_en_bytes(filas, encabezados=("Nombre", "Email", "Teléfono")):
    """Devuelve un .xlsx completo como bytes, sin tocar el disco."""
    import io

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
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_subida.py -q`
Expected: FAIL — `ImportError: cannot import name 'ListaInvalida'`

- [ ] **Step 3: Implementar lo mínimo**

Agregar al inicio de `src/subida.py`, junto a los imports:

```python
import tempfile
from collections import Counter
from dataclasses import dataclass, field

from src.contactos import leer_contactos
```

Y agregar al final de `src/subida.py`:

```python
class ListaInvalida(Exception):
    """El Excel se lee, pero no sirve como lista de envio."""


@dataclass(frozen=True)
class Resumen:
    validos: int
    descartados: int
    motivos: dict = field(default_factory=dict)


def guardar_lista(contenido, destino):
    """Deja `contenido` en `destino`, pero solo si es una lista usable.

    Se escribe a un temporal en la MISMA carpeta que el destino y se mueve con
    os.replace, que es atomico dentro del mismo sistema de archivos. Asi el
    destino nunca queda a medio escribir, y un archivo malo jamas reemplaza a
    la lista buena que ya estaba.
    """
    carpeta = os.path.dirname(destino) or "."
    os.makedirs(carpeta, exist_ok=True)

    descriptor, temporal = tempfile.mkstemp(suffix=".xlsx", dir=carpeta)
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(contenido)

        try:
            validos, descartes = leer_contactos(temporal)
        except ValueError as error:
            raise ListaInvalida(str(error))
        except Exception:
            raise ListaInvalida(
                "No pude leer el archivo como Excel. Puede estar danado."
            )

        if not validos:
            motivos = Counter(d.motivo for d in descartes)
            detalle = ", ".join(f"{m}: {n}" for m, n in motivos.items()) or "sin filas"
            raise ListaInvalida(
                f"Ningun contacto valido en el archivo ({detalle}). "
                "No se reemplazo la lista anterior."
            )

        os.replace(temporal, destino)
        temporal = None      # ya no hay que borrarlo: se movio
        return Resumen(
            validos=len(validos),
            descartados=len(descartes),
            motivos=dict(Counter(d.motivo for d in descartes)),
        )
    finally:
        if temporal and os.path.exists(temporal):
            os.unlink(temporal)
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_subida.py -q`
Expected: PASS — 14 passed

- [ ] **Step 5: Commit**

```bash
git add src/subida.py tests/test_subida.py
git commit -m "feat: reemplazo atomico de la lista, solo si es usable"
```

---

## Task 5: La app Flask con login

**Files:**
- Create: `src/panel.py`, `src/plantillas_html/login.html`, `src/plantillas_html/subir.html`
- Test: `tests/test_panel.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_panel.py`:

```python
import io

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
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_panel.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.panel'`

- [ ] **Step 3: Escribir las plantillas**

Crear `src/plantillas_html/login.html`:

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Entrar · Lista de contactos</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #f4f4f5; margin: 0;
           display: grid; place-items: center; min-height: 100vh; }
    form { background: #fff; padding: 2rem; border-radius: 8px; width: 20rem;
           box-shadow: 0 1px 3px rgba(0,0,0,.1); }
    h1 { font-size: 1.1rem; margin: 0 0 1.25rem; }
    input, button { width: 100%; padding: .6rem; font-size: 1rem;
                    border-radius: 6px; box-sizing: border-box; }
    input { border: 1px solid #d4d4d8; margin-bottom: .75rem; }
    button { border: 0; background: #18181b; color: #fff; cursor: pointer; }
    .error { background: #fef2f2; color: #991b1b; padding: .6rem;
             border-radius: 6px; margin-bottom: 1rem; font-size: .9rem; }
  </style>
</head>
<body>
  <form method="post" action="/login">
    <h1>Lista de contactos</h1>
    {% for mensaje in get_flashed_messages() %}
      <p class="error">{{ mensaje }}</p>
    {% endfor %}
    <input type="password" name="clave" placeholder="Contraseña" autofocus required>
    <button type="submit">Entrar</button>
  </form>
</body>
</html>
```

Crear `src/plantillas_html/subir.html`:

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lista de contactos</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #f4f4f5; margin: 0;
           padding: 2rem 1rem; }
    main { max-width: 34rem; margin: 0 auto; }
    section { background: #fff; padding: 1.5rem; border-radius: 8px;
              margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
    h1 { font-size: 1.2rem; margin: 0 0 1.5rem; }
    h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .05em;
         color: #71717a; margin: 0 0 .75rem; }
    input, button { font-size: 1rem; padding: .6rem; border-radius: 6px; }
    button { border: 0; background: #18181b; color: #fff; cursor: pointer; }
    .aviso { padding: .75rem; border-radius: 6px; margin-bottom: 1rem;
             font-size: .9rem; }
    .ok { background: #f0fdf4; color: #166534; }
    .error { background: #fef2f2; color: #991b1b; }
    .salir { float: right; font-size: .85rem; }
    table { width: 100%; border-collapse: collapse; font-size: .9rem; }
    td { padding: .3rem 0; }
    td:last-child { text-align: right; color: #71717a; }
  </style>
</head>
<body>
<main>
  <h1>Lista de contactos
    <form method="post" action="/salir" class="salir">
      <button type="submit" style="background:#e4e4e7;color:#3f3f46">Salir</button>
    </form>
  </h1>

  {% for categoria, mensaje in get_flashed_messages(with_categories=true) %}
    <p class="aviso {{ categoria }}">{{ mensaje }}</p>
  {% endfor %}

  <section>
    <h2>Archivo vigente</h2>
    {% if estado.existe %}
      <table>
        <tr><td>Contactos válidos</td><td>{{ estado.validos }}</td></tr>
        <tr><td>Descartados</td><td>{{ estado.descartados }}</td></tr>
        <tr><td>Última subida</td><td>{{ estado.fecha }}</td></tr>
      </table>
    {% else %}
      <p>Todavía no hay ninguna lista cargada.</p>
    {% endif %}
  </section>

  <section>
    <h2>Subir una lista nueva</h2>
    <form method="post" action="/subir" enctype="multipart/form-data">
      <input type="file" name="archivo" accept=".xlsx" required>
      <button type="submit">Subir</button>
    </form>
    <p style="font-size:.85rem;color:#71717a;margin-bottom:0">
      Formato .xlsx, máximo 10 MB, con las columnas <b>Nombre</b> y <b>Teléfono</b>.
      Si el archivo no sirve, la lista actual se conserva.
    </p>
  </section>
</main>
</body>
</html>
```

- [ ] **Step 4: Implementar la app**

Crear `src/panel.py`:

```python
"""Panel web para subir la lista de contactos.

Solo sube. No envia mensajes, no muestra telefonos y no recibe el token de
WhatsApp: si alguien entra, no se lleva la lista ni puede gastar dinero.
"""

import os
from datetime import datetime, timezone

from flask import (
    Flask, flash, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash

from src.contactos import leer_contactos
from src.intentos import ControlIntentos
from src.subida import ArchivoRechazado, ListaInvalida, guardar_lista, validar_archivo

CARPETA_PLANTILLAS = os.path.join(os.path.dirname(__file__), "plantillas_html")


def crear_app(config=None):
    """Fabrica de la app. Recibe la configuracion para poder probarla aislada."""
    app = Flask(__name__, template_folder=CARPETA_PLANTILLAS)

    ajustes = {
        "PANEL_PASSWORD_HASH": os.environ.get("PANEL_PASSWORD_HASH", ""),
        "PANEL_SECRET_KEY": os.environ.get("PANEL_SECRET_KEY", ""),
        "PANEL_DESTINO": os.environ.get("PANEL_DESTINO", "/datos/entrada/contactos.xlsx"),
        "PANEL_COOKIE_SEGURA": os.environ.get("PANEL_COOKIE_SEGURA", "1") == "1",
    }
    ajustes.update(config or {})

    app.config.update(
        SECRET_KEY=ajustes["PANEL_SECRET_KEY"],
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=ajustes["PANEL_COOKIE_SEGURA"],
        MAX_CONTENT_LENGTH=11 * 1024 * 1024,   # algo por encima del limite real,
                                               # para dar un mensaje propio
        PANEL_PASSWORD_HASH=ajustes["PANEL_PASSWORD_HASH"],
        PANEL_DESTINO=ajustes["PANEL_DESTINO"],
    )

    control = ControlIntentos()

    def hay_sesion():
        return session.get("dentro") is True

    @app.get("/login")
    def mostrar_login():
        return render_template("login.html")

    @app.post("/login")
    def entrar():
        espera = control.segundos_de_espera()
        if espera:
            flash(f"Demasiados intentos. Espera {espera} segundos.")
            return redirect(url_for("mostrar_login"))

        if check_password_hash(app.config["PANEL_PASSWORD_HASH"],
                               request.form.get("clave", "")):
            control.registrar_acierto()
            session["dentro"] = True
            return redirect(url_for("portada"))

        control.registrar_fallo()
        flash("Contraseña incorrecta")
        return redirect(url_for("mostrar_login"))

    @app.post("/salir")
    def salir():
        session.clear()
        return redirect(url_for("mostrar_login"))

    @app.get("/")
    def portada():
        if not hay_sesion():
            return redirect(url_for("mostrar_login"))
        return render_template("subir.html", estado=_estado(app.config["PANEL_DESTINO"]))

    @app.post("/subir")
    def subir():
        if not hay_sesion():
            return redirect(url_for("mostrar_login"))

        archivo = request.files.get("archivo")
        nombre = archivo.filename if archivo else ""
        contenido = archivo.read() if archivo else b""

        try:
            validar_archivo(nombre, contenido)
            resumen = guardar_lista(contenido, app.config["PANEL_DESTINO"])
        except (ArchivoRechazado, ListaInvalida) as error:
            flash(str(error), "error")
            return redirect(url_for("portada"))

        detalle = ", ".join(f"{m}: {n}" for m, n in resumen.motivos.items())
        mensaje = f"Lista actualizada: {resumen.validos} contactos válidos"
        if resumen.descartados:
            mensaje += f", {resumen.descartados} descartados ({detalle})"
        flash(mensaje, "ok")
        return redirect(url_for("portada"))

    @app.errorhandler(413)
    def demasiado_grande(_error):
        flash("El archivo pesa más de 10 MB.", "error")
        return redirect(url_for("portada")), 302

    return app


def _estado(destino):
    """Que lista hay cargada ahora mismo, para mostrarla en la pagina."""
    if not os.path.exists(destino):
        return {"existe": False}

    momento = datetime.fromtimestamp(os.path.getmtime(destino), timezone.utc)
    try:
        validos, descartes = leer_contactos(destino)
    except Exception:
        return {"existe": True, "validos": "?", "descartados": "?",
                "fecha": momento.astimezone().strftime("%Y-%m-%d %H:%M")}

    return {
        "existe": True,
        "validos": len(validos),
        "descartados": len(descartes),
        "fecha": momento.astimezone().strftime("%Y-%m-%d %H:%M"),
    }
```

- [ ] **Step 5: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_panel.py -q`
Expected: PASS — 8 passed

- [ ] **Step 6: Commit**

```bash
git add src/panel.py src/plantillas_html/ tests/test_panel.py
git commit -m "feat: panel web con login para subir la lista"
```

---

## Task 6: Pruebas de la subida por HTTP

**Files:**
- Modify: `tests/test_panel.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_panel.py`:

```python
import os


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
```

- [ ] **Step 2: Correr las pruebas**

Run: `python -m pytest tests/test_panel.py -q`
Expected: PASS — 14 passed

Estas pruebas no necesitan código nuevo: verifican el comportamiento que ya
implementaste en la Task 5. Si alguna falla, el fallo es real.

- [ ] **Step 3: Correr toda la suite**

Run: `python -m pytest -q`
Expected: PASS — 139 passed

- [ ] **Step 4: Commit**

```bash
git add tests/test_panel.py
git commit -m "test: cubrir la subida por HTTP de punta a punta"
```

---

## Task 7: El servicio en Docker

**Files:**
- Modify: `docker-compose.yaml`, `Dockerfile`, `README.md`, `DESPLIEGUE.md`

- [ ] **Step 1: Copiar las plantillas en la imagen**

En `Dockerfile`, la línea que copia `src/` ya incluye `src/plantillas_html/`.
Verifícalo después de construir:

```bash
docker compose build
docker compose run --rm panel ls /app/src/plantillas_html
```

Expected: `login.html  subir.html`

- [ ] **Step 2: Añadir el servicio al compose**

`docker-compose.yaml` queda así:

```yaml
services:
  enviador:
    build: .
    container_name: send-whatsapp
    restart: unless-stopped
    environment:
      TZ: America/Bogota
      WHATSAPP_TOKEN: ${WHATSAPP_TOKEN}
      WHATSAPP_PHONE_NUMBER_ID: ${WHATSAPP_PHONE_NUMBER_ID}
      WHATSAPP_WABA_ID: ${WHATSAPP_WABA_ID}
      GRAPH_API_VERSION: ${GRAPH_API_VERSION:-v21.0}
    volumes:
      - datos:/datos

  # Sube la lista y nada mas. Fijate en lo que NO tiene: ni WHATSAPP_TOKEN ni
  # PHONE_NUMBER_ID. Aunque alguien entre, no puede enviar mensajes.
  panel:
    build: .
    container_name: send-whatsapp-panel
    restart: unless-stopped
    command: >
      gunicorn --bind 0.0.0.0:8000 --workers 1 --timeout 120
      "src.panel:crear_app()"
    environment:
      TZ: America/Bogota
      PANEL_PASSWORD_HASH: ${PANEL_PASSWORD_HASH}
      PANEL_SECRET_KEY: ${PANEL_SECRET_KEY}
      PANEL_DESTINO: /datos/entrada/contactos.xlsx
    ports:
      - "8000"
    volumes:
      - datos:/datos

volumes:
  datos:
```

- [ ] **Step 3: Añadir gunicorn**

El servidor de desarrollo de Flask no debe exponerse a internet. `requirements.txt`:

```
openpyxl==3.1.5
requests==2.31.0
python-dotenv==1.0.0
flask==3.1.2
gunicorn==23.0.0
pytest==8.3.4
```

Run: `pip install -r requirements.txt`
Expected: instala `gunicorn`

- [ ] **Step 4: Documentar cómo generar los secretos**

Agregar a `DESPLIEGUE.md`, antes de la sección "Actualizar el código más adelante":

````markdown
## El panel de subida

El servicio `panel` sirve una página web para actualizar la lista sin `scp`.

### Generar los secretos

En tu máquina, con el entorno del proyecto:

```bash
python -c "from werkzeug.security import generate_password_hash as h; print(h('LA-CONTRASENA-QUE-QUIERAS'))"
python -c "import secrets; print(secrets.token_hex(32))"
```

El primero es `PANEL_PASSWORD_HASH`, el segundo `PANEL_SECRET_KEY`. Añádelos
como variables de entorno del recurso en Coolify.

⚠️ **La contraseña en claro no se guarda en ningún sitio.** Solo el hash viaja
al servidor; si la olvidas, generas otro hash.

### Exponerlo

A diferencia del `enviador`, el panel **sí** necesita dominio y HTTPS:
Coolify → servicio `panel` → **Domains → Generate Domain**.

Sin HTTPS la contraseña viaja en claro y la cookie de sesión (marcada como
`Secure`) no se envía, así que no podrás entrar.

### Qué puede y qué no

| Puede | No puede |
|-------|----------|
| Subir un `.xlsx` y validarlo | Enviar mensajes |
| Mostrar cuántos contactos hay | Ver o descargar teléfonos |
| Rechazar un archivo malo sin tocar el anterior | Editar la campaña |

Sus variables de entorno no incluyen `WHATSAPP_TOKEN`. Aunque alguien entre al
panel, no puede gastar dinero ni llevarse la lista.
````

- [ ] **Step 5: Enlazarlo desde el README**

En `README.md`, después de la sección "Uso", agregar:

```markdown
## Panel para subir la lista

Si el proyecto está desplegado en un servidor, hay una página web con
contraseña para actualizar el Excel sin usar `scp`. Ver
[DESPLIEGUE.md](DESPLIEGUE.md#el-panel-de-subida).
```

- [ ] **Step 6: Correr toda la suite**

Run: `python -m pytest -q`
Expected: PASS — 139 passed

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yaml requirements.txt README.md DESPLIEGUE.md
git commit -m "feat: servicio panel en docker-compose, servido con gunicorn"
```

---

## Task 8: Prueba manual en local

**Files:** ninguno

- [ ] **Step 1: Generar unos secretos de prueba**

```bash
python -c "from werkzeug.security import generate_password_hash as h; print(h('prueba123'))"
```

- [ ] **Step 2: Levantar el panel**

```bash
set PANEL_PASSWORD_HASH=<el hash del paso anterior>
set PANEL_SECRET_KEY=cualquier-cosa-para-probar
set PANEL_DESTINO=logs/prueba-panel.xlsx
set PANEL_COOKIE_SEGURA=0
python -c "from src.panel import crear_app; crear_app().run(port=8000, debug=False)"
```

`PANEL_COOKIE_SEGURA=0` es imprescindible en local: sin HTTPS, una cookie
marcada como `Secure` no se envía y no podrías entrar.

- [ ] **Step 3: Probarlo en el navegador**

Abre `http://localhost:8000` y comprueba, en este orden:

1. Redirige al login
2. Una contraseña incorrecta muestra "Contraseña incorrecta"
3. `prueba123` entra
4. Sube `contactos_validos_todos_los_paises.xlsx` → debe decir
   **"1003 contactos válidos, 21 descartados (largo_invalido: 21)"**
5. Sube cualquier `.txt` renombrado a `.xlsx` → lo rechaza y la lista anterior sigue
6. "Salir" cierra la sesión

- [ ] **Step 4: Limpiar**

```bash
del logs\prueba-panel.xlsx
```

---

## Self-review

**Cobertura del spec:**

| Requisito del spec | Task |
|--------------------|------|
| Servicio separado del enviador | 7 |
| Contraseña como hash en variable de entorno | 5, 7 |
| Cookie HttpOnly + Secure + SameSite | 5 |
| Espera creciente tras 3 fallos | 2, 5 |
| Solo `.xlsx`, máx 10 MB, se verifican los bytes | 3 |
| Nombre de destino fijo | 4, 6 |
| El panel no descarga ni muestra teléfonos | 5 (no hay ruta que lo permita) |
| `SECRET_KEY` desde variable de entorno | 5, 7 |
| Validar antes de reemplazar | 4 |
| Mostrar el estado del archivo vigente | 5 |
| Mensajes de error concretos | 3, 4, 5 |
| El panel no recibe `WHATSAPP_TOKEN` | 7 |
| Pruebas con el cliente de Flask | 5, 6 |
| HTTPS y dominio en Coolify | 7 |

**Un añadido sobre el spec:** el spec no mencionaba servidor de aplicaciones.
La Task 7 añade `gunicorn` porque el servidor de desarrollo de Flask no debe
exponerse a internet — lo advierte el propio Flask al arrancar.

**Consistencia de tipos:** `ControlIntentos(maximo, espera_base, espera_maxima,
ahora)` con `registrar_fallo()`, `registrar_acierto()` y `segundos_de_espera()`
se usa igual en Tasks 2 y 5. `validar_archivo(nombre, contenido)` y
`guardar_lista(contenido, destino) -> Resumen(validos, descartados, motivos)`
coinciden entre Tasks 3, 4, 5 y 6. Las claves de configuración
(`PANEL_PASSWORD_HASH`, `PANEL_SECRET_KEY`, `PANEL_DESTINO`,
`PANEL_COOKIE_SEGURA`) son las mismas en Tasks 5, 7 y 8.
