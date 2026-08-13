# Envío masivo de WhatsApp desde Excel — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un script CLI en Python que lee contactos de un Excel, los limpia, y les envía una plantilla aprobada de WhatsApp vía la Cloud API de Meta a un ritmo controlado, sin duplicar envíos si se interrumpe.

**Architecture:** Cuatro módulos con una responsabilidad cada uno bajo `src/`: `config.py` (carga y valida configuración), `contactos.py` (Excel → contactos limpios + descartes), `whatsapp.py` (payload + llamada HTTP), `registro.py` (log CSV e idempotencia). El orquestador `enviar.py` vive en la raíz y es el único punto de entrada. `whatsapp.py` no sabe qué es un Excel; `contactos.py` no sabe qué es WhatsApp.

**Tech Stack:** Python 3.13, `openpyxl` (Excel), `requests` (HTTP), `python-dotenv` (secretos), `pytest` (pruebas). Todo ya instalado.

**Repositorio público:** nunca se commitea `.env`, `DATOS-META.md`, `*.xlsx`, `*.csv` ni `logs/`. Ya verificado con `git check-ignore`.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---------|-----------------|
| `conftest.py` | Vacío. Hace que pytest ponga la raíz en `sys.path`. |
| `requirements.txt` | Dependencias fijadas. |
| `README.md` | Cómo usarlo. Sin valores reales. |
| `campana.example.json` | Configuración de ejemplo (sí se commitea). |
| `campana.json` | Configuración real (ignorada por git). |
| `src/__init__.py` | Marca el paquete. |
| `src/contactos.py` | `normalizar_telefono`, `normalizar_nombre`, `leer_contactos`. Nada de red. |
| `src/config.py` | Dataclasses de configuración + `cargar_config`. Falla temprano y claro. |
| `src/whatsapp.py` | `construir_payload`, `enviar_mensaje`, `enviar_con_reintentos`. Nada de Excel. |
| `src/registro.py` | `Registro`: escribe el CSV fila por fila y dice qué teléfonos ya se enviaron. |
| `enviar.py` | CLI: argparse, orquestación, ritmo, reporte final. |
| `tests/test_contactos.py` | Casos tomados de la basura real del Excel. |
| `tests/test_config.py` | Validación de configuración. |
| `tests/test_whatsapp.py` | Forma del payload y manejo de respuestas, sin red. |
| `tests/test_registro.py` | Idempotencia y escritura incremental. |

---

## Task 1: Andamiaje del proyecto

**Files:**
- Create: `conftest.py`, `requirements.txt`, `src/__init__.py`, `tests/__init__.py`, `README.md`

- [ ] **Step 1: Crear el árbol de carpetas y archivos vacíos**

```bash
mkdir -p src tests logs
```

Crear `conftest.py` con este contenido exacto (un comentario, nada más — su sola
presencia hace que pytest agregue la raíz del proyecto a `sys.path`, que es lo
que permite `from src.contactos import ...` en las pruebas):

```python
# Presente para que pytest agregue la raiz del proyecto a sys.path.
```

Crear `src/__init__.py` vacío y `tests/__init__.py` vacío.

- [ ] **Step 2: Escribir `requirements.txt`**

```
openpyxl==3.1.5
requests==2.31.0
python-dotenv==1.0.0
pytest==8.3.4
```

- [ ] **Step 3: Verificar que pytest arranca**

Run: `python -m pytest -q`
Expected: `no tests ran` (sin errores de importación ni de colección)

- [ ] **Step 4: Escribir `README.md`**

````markdown
# send-whatsapp

Envío masivo de plantillas de WhatsApp desde un Excel, usando la Cloud API
oficial de Meta.

## Requisitos

- Python 3.11+
- Una cuenta de WhatsApp Business (WABA) con un número en estado `CONNECTED`
- Al menos una plantilla aprobada por Meta

## Instalación

```bash
pip install -r requirements.txt
cp .env.example .env          # y llenar los valores
cp campana.example.json campana.json
```

## Uso

```bash
python enviar.py --dry-run                  # simula, no envia nada
python enviar.py --solo 57XXXXXXXXXX        # un solo numero, para probar
python enviar.py --limite 5                 # solo los primeros 5
python enviar.py                            # corrida completa
```

## Importante

- Solo se pueden enviar **plantillas aprobadas** por Meta. La API no permite
  texto libre para iniciar una conversación.
- Cada destinatario debe haber dado su consentimiento (opt-in). Enviar a listas
  compradas hace que Meta baje la calidad del número y termine bloqueándolo.
- Cada conversación de marketing **se cobra**.
- Un número nuevo arranca limitado a 1.000 conversaciones únicas cada 24 horas.

## Qué nunca se sube a git

`.env`, `DATOS-META.md`, cualquier `.xlsx`/`.csv` y la carpeta `logs/`.
Los Excel contienen datos personales sujetos a habeas data (Ley 1581).
````

- [ ] **Step 5: Commit**

```bash
git add conftest.py requirements.txt src/__init__.py tests/__init__.py README.md .gitignore .env.example
git commit -m "chore: andamiaje del proyecto"
```

---

## Task 2: Normalizar teléfonos

**Files:**
- Create: `src/contactos.py`
- Test: `tests/test_contactos.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_contactos.py`:

```python
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
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_contactos.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.contactos'`

- [ ] **Step 3: Implementar lo mínimo**

Crear `src/contactos.py`:

```python
"""Lectura y limpieza de contactos desde Excel. No sabe nada de WhatsApp."""

import re

# Motivos de descarte
VACIO = "vacio"
BASURA = "basura"
NO_ES_MOVIL_CO = "no_es_movil_co"
DUPLICADO = "duplicado"


def normalizar_telefono(valor):
    """Convierte una celda de Excel en un movil colombiano en formato E.164 sin '+'.

    Devuelve (telefono, motivo). Si telefono es None, motivo explica por que se
    descarto. Si telefono tiene valor, motivo es "".

    Acepta str o int: en un Excel la misma columna puede venir de las dos formas.
    """
    if valor is None:
        return None, VACIO

    texto = str(valor).strip()
    if not texto:
        return None, VACIO

    digitos = re.sub(r"\D", "", texto)

    # Ni un solo digito, o largos imposibles para un telefono.
    if not digitos or len(digitos) < 7 or len(digitos) > 13:
        return None, BASURA

    # Movil colombiano sin indicativo: 10 digitos que empiezan en 3.
    if len(digitos) == 10 and digitos.startswith("3"):
        return "57" + digitos, ""

    # Movil colombiano con indicativo: 57 + 10 digitos que empiezan en 3.
    if len(digitos) == 12 and digitos.startswith("57") and digitos[2] == "3":
        return digitos, ""

    return None, NO_ES_MOVIL_CO
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_contactos.py -q`
Expected: PASS — 16 passed

