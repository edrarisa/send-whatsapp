# Desplegar en un VPS

Guía para dejar el envío corriendo en un servidor Ubuntu/Debian.
No hace falta servidor web, ni base de datos, ni Docker: es un script.

---

## Qué necesita el VPS

- Ubuntu 22.04+ o Debian 12+ (cualquier VPS de 1 GB de RAM sobra)
- Python 3.11 o superior
- Salida a internet hacia `graph.facebook.com`

No necesita IP fija, ni dominio, ni puertos abiertos: el script **solo hace
peticiones salientes**. Nada entra desde fuera.

---

## 1. Preparar el servidor

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

# La zona horaria importa: las fechas que se escriben en el Excel usan la
# hora local del servidor. Sin esto, veras las horas en UTC.
sudo timedatectl set-timezone America/Bogota
```

## 2. Traer el código

```bash
sudo mkdir -p /opt/send-whatsapp
sudo chown $USER:$USER /opt/send-whatsapp
git clone https://github.com/edrarisa/send-whatsapp.git /opt/send-whatsapp
cd /opt/send-whatsapp
```

## 3. Entorno virtual y dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Verifica que quedó bien antes de seguir:**

```bash
python -m pytest -q
```

Debe decir `92 passed`. Si falla algo, no sigas: hay un problema de entorno.

## 4. Carpetas para los datos

El log y los Excel **no pueden vivir dentro del repo**. Si algún día
redespliegas con un `git clone` limpio o borras la carpeta, perderías el
registro de a quién ya le enviaste — y el script reenviaría todo desde cero.

```bash
sudo mkdir -p /var/lib/send-whatsapp/{logs,datos}
sudo chown -R $USER:$USER /var/lib/send-whatsapp
chmod 700 /var/lib/send-whatsapp
```

## 5. El archivo `.env`

Nunca viaja por git. Créalo a mano:

```bash
nano /opt/send-whatsapp/.env
```

Contenido:

```
WHATSAPP_TOKEN=EAA...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_WABA_ID=...
GRAPH_API_VERSION=v21.0
```

**Protégelo:** el token permite enviar mensajes y gastar tu tarjeta.

```bash
chmod 600 /opt/send-whatsapp/.env
```

## 6. Subir los datos desde tu máquina

Desde Windows, en PowerShell:

```powershell
scp .env           usuario@TU_IP:/opt/send-whatsapp/.env
scp campana.json   usuario@TU_IP:/opt/send-whatsapp/campana.json
scp contactos.xlsx usuario@TU_IP:/var/lib/send-whatsapp/datos/contactos.xlsx
```

## 7. Ajustar `campana.json` para el servidor

Dos rutas cambian a absolutas:

```json
{
  "excel": {
    "ruta": "/var/lib/send-whatsapp/datos/contactos.xlsx",
    "columna_nombre": "Nombre",
    "columna_telefono": "Teléfono"
  },
  "plantilla": {
    "nombre": "conversatorio_datos_agosto_2026",
    "idioma": "es",
    "parametros_cuerpo": [{ "origen": "nombre_normalizado" }],
    "imagen_cabecera": "/opt/send-whatsapp/Conversatorio-LinkedIn-MYQ-2026.jpg",
    "parametro_boton_url": null
  },
  "envio": {
    "segundos_entre_mensajes": 3,
    "jitter": 0.2,
    "tope_diario": 900,
    "nombre_por_defecto": "Hola",
    "ruta_log": "/var/lib/send-whatsapp/logs/envios.csv"
  }
}
```

⚠️ `ruta_log` **fuera de `/opt/send-whatsapp`**. Es lo que hace el envío
reanudable y lo que evita cobrar dos veces al mismo número.

## 8. Probar sin enviar

```bash
cd /opt/send-whatsapp
source .venv/bin/activate
python enviar.py --dry-run
```

Revisa que el nombre de la plantilla y el número de contactos sean los
correctos. Después, un envío de prueba a ti mismo:

```bash
python enviar.py --solo 57XXXXXXXXXX
```

---

## Correr el envío completo

Un envío de 820 mensajes a 3 segundos tarda unos **45 minutos**. Si lanzas el
comando por SSH y se corta la conexión, el proceso muere. Usa `tmux`:

```bash
sudo apt install -y tmux

tmux new -s envio           # abre una sesion que sobrevive a la desconexion
cd /opt/send-whatsapp && source .venv/bin/activate
python enviar.py

