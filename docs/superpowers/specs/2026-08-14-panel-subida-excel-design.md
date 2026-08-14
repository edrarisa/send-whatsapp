# Panel web para subir el Excel de contactos — Diseño

**Fecha:** 2026-08-14
**Estado:** aprobado por el usuario, pendiente plan de implementación

## Problema

Actualizar la lista de contactos en el servidor exige `scp` al host y luego
`docker cp` al contenedor. Es engorroso y hay que hacerlo cada vez que cambia
la lista.

## Alcance

**Dentro:** una página web con contraseña donde subir el `.xlsx`, que valida el
archivo antes de reemplazar el actual y muestra cuántos contactos quedaron.

**Fuera (YAGNI):** lanzar envíos, ver o descargar teléfonos, editar la campaña,
gestión de usuarios, historial, estadísticas. Todo eso sigue por CLI.

Cada función extra es superficie de ataque nueva sobre datos personales.

## Restricción que enmarca todo

El panel queda expuesto a internet y da acceso a una lista de **1.003 personas
reales**, sujeta a habeas data (Ley 1581). El diseño prioriza reducir lo que un
atacante obtiene si entra, por encima de la comodidad.

## Enfoque elegido

Servicio aparte en el mismo `docker-compose.yaml`, con la misma imagen.

```
enviador   sleep infinity, sin puertos      (como está hoy)
panel      flask, puerto 8000               (nuevo)
   └── ambos montan el volumen /datos
```

**Por qué separado:** el panel no puede lanzar envíos ni por accidente, y si lo
tumban, el enviador sigue intacto.

Descartados: todo en un contenedor (un fallo del panel se lleva el enviador) y
subida por URL firmada (no resuelve el "¿dónde lo subo?").

## Arquitectura

| Archivo | Responsabilidad |
|---------|-----------------|
| `src/panel.py` | App Flask: sesión, subida, validación. No importa `enviar.py`. |
| `src/plantillas_html/` | Dos plantillas: login y subida. HTML plano, sin JavaScript. |
| `docker-compose.yaml` | Se añade el servicio `panel`. |
| `requirements.txt` | Se añade `flask`. Única dependencia nueva. |

`panel.py` solo usa `leer_contactos` de `contactos.py` para validar. **No tiene
acceso al token de WhatsApp**: sus variables de entorno no lo incluyen.

## Seguridad

| Medida | Qué evita |
|--------|-----------|
| Contraseña como **hash** en `PANEL_PASSWORD_HASH` | Que leer las variables del panel revele la contraseña |
| HTTPS por el proxy de Coolify | Que la contraseña viaje en claro |
| Cookie `HttpOnly` + `Secure` + `SameSite=Strict` | Robo de sesión |
| Espera creciente tras 3 intentos fallidos | Fuerza bruta |
| Solo `.xlsx`, máx 10 MB, se verifican los **bytes** (`PK`) | Subir un ejecutable renombrado |
| Nombre de destino **fijo**, nunca el del usuario | Escribir fuera de `/datos/entrada` |
| El panel **no descarga** el Excel ni muestra teléfonos | Que entrar equivalga a llevarse la lista |
| `SECRET_KEY` desde variable de entorno | Falsificar cookies de sesión |

El panel sube, no baja. Es la decisión de seguridad más importante del diseño.

## Flujo de subida

```
1. Recibe el archivo        -> a un temporal, NO al destino
2. Valida bytes y tamaño
3. Lo procesa con leer_contactos()
4. Si hay 0 validos o falla -> RECHAZA; la lista anterior sigue intacta
5. Si esta bien             -> lo mueve a /datos/entrada/contactos.xlsx
6. Muestra el resumen       -> "1003 validos, 21 descartados (largo_invalido: 21)"
```

**Nunca reemplaza una lista buena por un archivo roto.** Validar antes de
sustituir es lo que hace segura la operación.

La página muestra el estado actual: fecha de la última subida y cuántos
contactos tiene el archivo vigente.

## Manejo de errores

Cada fallo devuelve un mensaje que dice qué pasó y qué hacer:

| Situación | Mensaje |
|-----------|---------|
| No es un `.xlsx` | "El archivo debe ser .xlsx" |
| Pasa de 10 MB | "El archivo pesa X MB; el máximo son 10 MB" |
| Falta la columna `Teléfono` | "El Excel no tiene la columna 'Teléfono'. Encontradas: [...]" |
| 0 contactos válidos | "Ningún contacto válido. No se reemplazó la lista anterior." |
| Contraseña incorrecta | "Contraseña incorrecta" (sin decir si el usuario existe) |

## Configuración

Variables de entorno del servicio `panel`:

```
PANEL_PASSWORD_HASH=pbkdf2:sha256:...     # generado con werkzeug
PANEL_SECRET_KEY=<cadena aleatoria larga>
PANEL_DESTINO=/datos/entrada/contactos.xlsx
```

**No recibe** `WHATSAPP_TOKEN`: no lo necesita y no debe poder enviar.

## Pruebas

Con el cliente de pruebas de Flask, sin levantar servidor ni tocar la red:

- Sin sesión, cualquier ruta redirige al login
- Contraseña incorrecta no crea sesión
- Contraseña correcta sí
- Un `.txt` renombrado a `.xlsx` se rechaza (falla la comprobación de bytes)
- Un archivo de más de 10 MB se rechaza
- Un Excel sin columna `Teléfono` se rechaza **y el archivo anterior sigue ahí**
- Un Excel válido reemplaza el anterior y devuelve el conteo correcto
- Un nombre con `../` no escribe fuera de la carpeta de destino
- La cookie de sesión trae `HttpOnly` y `SameSite`

## Despliegue

El servicio `panel` necesita dominio y HTTPS en Coolify — a diferencia del
`enviador`, que no expone nada. En Coolify: **Domains → Generate Domain** sobre
el servicio `panel` únicamente.

## Decisiones registradas

| Decisión | Motivo |
|----------|--------|
| Flask, no FastAPI | Sirve HTML y formularios sin capas extra; FastAPI brilla en APIs JSON, que no es el caso |
| Sin JavaScript | Un formulario HTML basta; menos código que auditar |
| Contraseña única, sin usuarios | Lo usa una sola persona; añadir cuentas es complejidad sin beneficio |
| Validar antes de reemplazar | Evita perder la lista buena por subir el archivo equivocado |
| El panel no descarga nada | Limita el daño si alguien entra |
| Servicio separado del enviador | El panel no puede gastar dinero ni tumbar el envío |

## Fuera de alcance, para más adelante

Si el panel resulta útil, los candidatos naturales son: lanzar el envío desde
ahí, ver el progreso en vivo y consultar el log. Ninguno entra ahora: cada uno
convierte una página que solo recibe archivos en una que ejecuta acciones con
costo económico.
