# Imagen de amarr (port a Python). Equivale a la configuración Jib del original,
# pero sobre python:3.12-slim en lugar de un JRE.
FROM python:3.12-slim

# Evita ficheros .pyc y fuerza salida sin búfer (mejores logs en contenedor).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instala primero las dependencias para aprovechar la caché de capas.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código de la aplicación.
COPY amarr ./amarr

# Valores por defecto (se pueden sobrescribir al lanzar el contenedor).
ENV AMARR_PORT=8080 \
    AMARR_LOG_LEVEL=INFO \
    AMARR_CONFIG_PATH=/config \
    AMULE_FINISHED_PATH=/finished

# Puerto donde amarr expone la API qBittorrent y el indexador Torznab.
EXPOSE 8080

# Directorio de configuración persistente (categorías y hashes).
VOLUME ["/config"]

# Arranca el servidor (lee toda la configuración del entorno).
CMD ["python", "-m", "amarr.app"]
