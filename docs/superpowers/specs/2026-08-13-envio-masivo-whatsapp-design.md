# Envío masivo de WhatsApp desde Excel — Diseño

**Fecha:** 2026-08-13
**Estado:** aprobado por el usuario, pendiente plan de implementación

## Problema

Enviar plantillas de WhatsApp a cientos de contactos leídos de un Excel, a un
ritmo controlado, sin cobrar dos veces por el mismo destinatario y sin quemar la
calidad del número emisor.

## Contexto ya resuelto

La infraestructura de Meta existe y está verificada. Los valores reales viven en
`DATOS-META.md` y `.env`, **ambos fuera de git** (repositorio público).

| Recurso | Estado |
|---------|--------|
| WABA ID | ✅ obtenido |
| Phone Number ID | ✅ obtenido — número `CONNECTED`, calidad `GREEN`, `platform_type: CLOUD_API` |
| Token | ✅ permanente, sin caducidad, en `.env` |
| Plantillas aprobadas | ✅ 14 |

## Alcance

**Dentro:**

- Leer contactos de un `.xlsx`
- Normalizar y validar nombres y teléfonos colombianos
- Enviar una plantilla aprobada vía Cloud API
- Controlar ritmo y tope diario
- Registrar cada envío y poder reanudar sin duplicar

**Fuera (YAGNI):**

- Interfaz web
- Recepción de respuestas / webhooks
- Creación de plantillas por API
- Recuperación de teléfonos mal formados (fijos, extranjeros)
- Envío de texto libre (la API no lo permite fuera de la ventana de 24h)

## Enfoque elegido

Script CLI con archivo de configuración JSON. La campaña vive en el JSON;
cambiar de campaña no toca código.

Descartados: hardcodear todo (se rompe en cada campaña nueva) e interfaz web
(3-4× el trabajo, innecesario para un solo usuario técnico).

## Arquitectura

Cuatro módulos, una responsabilidad cada uno:

```
config.py      Lee campana.json + .env. Valida que no falte nada. Falla temprano.
contactos.py   Excel -> normaliza -> valida -> (lista limpia, lista de descartes).
whatsapp.py    Cliente Cloud API. Arma el payload y envía UN mensaje.
enviar.py      Orquesta: recorre, controla ritmo, reintenta, registra.
```

**Frontera clave:** `whatsapp.py` no sabe qué es un Excel; `contactos.py` no sabe
qué es WhatsApp. Ambos se prueban sin gastar un mensaje real.

### Flujo

```
campana.json + .env
        |
        v
   config.py  --(falla si falta algo)--> salida con error claro
        |
        v
  contactos.py  --> descartes.xlsx (motivo por fila)
        |
        v
   [contactos válidos]  --(menos los ya enviados según log)-->
        |
        v
   enviar.py  --por cada uno-->  whatsapp.py  -->  Graph API
        |                                             |
        +--> logs/envios.csv  <-----------------------+
             (se escribe en el momento, no al final)
```

## Componentes

### `config.py`

Carga `.env` (token, phone_number_id, versión de API) y el JSON de campaña.
Valida en el arranque: token presente, plantilla con nombre e idioma, ruta del
Excel existe, mapeo de parámetros coherente. Si algo falta, aborta con un
mensaje que dice exactamente qué.

### `contactos.py`

**Teléfono** — acepta `str` o `int` (los dos Excel de muestra difieren en tipo).
Se queda solo con dígitos. Si son 10 y empiezan con `3` → móvil colombiano
válido → prefija `57`. Todo lo demás se descarta con motivo:

| Motivo | Ejemplo real |
|--------|--------------|
| `vacio` | celda en blanco (553 casos en el Excel grande) |
| `no_es_movil_co` | `(1) 2288478`, `604 4488388`, `50761000000` |
| `basura` | `RODRIGUEZ`, `0`, `99999991`, `57321800000000000` |
| `duplicado` | mismo número en dos filas |

**Nombre** — primer token, se elimina el literal `nan` (residuo de un export de
pandas), se capitaliza:

- `"ANGELA SANCHEZ"` → `Angela`
- `"Andrea nan"` → `Andrea`
- `"Adriana Marcela Rodríguez Rocha"` → `Adriana`
- vacío o basura → valor por defecto configurable

Devuelve `(validos, descartados)`. Nunca lanza excepción por una fila mala.

### `whatsapp.py`

`POST /{version}/{phone_number_id}/messages` con
`Authorization: Bearer {token}`.

Arma el objeto `template` según la configuración. Soporta las tres estructuras
que existen en la WABA:

| Estructura | Ejemplo real | Componentes |
|-----------|--------------|-------------|
| Solo cuerpo | `hello_world` | ninguno |
| Cuerpo + botón URL variable | `bonos_popsy_v7` | `body` + `button` (sub_type `url`, index 0) |
| Imagen + cuerpo + botón fijo | `dama_week_*` | `header` (image) + `body` |

Cada parámetro se declara en el JSON como **valor fijo** o **columna del Excel**.

Devuelve un resultado tipado: éxito con `message_id`, o fallo con código y
mensaje de Meta.

### `enviar.py`

