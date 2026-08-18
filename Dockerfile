FROM python:3.13-slim

# La hora local se usa al escribir la fecha de envio en el Excel.
ENV TZ=America/Bogota \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Las dependencias en su propia capa: cambian mucho menos que el codigo,
# asi los rebuilds no vuelven a descargarlas.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY enviar.py vigilante.py conftest.py ./
COPY tests/ ./tests/
COPY Conversatorio-LinkedIn-MYQ-2026.jpg recordatorio-conversatorio-agosto.jpeg Conectate-hoy-whatsapp.jpg ./

# /datos es un volumen: ahi viven el log, los Excel y campana.json. Tiene que
# sobrevivir a los redespliegues, porque el log es lo unico que impide volver
# a enviarle a quien ya recibio.
RUN mkdir -p /datos/logs /datos/entrada /datos/ordenes \
 && useradd --create-home --uid 1000 enviador \
 && chown -R enviador:enviador /app /datos

USER enviador
VOLUME ["/datos"]

# Por defecto solo se queda vivo. El compose sobreescribe esto: el enviador
# corre `python vigilante.py` y el panel corre gunicorn. Lanzar el envio a mano
# sigue siendo posible en cualquier momento:
#
#   docker exec send-whatsapp python enviar.py --config /datos/campana.json
#
CMD ["sleep", "infinity"]