- [ ] **Step 5: Commit**

```bash
git add src/contactos.py tests/test_contactos.py
git commit -m "feat: normalizar telefonos a moviles colombianos E.164"
```

---

## Task 3: Normalizar nombres

**Files:**
- Modify: `src/contactos.py`
- Test: `tests/test_contactos.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_contactos.py`:

```python
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
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_contactos.py -q`
Expected: FAIL — `ImportError: cannot import name 'normalizar_nombre'`

- [ ] **Step 3: Implementar lo mínimo**

Agregar a `src/contactos.py`, después de `normalizar_telefono`:

```python
# Restos tipicos de un export mal hecho (pandas escribe "nan" cuando la celda
# estaba vacia). Si no los quitamos, el mensaje dice "Hola, Andrea nan.".
BASURA_EN_NOMBRES = {"nan", "none", "null", "na", "-", "--", "."}


def normalizar_nombre(valor, por_defecto="Hola"):
    """Devuelve el primer nombre, capitalizado y sin residuos de export.

    "ANGELA SANCHEZ"  -> "Angela"
    "Andrea nan"      -> "Andrea"
    ""                -> por_defecto
    """
    if valor is None:
        return por_defecto

    texto = str(valor).strip()
    if not texto:
        return por_defecto

    palabras = [p for p in texto.split() if p.lower() not in BASURA_EN_NOMBRES]
    if not palabras:
        return por_defecto

    primero = palabras[0]
    # Un "nombre" sin ninguna letra no sirve para saludar a nadie.
    if not any(c.isalpha() for c in primero):
        return por_defecto

    return primero.capitalize()
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_contactos.py -q`
Expected: PASS — 27 passed

- [ ] **Step 5: Commit**

```bash
git add src/contactos.py tests/test_contactos.py
git commit -m "feat: normalizar nombres a primer nombre capitalizado"
```

---

## Task 4: Leer contactos del Excel

**Files:**
- Modify: `src/contactos.py`
- Test: `tests/test_contactos.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_contactos.py`:

```python
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
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_contactos.py -q`
Expected: FAIL — `ImportError: cannot import name 'Contacto'`

- [ ] **Step 3: Implementar lo mínimo**

Agregar al inicio de `src/contactos.py`, junto a los imports:

```python
from dataclasses import dataclass, field
```

Y agregar al final del archivo:

```python
@dataclass(frozen=True)
class Contacto:
    """Un destinatario listo para enviar."""

    nombre: str                  # primer nombre capitalizado, ej "Ana"
    telefono: str                # E.164 sin '+', ej "573001234567"
    fila: int                    # numero de fila en el Excel, para reportes
    crudo: dict = field(default_factory=dict)   # la fila original por nombre de columna


@dataclass(frozen=True)
class Descarte:
    """Una fila que no se puede usar, y por que."""

    fila: int
    nombre_crudo: str
    telefono_crudo: str
    motivo: str


def leer_contactos(
    ruta,
    hoja=None,
    columna_nombre="Nombre",
    columna_telefono="Teléfono",
    nombre_por_defecto="Hola",
):
    """Lee un .xlsx y devuelve (validos, descartes).

    Nunca lanza excepcion por una fila mala: la manda a descartes con su motivo.
    Solo falla si el archivo no existe o si faltan las columnas pedidas.
    """
    from openpyxl import load_workbook

    libro = load_workbook(ruta, read_only=True, data_only=True)
    try:
        pagina = libro[hoja] if hoja else libro.worksheets[0]
        filas = pagina.iter_rows(values_only=True)

        try:
            encabezados = [str(c).strip() if c is not None else "" for c in next(filas)]
        except StopIteration:
            return [], []

        for requerida in (columna_nombre, columna_telefono):
            if requerida not in encabezados:
                raise ValueError(
                    f"El Excel no tiene la columna '{requerida}'. "
                    f"Columnas encontradas: {encabezados}"
                )

        indice_nombre = encabezados.index(columna_nombre)
        indice_telefono = encabezados.index(columna_telefono)

        validos = []
        descartes = []
        ya_vistos = set()

        for numero_fila, fila in enumerate(filas, start=2):
            if not any(c is not None and str(c).strip() for c in fila):
                continue  # fila completamente vacia: ni siquiera es un descarte

            nombre_crudo = fila[indice_nombre] if indice_nombre < len(fila) else None
            telefono_crudo = fila[indice_telefono] if indice_telefono < len(fila) else None

            telefono, motivo = normalizar_telefono(telefono_crudo)
            if telefono is None:
                descartes.append(Descarte(
                    fila=numero_fila,
                    nombre_crudo=_texto(nombre_crudo),
                    telefono_crudo=_texto(telefono_crudo),
                    motivo=motivo,
                ))
                continue

            if telefono in ya_vistos:
                descartes.append(Descarte(
                    fila=numero_fila,
                    nombre_crudo=_texto(nombre_crudo),
                    telefono_crudo=_texto(telefono_crudo),
                    motivo=DUPLICADO,
                ))
                continue

            ya_vistos.add(telefono)
            validos.append(Contacto(
                nombre=normalizar_nombre(nombre_crudo, nombre_por_defecto),
                telefono=telefono,
                fila=numero_fila,
                crudo={
                    encabezado: fila[i] if i < len(fila) else None
                    for i, encabezado in enumerate(encabezados)
                    if encabezado
                },
            ))

        return validos, descartes
    finally:
        libro.close()


def _texto(valor):
    return "" if valor is None else str(valor).strip()
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_contactos.py -q`
Expected: PASS — 33 passed

- [ ] **Step 5: Probar contra el Excel real (sin enviar nada)**

Run:

