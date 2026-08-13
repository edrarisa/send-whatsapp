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