# Ctrl+B, luego D  -> te sales dejandolo corriendo
# tmux attach -t envio  -> vuelves a entrar para mirar
```

Si aun asi se interrumpe, no pierdes nada: relanzas `python enviar.py` y
continúa donde quedó, saltando a quien ya recibió.

---

## Automatizar con cron (opcional)

Para que envíe solo cada día hasta terminar la lista:

```bash
crontab -e
```

```cron
# Todos los dias a las 9:00, hasta agotar la lista
0 9 * * * cd /opt/send-whatsapp && ./.venv/bin/python enviar.py >> /var/lib/send-whatsapp/logs/cron.log 2>&1
```

Funciona porque el script es idempotente: cada corrida salta a quien ya recibió
y respeta el tope de las últimas 24 horas. Cuando no queda nadie pendiente,
imprime "Nada por enviar" y termina.

---

## Seguridad

Estás poniendo en un servidor un token que gasta dinero y una lista de datos
personales sujeta a habeas data (Ley 1581).

```bash
chmod 600 /opt/send-whatsapp/.env          # solo tu usuario lo lee
chmod 700 /var/lib/send-whatsapp           # los Excel y logs, tambien
```

Además:

- **No uses root** para correr el script.
- **Deshabilita el login por contraseña** en SSH; usa solo llaves.
- **Borra los Excel del servidor** cuando termine la campaña. No hay razón para
  dejar 800 teléfonos de personas reales en una máquina expuesta a internet.
- Si el VPS es compartido o lo administra un tercero, ten presente que tienen
  acceso a esos archivos.

---

## Opción B — Desplegar en Coolify

El repositorio trae `Dockerfile` y `docker-compose.yaml` listos.

### La idea de fondo

Coolify está pensado para **servicios que corren siempre**. Este proyecto es un
script que envía y termina. Si el contenedor ejecutara el envío al arrancar,
**cada redespliegue dispararía la campaña otra vez**.

Por eso el contenedor arranca con `sleep infinity` y no hace nada solo. El
envío se dispara a propósito, como tarea programada o a mano.

### 1. Crear el recurso

En Coolify: **+ Add Resource → Docker Compose** (o *Application* si prefieres
que detecte el `Dockerfile`).

| Campo | Valor |
|-------|-------|
| Repositorio | `https://github.com/edrarisa/send-whatsapp` |
| Rama | `main` |
| Compose file | `docker-compose.yaml` |

El repositorio es público, así que no necesita credenciales de GitHub.

### 2. Variables de entorno

En la pestaña de variables del recurso, marcadas como **secretas**:

```
WHATSAPP_TOKEN=EAA...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_WABA_ID=...
GRAPH_API_VERSION=v21.0
```

No hace falta subir ningún `.env`: el script lee primero las variables de
entorno y solo cae al archivo si no las encuentra.

### 3. Desplegar y comprobar

Dale a **Deploy**. Cuando termine, abre la terminal del contenedor desde Coolify
y verifica que la imagen quedó bien:

```bash
python -m pytest -q          # debe decir 97 passed
```

### 4. Meter los datos en el volumen

El volumen `/datos` es persistente y **está vacío** al principio. Necesita dos
cosas. Desde tu máquina:

```bash
docker cp campana.json    send-whatsapp:/datos/campana.json
docker cp contactos.xlsx  send-whatsapp:/datos/entrada/contactos.xlsx
```

O crea `campana.json` directamente desde la terminal de Coolify con `nano`.

### 5. `campana.json` con rutas del contenedor

```json
{
  "excel": {
    "ruta": "/datos/entrada/contactos.xlsx",
    "columna_nombre": "Nombre",
    "columna_telefono": "Teléfono"
  },
  "plantilla": {
    "nombre": "conversatorio_datos_agosto_2026",
    "idioma": "es",
    "parametros_cuerpo": [{ "origen": "nombre_normalizado" }],
    "imagen_cabecera": "/app/Conversatorio-LinkedIn-MYQ-2026.jpg",
    "parametro_boton_url": null
  },
  "envio": {
    "segundos_entre_mensajes": 3,
    "jitter": 0.2,
    "tope_diario": 900,
    "nombre_por_defecto": "Hola",
    "ruta_log": "/datos/logs/envios.csv"
  }
}
```

La imagen del banner sí viaja dentro de la imagen Docker (`/app/`), porque está
en el repositorio. Los datos van en `/datos/`, que es el volumen.

### 6. Enviar

Siempre en este orden:

```bash
# Simulacion, no envia nada
docker exec send-whatsapp python enviar.py --config /datos/campana.json --dry-run

# Uno solo, para verificar en el celular
docker exec send-whatsapp python enviar.py --config /datos/campana.json --solo 57XXXXXXXXXX

# Campana completa
docker exec send-whatsapp python enviar.py --config /datos/campana.json
```

Desde Coolify también puedes hacerlo abriendo la terminal del contenedor.

### 7. Programarlo (opcional)

En el recurso → **Scheduled Tasks**:

| Campo | Valor |
|-------|-------|
| Comando | `python enviar.py --config /datos/campana.json` |
| Frecuencia | `0 9 * * *` |
| Contenedor | `enviador` |

Es seguro repetirlo: cada corrida salta a quien ya recibió y respeta el tope de
las últimas 24 horas.

### Lo que NO puede pasar

⚠️ **Que el volumen `datos` se borre.** Ahí vive `envios.csv`, que es lo único
que impide reenviar a toda la lista. Si borras el volumen y relanzas, se envían
los 820 otra vez: pagas dos veces y la gente recibe el mensaje repetido.

Redesplegar el recurso **no** borra el volumen. Borrar el recurso, sí.

⚠️ **Que los secretos entren a la imagen.** El `.dockerignore` deja fuera
`.env`, los `.xlsx` y `DATOS-META.md`. No los quites de ahí: las capas de una
imagen son legibles aunque el archivo se borre después.

---

## Actualizar el código más adelante

```bash
cd /opt/send-whatsapp
git pull
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

`.env`, `campana.json`, los Excel y los logs **no se tocan** con el `git pull`:
están fuera del repositorio o ignorados.