```bash
python -c "from src.contactos import leer_contactos; v,d = leer_contactos('Libro_Consolidado_Final.xlsx'); print(len(v),'validos /',len(d),'descartes')"
```

Expected: `820 validos / 720 descartes`

- [ ] **Step 6: Commit**

```bash
git add src/contactos.py tests/test_contactos.py
git commit -m "feat: leer contactos del Excel con deduplicacion y reporte de descartes"
```

---

## Task 5: Configuración

**Files:**
- Create: `src/config.py`, `campana.example.json`
- Test: `tests/test_config.py`

- [ ] **Step 1: Escribir `campana.example.json`**

```json
{
  "excel": {
    "ruta": "prueba.xlsx",
    "hoja": null,
    "columna_nombre": "Nombre",
    "columna_telefono": "Teléfono"
  },
  "plantilla": {
    "nombre": "bonos_popsy_v7",
    "idioma": "es",
    "parametros_cuerpo": [
      { "origen": "nombre_normalizado" }
    ],
    "imagen_cabecera": null,
    "parametro_boton_url": { "origen": "fijo", "valor": "PRUEBA123" }
  },
  "envio": {
    "segundos_entre_mensajes": 5,
    "jitter": 0.2,
    "tope_diario": 900,
    "nombre_por_defecto": "Hola",
    "ruta_log": "logs/envios.csv"
  }
}
```

- [ ] **Step 2: Escribir las pruebas que fallan**

Crear `tests/test_config.py`:

```python
import json

import pytest

from src.config import ConfigInvalida, cargar_config

ENTORNO_COMPLETO = {
    "WHATSAPP_TOKEN": "EAAtoken",
    "WHATSAPP_PHONE_NUMBER_ID": "111222333",
    "GRAPH_API_VERSION": "v21.0",
}

CAMPANA_MINIMA = {
    "excel": {"ruta": "prueba.xlsx"},
    "plantilla": {"nombre": "bonos_popsy_v7", "idioma": "es"},
}


def _escribir(tmp_path, datos, nombre="campana.json"):
    ruta = tmp_path / nombre
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return str(ruta)


def test_carga_una_campana_minima_y_rellena_los_valores_por_defecto(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {"excel": {"ruta": str(tmp_path / "prueba.xlsx")},
             "plantilla": {"nombre": "bonos_popsy_v7", "idioma": "es"}}

    config = cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert config.meta.token == "EAAtoken"
    assert config.meta.phone_number_id == "111222333"
    assert config.plantilla.nombre == "bonos_popsy_v7"
    assert config.envio.segundos_entre_mensajes == 1.5     # valor por defecto
    assert config.envio.tope_diario == 900                 # valor por defecto
    assert config.excel.columna_nombre == "Nombre"         # valor por defecto


def test_falla_claro_si_falta_el_token(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {"excel": {"ruta": str(tmp_path / "prueba.xlsx")},
             "plantilla": {"nombre": "x", "idioma": "es"}}

    with pytest.raises(ConfigInvalida) as error:
        cargar_config(_escribir(tmp_path, datos), {"WHATSAPP_PHONE_NUMBER_ID": "1"})

    assert "WHATSAPP_TOKEN" in str(error.value)


def test_falla_claro_si_el_excel_no_existe(tmp_path):
    datos = {"excel": {"ruta": str(tmp_path / "no-existe.xlsx")},
             "plantilla": {"nombre": "x", "idioma": "es"}}

    with pytest.raises(ConfigInvalida) as error:
        cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert "no-existe.xlsx" in str(error.value)


def test_falla_claro_si_la_plantilla_no_tiene_idioma(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {"excel": {"ruta": str(tmp_path / "prueba.xlsx")},
             "plantilla": {"nombre": "x"}}

    with pytest.raises(ConfigInvalida) as error:
        cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert "idioma" in str(error.value)


def test_falla_claro_si_un_parametro_tiene_un_origen_desconocido(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {
        "excel": {"ruta": str(tmp_path / "prueba.xlsx")},
        "plantilla": {"nombre": "x", "idioma": "es",
                      "parametros_cuerpo": [{"origen": "inventado"}]},
    }

    with pytest.raises(ConfigInvalida) as error:
        cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert "inventado" in str(error.value)


def test_falla_claro_si_un_parametro_de_columna_no_dice_cual(tmp_path):
    (tmp_path / "prueba.xlsx").write_bytes(b"")
    datos = {
        "excel": {"ruta": str(tmp_path / "prueba.xlsx")},
        "plantilla": {"nombre": "x", "idioma": "es",
                      "parametros_cuerpo": [{"origen": "columna"}]},
    }

    with pytest.raises(ConfigInvalida) as error:
        cargar_config(_escribir(tmp_path, datos), ENTORNO_COMPLETO)

    assert "columna" in str(error.value)
```

- [ ] **Step 3: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 4: Implementar lo mínimo**

Crear `src/config.py`:

