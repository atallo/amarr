# amarr image (Python port). Equivalent to the original's Jib configuration,
# but on python:3.12-slim instead of a JRE.
FROM python:3.12-slim

# Avoids .pyc files and forces unbuffered output (better logs in a container).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install the dependencies first to take advantage of layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code.
COPY amarr ./amarr

# Default values (can be overridden when launching the container).
ENV AMARR_PORT=8080 \
    AMARR_LOG_LEVEL=INFO \
    AMARR_CONFIG_PATH=/config \
    AMULE_FINISHED_PATH=/finished

# Port where amarr exposes the qBittorrent API and the Torznab indexer.
EXPOSE 8080

# Persistent configuration directory (categories and hashes).
VOLUME ["/config"]

# Starts the server (reads all the configuration from the environment).
CMD ["python", "-m", "amarr.app"]