Recorre los contactos válidos, salteando los que ya figuran como enviados en el
log. Por cada uno:

1. Envía vía `whatsapp.py`
2. Escribe el resultado a `logs/envios.csv` **inmediatamente**
3. Espera `segundos_entre_mensajes` + jitter aleatorio

## Control de ritmo

- `segundos_entre_mensajes`: configurable. **5 s para la prueba**, ~1,5 s para
  producción.
- Jitter aleatorio (±20%) para no parecer un robot exacto.
- `tope_diario`: 900 por defecto — colchón bajo el límite de 1.000
  conversaciones/24h del tier inicial.

## Manejo de errores

**Reintentables** (3 intentos, espera creciente 2s → 4s → 8s):

- `429` límite de tasa
- `5xx` errores de Meta
- timeouts y fallos de red

**No reintentables** (se registran y se sigue con el siguiente):

- `131026` destinatario no tiene WhatsApp
- `132xxx` errores de plantilla (nombre, idioma o parámetros mal)
- `190` token inválido o revocado → **aborta todo el proceso**, no tiene sentido
  seguir

Un contacto que falla nunca detiene la corrida.

## Idempotencia — evitar cobrar dos veces

Esto es lo más importante del diseño. Cada conversación de marketing cuesta
dinero, y un doble envío también molesta al destinatario.

- `logs/envios.csv` se escribe fila por fila **en el momento**, con:
  `timestamp, telefono, nombre, estado, message_id, codigo_error, mensaje_error`
- Al arrancar, el script lee el log y **salta los teléfonos con estado `enviado`**
- Si el proceso se cae en el mensaje 400, se relanza y continúa en el 401

## Modos de ejecución

| Flag | Efecto |
|------|--------|
| `--dry-run` | Imprime los payloads exactos. **No envía nada.** |
| `--limite N` | Envía solo a los primeros N contactos válidos |
| `--solo 57XXXXXXXXXX` | Envía únicamente a ese número |
| (sin flags) | Corrida completa |

## Configuración — `campana.json`

```json
{
  "excel": {
    "ruta": "prueba.xlsx",
    "hoja": "Sheet1",
    "columna_nombre": "Nombre",
    "columna_telefono": "Teléfono"
  },
  "plantilla": {
    "nombre": "bonos_popsy_v7",
    "idioma": "es",
    "parametros_cuerpo": [
      { "origen": "nombre_normalizado" }
    ],
    "parametro_boton_url": { "origen": "fijo", "valor": "PRUEBA123" }
  },
  "envio": {
    "segundos_entre_mensajes": 5,
    "jitter": 0.2,
    "tope_diario": 900,
    "nombre_por_defecto": "Hola"
  }
}
```

Tipos de `origen` para un parámetro:

- `"nombre_normalizado"` — el primer nombre ya limpio
- `"columna"` + `"nombre": "MiColumna"` — el valor crudo de esa columna
- `"fijo"` + `"valor": "..."` — el mismo texto para todos

## Pruebas

Sin gastar mensajes reales:

- **`contactos.py`** — casos tomados del Excel real: `99999991`, `RODRIGUEZ`,
  `0`, `(1) 2288478`, `604 4488388`, `50761000000`, `57321800000000000`,
  celdas vacías, duplicados, teléfono como `int` y como `str`, `"Andrea nan"`,
  `"ANGELA SANCHEZ"`.
- **`whatsapp.py`** — verificar la forma del payload contra las tres estructuras
  de plantilla, sin llamar a la red.
- **`enviar.py`** — que el log haga saltar los ya enviados; que un fallo no
  detenga la corrida; que `--dry-run` no envíe.

Con mensajes reales, en orden:

1. `--dry-run` sobre `prueba.xlsx` → revisar los dos payloads a ojo
2. `--solo <número propio>` → un mensaje a uno mismo, verificar en el celular
3. `prueba.xlsx` completo (2 contactos, 5 s entre mensajes)

## Plan de la primera prueba

- Excel: `prueba.xlsx` — 2 contactos (fuera de git)
- Plantilla: `bonos_popsy_v7` (`es`) — sin imagen, con variable de nombre y
  parámetro de botón
- Ritmo: 5 segundos entre mensajes

## Seguridad — el repositorio es público

Nunca entran a git: `.env`, `DATOS-META.md`, cualquier `.xlsx`/`.csv`, y la
carpeta `logs/` (contiene teléfonos de personas reales, sujetos a habeas data).
El spec y el README usan marcadores, no valores reales.

## Decisiones registradas

| Decisión | Motivo |
|----------|--------|
| Python | Ya instalado (3.13); `openpyxl`, `requests`, `python-dotenv` presentes |
| Solo móviles colombianos | Es el 100% de la lista real; agregar países es cambiar una función |
| Log en CSV, no base de datos | Un archivo que se abre en Excel; suficiente para cientos de filas |
| Seguir con el número actual | Ya está `CONNECTED` y con calidad `GREEN`; una SIM nueva arranca en `UNKNOWN` |
| Cambiar de número = 1 línea del `.env` | Solo cambia `WHATSAPP_PHONE_NUMBER_ID`, siempre que el número entre a la **misma** WABA |