```python
"""Carga y valida la configuracion. Falla temprano y con un mensaje util."""

import json
import os
from dataclasses import dataclass, field

ORIGENES_VALIDOS = ("nombre_normalizado", "columna", "fijo")


class ConfigInvalida(Exception):
    """La configuracion esta incompleta o mal formada."""


@dataclass(frozen=True)
class ConfigMeta:
    token: str
    phone_number_id: str
    version_api: str = "v21.0"


@dataclass(frozen=True)
class ConfigExcel:
    ruta: str
    hoja: str = None
    columna_nombre: str = "Nombre"
    columna_telefono: str = "Teléfono"


@dataclass(frozen=True)
class Parametro:
    """De donde sale el valor de una variable de la plantilla."""

    origen: str           # "nombre_normalizado" | "columna" | "fijo"
    nombre: str = ""      # nombre de la columna, si origen == "columna"
    valor: str = ""       # texto literal, si origen == "fijo"


@dataclass(frozen=True)
class ConfigPlantilla:
    nombre: str
    idioma: str
    parametros_cuerpo: list = field(default_factory=list)
    imagen_cabecera: str = None            # URL publica de la imagen, o None
    parametro_boton_url: Parametro = None  # solo si la plantilla lo pide


@dataclass(frozen=True)
class ConfigEnvio:
    segundos_entre_mensajes: float = 1.5
    jitter: float = 0.2
    tope_diario: int = 900
    nombre_por_defecto: str = "Hola"
    ruta_log: str = "logs/envios.csv"


@dataclass(frozen=True)
class Config:
    meta: ConfigMeta
    excel: ConfigExcel
    plantilla: ConfigPlantilla
    envio: ConfigEnvio


def cargar_config(ruta_campana, entorno):
    """Lee el JSON de campana y las variables de entorno. Devuelve un Config.

    `entorno` es un diccionario (normalmente os.environ) para poder probarlo sin
    tocar el sistema.
    """
    meta = _leer_meta(entorno)

    try:
        with open(ruta_campana, encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except FileNotFoundError:
        raise ConfigInvalida(f"No encuentro el archivo de campana: {ruta_campana}")
    except json.JSONDecodeError as error:
        raise ConfigInvalida(f"El JSON de campana esta mal formado: {error}")

    return Config(
        meta=meta,
        excel=_leer_excel(datos.get("excel", {})),
        plantilla=_leer_plantilla(datos.get("plantilla", {})),
        envio=_leer_envio(datos.get("envio", {})),
    )


def _leer_meta(entorno):
    token = (entorno.get("WHATSAPP_TOKEN") or "").strip()
    if not token:
        raise ConfigInvalida(
            "Falta WHATSAPP_TOKEN en el .env. "
            "Se genera en Business Settings > Usuarios del sistema > Generar token."
        )

    phone_number_id = (entorno.get("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
    if not phone_number_id:
        raise ConfigInvalida(
            "Falta WHATSAPP_PHONE_NUMBER_ID en el .env. "
            "Es el ID interno de Meta, no el numero telefonico."
        )

    return ConfigMeta(
        token=token,
        phone_number_id=phone_number_id,
        version_api=(entorno.get("GRAPH_API_VERSION") or "v21.0").strip(),
    )


def _leer_excel(datos):
    ruta = (datos.get("ruta") or "").strip()
    if not ruta:
        raise ConfigInvalida("Falta 'excel.ruta' en el archivo de campana.")
    if not os.path.exists(ruta):
        raise ConfigInvalida(f"No encuentro el Excel: {ruta}")

    return ConfigExcel(
        ruta=ruta,
        hoja=datos.get("hoja") or None,
        columna_nombre=datos.get("columna_nombre") or "Nombre",
        columna_telefono=datos.get("columna_telefono") or "Teléfono",
    )


def _leer_plantilla(datos):
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise ConfigInvalida("Falta 'plantilla.nombre' en el archivo de campana.")

    idioma = (datos.get("idioma") or "").strip()
    if not idioma:
        raise ConfigInvalida(
            "Falta 'plantilla.idioma'. Debe coincidir exacto con el de Meta "
            "(por ejemplo 'es' y 'es_CO' no son intercambiables)."
        )

    parametros = [_leer_parametro(p) for p in datos.get("parametros_cuerpo") or []]

    boton = datos.get("parametro_boton_url")
    return ConfigPlantilla(
        nombre=nombre,
        idioma=idioma,
        parametros_cuerpo=parametros,
        imagen_cabecera=datos.get("imagen_cabecera") or None,
        parametro_boton_url=_leer_parametro(boton) if boton else None,
    )


def _leer_parametro(datos):
    origen = (datos.get("origen") or "").strip()
    if origen not in ORIGENES_VALIDOS:
        raise ConfigInvalida(
            f"Origen de parametro desconocido: '{origen}'. "
            f"Los validos son: {', '.join(ORIGENES_VALIDOS)}."
        )

    if origen == "columna" and not (datos.get("nombre") or "").strip():
        raise ConfigInvalida(
            "Un parametro con origen 'columna' necesita el campo 'nombre' "
            "con el nombre exacto de la columna del Excel."
        )

    return Parametro(
        origen=origen,
        nombre=(datos.get("nombre") or "").strip(),
        valor=str(datos.get("valor") or ""),
    )


def _leer_envio(datos):
    predeterminado = ConfigEnvio()
    return ConfigEnvio(
        segundos_entre_mensajes=float(
            datos.get("segundos_entre_mensajes", predeterminado.segundos_entre_mensajes)
        ),
        jitter=float(datos.get("jitter", predeterminado.jitter)),
        tope_diario=int(datos.get("tope_diario", predeterminado.tope_diario)),
        nombre_por_defecto=datos.get("nombre_por_defecto")
        or predeterminado.nombre_por_defecto,
        ruta_log=datos.get("ruta_log") or predeterminado.ruta_log,
    )
```

- [ ] **Step 5: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_config.py -q`
Expected: PASS — 6 passed

- [ ] **Step 6: Commit**

```bash
git add src/config.py tests/test_config.py campana.example.json
git commit -m "feat: cargar y validar configuracion de campana"
```

---

## Task 6: Construir el payload de la plantilla

**Files:**
- Create: `src/whatsapp.py`
- Test: `tests/test_whatsapp.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_whatsapp.py`:

```python
import pytest

from src.config import ConfigPlantilla, Parametro
from src.contactos import Contacto
from src.whatsapp import construir_payload

ANA = Contacto(
    nombre="Ana",
    telefono="573001234567",
    fila=2,
    crudo={"Nombre": "ANA GOMEZ", "Email": "e@x.com", "CuponId": "abc123"},
)


def test_plantilla_sin_variables_no_lleva_componentes():
    plantilla = ConfigPlantilla(nombre="hello_world", idioma="en_US")

    assert construir_payload(ANA, plantilla) == {
        "messaging_product": "whatsapp",
        "to": "573001234567",
        "type": "template",
        "template": {"name": "hello_world", "language": {"code": "en_US"}},
    }


def test_el_nombre_normalizado_entra_como_variable_del_cuerpo():
    plantilla = ConfigPlantilla(
        nombre="bonos_popsy_v7",
        idioma="es",
        parametros_cuerpo=[Parametro(origen="nombre_normalizado")],
    )

    payload = construir_payload(ANA, plantilla)

    assert payload["template"]["components"] == [
        {"type": "body", "parameters": [{"type": "text", "text": "Ana"}]}
    ]


