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

## Reanudar un envío a medias

El script escribe cada resultado en el CSV de `envio.ruta_log` **en el momento**,
y al arrancar salta a quien ya figura como `enviado`. Eso significa:

- Si el proceso se cae en el mensaje 400, lo relanzas y sigue en el 401.
- Puedes correrlo tantas veces como quieras: nunca envía dos veces al mismo número.
- El tope se cuenta sobre una **ventana móvil de 24 horas**, no por corrida. Si
  ya se enviaron 900 hoy, la siguiente ejecución no manda nada y te avisa.

## Desplegar en un servidor

Tres cosas que hay que resolver antes de dejarlo corriendo solo:

**1. El log tiene que sobrevivir a los despliegues.** Por defecto vive en
`logs/envios.csv`, dentro del proyecto. Si redespliegas con un `git clone`
limpio o un contenedor sin volumen, se pierde y **reenvía todo desde cero**.
Ponlo en una ruta absoluta fuera del repo:

```json
"envio": { "ruta_log": "/var/lib/send-whatsapp/envios.csv" }
```

**2. Un solo lugar como fuente de verdad.** Si lo corres en tu máquina *y* en el
servidor, cada uno lleva su propio CSV y no se enteran del otro. Elige uno.

**3. El `.env` va en el servidor, nunca en git.** Cópialo por SSH o usa las
variables de entorno del sistema.

## Qué nunca se sube a git

`.env`, `DATOS-META.md`, cualquier `.xlsx`/`.csv` y la carpeta `logs/`.
Los Excel contienen datos personales sujetos a habeas data (Ley 1581).