def test_un_parametro_puede_venir_de_una_columna_del_excel():
    plantilla = ConfigPlantilla(
        nombre="x",
        idioma="es",
        parametros_cuerpo=[Parametro(origen="columna", nombre="CuponId")],
    )

    payload = construir_payload(ANA, plantilla)

    assert payload["template"]["components"][0]["parameters"] == [
        {"type": "text", "text": "abc123"}
    ]


def test_un_parametro_puede_ser_un_valor_fijo_igual_para_todos():
    plantilla = ConfigPlantilla(
        nombre="x",
        idioma="es",
        parametros_cuerpo=[Parametro(origen="fijo", valor="PRUEBA123")],
    )

    payload = construir_payload(ANA, plantilla)

    assert payload["template"]["components"][0]["parameters"] == [
        {"type": "text", "text": "PRUEBA123"}
    ]


def test_el_boton_url_va_como_componente_aparte_con_su_indice():
    plantilla = ConfigPlantilla(
        nombre="bonos_popsy_v7",
        idioma="es",
        parametros_cuerpo=[Parametro(origen="nombre_normalizado")],
        parametro_boton_url=Parametro(origen="columna", nombre="CuponId"),
    )

    payload = construir_payload(ANA, plantilla)

    assert payload["template"]["components"][1] == {
        "type": "button",
        "sub_type": "url",
        "index": "0",
        "parameters": [{"type": "text", "text": "abc123"}],
    }


def test_la_imagen_de_cabecera_va_primero():
    plantilla = ConfigPlantilla(
        nombre="dama_week_11_noviembre",
        idioma="es_CO",
        parametros_cuerpo=[Parametro(origen="nombre_normalizado")],
        imagen_cabecera="https://ejemplo.com/banner.jpg",
    )

    componentes = construir_payload(ANA, plantilla)["template"]["components"]

    assert componentes[0] == {
        "type": "header",
        "parameters": [
            {"type": "image", "image": {"link": "https://ejemplo.com/banner.jpg"}}
        ],
    }
    assert componentes[1]["type"] == "body"


def test_una_columna_vacia_no_rompe_el_envio():
    contacto_sin_cupon = Contacto(nombre="Ana", telefono="573001112233", fila=3, crudo={})
    plantilla = ConfigPlantilla(
        nombre="x", idioma="es",
        parametros_cuerpo=[Parametro(origen="columna", nombre="CuponId")],
    )

    payload = construir_payload(contacto_sin_cupon, plantilla)

    assert payload["template"]["components"][0]["parameters"] == [
        {"type": "text", "text": ""}
    ]
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_whatsapp.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.whatsapp'`

- [ ] **Step 3: Implementar lo mínimo**

Crear `src/whatsapp.py`:

```python
"""Cliente de la Cloud API de WhatsApp. No sabe nada de Excel."""


def resolver_parametro(parametro, contacto):
    """Devuelve el texto que va a reemplazar una variable de la plantilla."""
    if parametro.origen == "nombre_normalizado":
        return contacto.nombre
    if parametro.origen == "fijo":
        return parametro.valor
    if parametro.origen == "columna":
        valor = contacto.crudo.get(parametro.nombre)
        return "" if valor is None else str(valor).strip()
    raise ValueError(f"Origen de parametro desconocido: {parametro.origen}")


def construir_payload(contacto, plantilla):
    """Arma el cuerpo JSON de POST /{phone_number_id}/messages."""
    componentes = []

    if plantilla.imagen_cabecera:
        componentes.append({
            "type": "header",
            "parameters": [
                {"type": "image", "image": {"link": plantilla.imagen_cabecera}}
            ],
        })

    if plantilla.parametros_cuerpo:
        componentes.append({
            "type": "body",
            "parameters": [
                {"type": "text", "text": resolver_parametro(p, contacto)}
                for p in plantilla.parametros_cuerpo
            ],
        })

    if plantilla.parametro_boton_url:
        componentes.append({
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [
                {"type": "text",
                 "text": resolver_parametro(plantilla.parametro_boton_url, contacto)}
            ],
        })

    template = {"name": plantilla.nombre, "language": {"code": plantilla.idioma}}
    if componentes:
        template["components"] = componentes

    return {
        "messaging_product": "whatsapp",
        "to": contacto.telefono,
        "type": "template",
        "template": template,
    }
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_whatsapp.py -q`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/whatsapp.py tests/test_whatsapp.py
git commit -m "feat: construir payload de plantilla con cuerpo, imagen y boton"
```

---

## Task 7: Enviar por HTTP con reintentos

**Files:**
- Modify: `src/whatsapp.py`
- Test: `tests/test_whatsapp.py`

**Contexto de la API real.** Éxito devuelve HTTP 200 con
`{"messages": [{"id": "wamid.XXX"}]}`. Un fallo devuelve
`{"error": {"message": "...", "code": 190, "error_subcode": 0}}`.
Códigos que importan:

| Código | Significado | Qué hacer |
|--------|-------------|-----------|
| HTTP 429 | límite de tasa | reintentar |
| HTTP 5xx | error de Meta | reintentar |
| `190` | token inválido o revocado | **abortar todo** |
| `131026` | el destinatario no tiene WhatsApp | registrar y seguir |
| `132xxx` | plantilla mal escrita o parámetros que no cuadran | registrar y seguir |

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_whatsapp.py`:

```python
from src.config import ConfigMeta
from src.whatsapp import TokenInvalido, enviar_con_reintentos, enviar_mensaje

META = ConfigMeta(token="EAAtoken", phone_number_id="111222333", version_api="v21.0")


class RespuestaFalsa:
    def __init__(self, codigo_http, cuerpo):
        self.status_code = codigo_http
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


class SesionFalsa:
    """Sustituye a requests.Session: devuelve respuestas preparadas y guarda las llamadas."""

    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.llamadas.append({"url": url, "json": json, "headers": headers})
        return self._respuestas.pop(0)


def test_un_envio_exitoso_devuelve_el_id_del_mensaje():
    sesion = SesionFalsa([RespuestaFalsa(200, {"messages": [{"id": "wamid.ABC"}]})])

    resultado = enviar_mensaje(sesion, META, {"to": "573001234567"})

    assert resultado.ok is True
    assert resultado.message_id == "wamid.ABC"


def test_arma_bien_la_url_y_la_cabecera_de_autorizacion():
    sesion = SesionFalsa([RespuestaFalsa(200, {"messages": [{"id": "wamid.ABC"}]})])

    enviar_mensaje(sesion, META, {"to": "573001234567"})

    llamada = sesion.llamadas[0]
    assert llamada["url"] == "https://graph.facebook.com/v21.0/111222333/messages"
    assert llamada["headers"]["Authorization"] == "Bearer EAAtoken"


def test_un_destinatario_sin_whatsapp_falla_pero_no_se_reintenta():
    cuerpo = {"error": {"message": "Recipient not found", "code": 131026}}
    sesion = SesionFalsa([RespuestaFalsa(400, cuerpo)])

    resultado = enviar_mensaje(sesion, META, {})

    assert resultado.ok is False
    assert resultado.codigo == "131026"
    assert resultado.reintentable is False


def test_el_limite_de_tasa_si_es_reintentable():
    sesion = SesionFalsa([RespuestaFalsa(429, {"error": {"message": "rate", "code": 4}})])

    resultado = enviar_mensaje(sesion, META, {})

    assert resultado.reintentable is True


def test_reintenta_hasta_que_funciona():
    sesion = SesionFalsa([
        RespuestaFalsa(429, {"error": {"message": "rate", "code": 4}}),
        RespuestaFalsa(200, {"messages": [{"id": "wamid.OK"}]}),
    ])

    resultado = enviar_con_reintentos(sesion, META, {}, intentos=3, espera_inicial=0)

    assert resultado.ok is True
    assert len(sesion.llamadas) == 2


def test_no_reintenta_un_error_permanente():
    cuerpo = {"error": {"message": "template not found", "code": 132001}}
    sesion = SesionFalsa([RespuestaFalsa(400, cuerpo)])

    resultado = enviar_con_reintentos(sesion, META, {}, intentos=3, espera_inicial=0)

    assert resultado.ok is False
    assert len(sesion.llamadas) == 1


def test_un_token_invalido_aborta_todo_el_proceso():
    cuerpo = {"error": {"message": "Invalid OAuth token", "code": 190}}
    sesion = SesionFalsa([RespuestaFalsa(401, cuerpo)])

    with pytest.raises(TokenInvalido):
        enviar_con_reintentos(sesion, META, {}, intentos=3, espera_inicial=0)
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_whatsapp.py -q`
Expected: FAIL — `ImportError: cannot import name 'TokenInvalido'`

- [ ] **Step 3: Implementar lo mínimo**

Agregar al inicio de `src/whatsapp.py`:

```python
import time
from dataclasses import dataclass
```

Y agregar al final de `src/whatsapp.py`:

```python
# El token esta mal o fue revocado: no tiene sentido seguir intentando.
CODIGO_TOKEN_INVALIDO = 190

# Errores de Meta que se resuelven solos si esperamos un poco.
HTTP_REINTENTABLES = (408, 429, 500, 502, 503, 504)


class TokenInvalido(Exception):
    """El token fue rechazado. Hay que abortar la corrida completa."""


@dataclass(frozen=True)
class Resultado:
    ok: bool
    message_id: str = ""
    codigo: str = ""
    mensaje: str = ""
    reintentable: bool = False


def enviar_mensaje(sesion, meta, payload, timeout=30):
    """Hace UN intento. No reintenta, no espera. Devuelve un Resultado."""
    url = f"https://graph.facebook.com/{meta.version_api}/{meta.phone_number_id}/messages"
    cabeceras = {
        "Authorization": f"Bearer {meta.token}",
        "Content-Type": "application/json",
    }

    try:
        respuesta = sesion.post(url, json=payload, headers=cabeceras, timeout=timeout)
    except Exception as error:                      # red caida, DNS, timeout
        return Resultado(ok=False, codigo="red", mensaje=str(error), reintentable=True)

    try:
        cuerpo = respuesta.json()
    except Exception:
        cuerpo = {}

    if respuesta.status_code == 200:
        mensajes = cuerpo.get("messages") or [{}]
        return Resultado(ok=True, message_id=mensajes[0].get("id", ""))

    error = cuerpo.get("error") or {}
    codigo = error.get("code", "")

    if codigo == CODIGO_TOKEN_INVALIDO:
        raise TokenInvalido(error.get("message", "Token rechazado por Meta"))

    return Resultado(
        ok=False,
        codigo=str(codigo) if codigo != "" else str(respuesta.status_code),
        mensaje=error.get("message", "") or f"HTTP {respuesta.status_code}",
        reintentable=respuesta.status_code in HTTP_REINTENTABLES,
    )


def enviar_con_reintentos(sesion, meta, payload, intentos=3, espera_inicial=2, timeout=30):
    """Reintenta con espera creciente, pero solo los errores que valen la pena."""
    espera = espera_inicial
    resultado = None

    for intento in range(intentos):
        resultado = enviar_mensaje(sesion, meta, payload, timeout=timeout)
        if resultado.ok or not resultado.reintentable:
            return resultado
        if intento < intentos - 1:
            time.sleep(espera)
            espera *= 2

    return resultado
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_whatsapp.py -q`
Expected: PASS — 14 passed

- [ ] **Step 5: Commit**

```bash
git add src/whatsapp.py tests/test_whatsapp.py
git commit -m "feat: enviar por HTTP con reintentos y clasificacion de errores"
```

---

## Task 8: Registro e idempotencia

**Files:**
- Create: `src/registro.py`
- Test: `tests/test_registro.py`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_registro.py`:

```python
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
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `python -m pytest tests/test_registro.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.registro'`

- [ ] **Step 3: Implementar lo mínimo**

Crear `src/registro.py`:

```python
"""Log de envios en CSV. Es lo que evita cobrar dos veces al mismo numero."""

import csv
import os
from datetime import datetime, timezone

CAMPOS = [
    "timestamp",
    "telefono",
    "nombre",
    "estado",          # "enviado" | "fallo"
    "message_id",
    "codigo_error",
    "mensaje_error",
]

ENVIADO = "enviado"
FALLO = "fallo"


class Registro:
    """Escribe cada resultado en el momento y sabe a quien ya se le envio.

    Se escribe fila por fila con flush inmediato: si el proceso muere en el
    mensaje 400, los 399 anteriores quedan guardados y no se vuelven a enviar.
    """

    def __init__(self, ruta):
        self.ruta = ruta
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        self._archivo = None
        self._escritor = None

    def telefonos_enviados(self):
        """Los telefonos que ya recibieron el mensaje correctamente."""
        if not os.path.exists(self.ruta):
            return set()

        with open(self.ruta, encoding="utf-8", newline="") as archivo:
            return {
                fila["telefono"]
                for fila in csv.DictReader(archivo)
                if fila.get("estado") == ENVIADO and fila.get("telefono")
            }

    def anotar(self, telefono, nombre, estado, message_id="", codigo_error="",
               mensaje_error=""):
        self._abrir()
        self._escritor.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "telefono": telefono,
            "nombre": nombre,
            "estado": estado,
            "message_id": message_id,
            "codigo_error": codigo_error,
            "mensaje_error": mensaje_error,
        })
        self._archivo.flush()          # sin esto, una caida pierde el buffer

    def cerrar(self):
        if self._archivo:
            self._archivo.close()
            self._archivo = None
            self._escritor = None

    def _abrir(self):
        if self._escritor:
            return
        hay_que_escribir_encabezado = (
            not os.path.exists(self.ruta) or os.path.getsize(self.ruta) == 0
        )
        self._archivo = open(self.ruta, "a", encoding="utf-8", newline="")
        self._escritor = csv.DictWriter(self._archivo, fieldnames=CAMPOS)
        if hay_que_escribir_encabezado:
            self._escritor.writeheader()
            self._archivo.flush()
```

- [ ] **Step 4: Correr las pruebas para verificar que pasan**

Run: `python -m pytest tests/test_registro.py -q`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/registro.py tests/test_registro.py
git commit -m "feat: log de envios en CSV con idempotencia"
```

---

## Task 9: El orquestador CLI

**Files:**
- Create: `enviar.py`

- [ ] **Step 1: Escribir `enviar.py`**

```python
"""Envio masivo de plantillas de WhatsApp desde un Excel.

    python enviar.py --dry-run
    python enviar.py --solo 57XXXXXXXXXX
    python enviar.py --limite 5
    python enviar.py
"""

import argparse
import json
import random
import sys
import time

import requests
from dotenv import dotenv_values

from src.config import ConfigInvalida, cargar_config
from src.contactos import leer_contactos
from src.registro import ENVIADO, FALLO, Registro
from src.whatsapp import TokenInvalido, construir_payload, enviar_con_reintentos


def parsear_argumentos(argv=None):
    parser = argparse.ArgumentParser(description="Envio masivo de plantillas de WhatsApp.")
    parser.add_argument("--config", default="campana.json",
                        help="Archivo de campana (por defecto: campana.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra los payloads y NO envia nada")
    parser.add_argument("--limite", type=int, default=None,
                        help="Envia solo a los primeros N contactos")
    parser.add_argument("--solo", default=None,
                        help="Envia solo a este numero (formato 57XXXXXXXXXX)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parsear_argumentos(argv)

    try:
        entorno = {**dotenv_values(".env")}
        config = cargar_config(args.config, entorno)
    except ConfigInvalida as error:
        print(f"ERROR DE CONFIGURACION: {error}")
        return 1

    try:
        validos, descartes = leer_contactos(
            config.excel.ruta,
            hoja=config.excel.hoja,
            columna_nombre=config.excel.columna_nombre,
            columna_telefono=config.excel.columna_telefono,
            nombre_por_defecto=config.envio.nombre_por_defecto,
        )
    except (ValueError, OSError) as error:
        print(f"ERROR LEYENDO EL EXCEL: {error}")
        return 1

    print(f"Excel: {config.excel.ruta}")
    print(f"  {len(validos)} contactos validos, {len(descartes)} descartados")
    if descartes:
        print("  Motivos:", _contar_motivos(descartes))

    registro = Registro(config.envio.ruta_log)
    ya_enviados = registro.telefonos_enviados()

    pendientes = [c for c in validos if c.telefono not in ya_enviados]
    if ya_enviados:
        print(f"  {len(validos) - len(pendientes)} ya estaban enviados segun el log, se saltan")

    if args.solo:
        pendientes = [c for c in pendientes if c.telefono == args.solo]
        if not pendientes:
            print(f"El numero {args.solo} no esta en la lista de pendientes.")
            return 1

    if args.limite is not None:
        pendientes = pendientes[: args.limite]

    if len(pendientes) > config.envio.tope_diario:
        print(f"  Tope diario de {config.envio.tope_diario}: se recortan "
              f"{len(pendientes) - config.envio.tope_diario} para otra corrida")
        pendientes = pendientes[: config.envio.tope_diario]

    print(f"\nPlantilla: {config.plantilla.nombre} ({config.plantilla.idioma})")
    print(f"A enviar ahora: {len(pendientes)}")
    print(f"Ritmo: {config.envio.segundos_entre_mensajes}s entre mensajes\n")

    if not pendientes:
        print("Nada por enviar.")
        return 0

    if args.dry_run:
        return _simular(pendientes, config)

    return _enviar(pendientes, config, registro)


def _simular(pendientes, config):
    print("--- DRY RUN: no se envia nada ---\n")
    for contacto in pendientes:
        payload = construir_payload(contacto, config.plantilla)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print()
    print(f"Se habrian enviado {len(pendientes)} mensajes.")
    return 0


def _enviar(pendientes, config, registro):
    sesion = requests.Session()
    enviados = 0
    fallidos = 0
    total = len(pendientes)

    try:
        for indice, contacto in enumerate(pendientes, start=1):
            payload = construir_payload(contacto, config.plantilla)

            try:
                resultado = enviar_con_reintentos(sesion, config.meta, payload)
            except TokenInvalido as error:
                print(f"\nTOKEN RECHAZADO POR META: {error}")
                print("Se detiene todo. Hay que generar un token nuevo.")
                return 1

            if resultado.ok:
                enviados += 1
                registro.anotar(contacto.telefono, contacto.nombre, ENVIADO,
                                message_id=resultado.message_id)
                estado = f"OK   {resultado.message_id}"
            else:
                fallidos += 1
                registro.anotar(contacto.telefono, contacto.nombre, FALLO,
                                codigo_error=resultado.codigo,
                                mensaje_error=resultado.mensaje)
                estado = f"FALLO [{resultado.codigo}] {resultado.mensaje}"

            print(f"[{indice}/{total}] {contacto.telefono} {contacto.nombre:<15} {estado}")

            if indice < total:
                time.sleep(_pausa(config.envio))
    finally:
        registro.cerrar()

    print(f"\nEnviados: {enviados}   Fallidos: {fallidos}")
    print(f"Detalle completo en: {config.envio.ruta_log}")
    return 0 if fallidos == 0 else 2


def _pausa(envio):
    """Espera con variacion aleatoria, para no verse como un robot exacto."""
    variacion = envio.segundos_entre_mensajes * envio.jitter
    return max(0.0, envio.segundos_entre_mensajes + random.uniform(-variacion, variacion))


def _contar_motivos(descartes):
    conteo = {}
    for descarte in descartes:
        conteo[descarte.motivo] = conteo.get(descarte.motivo, 0) + 1
    return conteo


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verificar que la ayuda funciona**

Run: `python enviar.py --help`
Expected: muestra las cuatro opciones sin error de importación

- [ ] **Step 3: Verificar que falla claro sin configuración**

Run: `python enviar.py --config no-existe.json`
Expected: `ERROR DE CONFIGURACION: No encuentro el archivo de campana: no-existe.json` y código de salida 1

- [ ] **Step 4: Correr toda la suite**

Run: `python -m pytest -q`
Expected: PASS — 60 passed

- [ ] **Step 5: Commit**

```bash
git add enviar.py
git commit -m "feat: CLI orquestador con dry-run, limite y filtro por numero"
```

---

## Task 10: Prueba real controlada

**Files:**
- Create: `campana.json` (ignorado por git)

- [ ] **Step 1: Crear `campana.json` para la prueba**

```json
{
  "excel": {
    "ruta": "prueba.xlsx",
    "hoja": null,
    "columna_nombre": "Nombre",
    "columna_telefono": "Teléfono"
  },
  "plantilla": {
    "nombre": "bonos_popsy_v7",
    "idioma": "es",
    "parametros_cuerpo": [
      { "origen": "nombre_normalizado" }
    ],
    "imagen_cabecera": null,
    "parametro_boton_url": { "origen": "fijo", "valor": "PRUEBA123" }
  },
  "envio": {
    "segundos_entre_mensajes": 5,
    "jitter": 0.2,
    "tope_diario": 900,
    "nombre_por_defecto": "Hola",
    "ruta_log": "logs/envios.csv"
  }
}
```

- [ ] **Step 2: Dry-run — revisar los payloads antes de gastar un solo mensaje**

Run: `python enviar.py --dry-run`

Expected: dos payloads, el primero exactamente así:

```json
{
  "messaging_product": "whatsapp",
  "to": "573001234567",
  "type": "template",
  "template": {
    "name": "bonos_popsy_v7",
    "language": { "code": "es" },
    "components": [
      { "type": "body", "parameters": [ { "type": "text", "text": "Ana" } ] },
      { "type": "button", "sub_type": "url", "index": "0",
        "parameters": [ { "type": "text", "text": "PRUEBA123" } ] }
    ]
  }
}
```

**No continuar si el payload no coincide.** Revisar nombre de plantilla, idioma
y el texto de la variable.

- [ ] **Step 3: Enviar a un solo número y verificar en el celular**

Run: `python enviar.py --solo 573001234567`

Expected: `[1/1] 573001234567 Ana           OK   wamid.XXXX`

Verificar en el teléfono que llegó el mensaje, que dice **"¡Hola Ana!"** y que
el botón "Descargar Cupón" aparece.

- [ ] **Step 4: Verificar que no reenvía**

Run: `python enviar.py --solo 573001234567`
Expected: `El numero 573001234567 no esta en la lista de pendientes.`

Esto confirma la idempotencia: el log ya lo tiene como enviado.

- [ ] **Step 5: Correr los dos contactos**

Run: `python enviar.py`

Expected: envía solo al segundo (el primero ya está en el log), con ~5 segundos
de pausa antes si hubiera más.

- [ ] **Step 6: Revisar el log**

Run: `python -c "print(open('logs/envios.csv',encoding='utf-8').read())"`

Expected: encabezado + una fila por envío con `estado=enviado` y su `message_id`.

- [ ] **Step 7: Confirmar que el log no entra a git**

Run: `git status --short`
Expected: `logs/` y `campana.json` **no** aparecen

- [ ] **Step 8: Commit**

```bash
git add campana.example.json
git commit -m "docs: configuracion de ejemplo para la primera campana"
```

---

## Self-review

**Cobertura del spec:**

| Requisito del spec | Task |
|--------------------|------|
| `config.py` valida y falla temprano | 5 |
| `contactos.py` normaliza teléfono (str e int) | 2 |
| `contactos.py` normaliza nombre (`nan`, mayúsculas) | 3 |
| Descartes con motivo (`vacio`, `no_es_movil_co`, `basura`, `duplicado`) | 2, 4 |
| Deduplicación | 4 |
| `whatsapp.py` — tres estructuras de plantilla | 6 |
| Parámetro fijo / columna / nombre normalizado | 6 |
| Reintentos solo en errores temporales | 7 |
| Token inválido aborta todo | 7 |
| Log incremental con flush | 8 |
| Reanudable (salta enviados) | 8, 9 |
| `--dry-run`, `--limite`, `--solo` | 9 |
| Ritmo con jitter y tope diario | 9 |
| Prueba real en tres pasos | 10 |

**Fuera de alcance por decisión (YAGNI):** el spec menciona exportar los
descartes a un `.xlsx` aparte. El usuario indicó que hará un Excel nuevo y que
no se envíe a esa lista, así que el CLI solo **imprime el conteo por motivo**.
Si más adelante hace falta el archivo de descartes, es una función de 10 líneas
sobre `Descarte`, que ya tiene todos los datos.

**Consistencia de tipos:** `Contacto(nombre, telefono, fila, crudo)` y
`Parametro(origen, nombre, valor)` se usan idénticos en Tasks 4, 6, 7 y 9.
`Resultado(ok, message_id, codigo, mensaje, reintentable)` se consume igual en
Tasks 7 y 9. Las constantes `ENVIADO`/`FALLO` viven en `src/registro.py` y se
importan desde `enviar.py`.
