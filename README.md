# Amarr - Conector aMule para *arr (port a Python)

Este conector permite usar **aMule** como cliente de descargas para
[Sonarr](https://sonarr.tv/) y [Radarr](https://radarr.video/). Funciona
**emulando un cliente de torrents** (la WebAPI de qBittorrent v2.8.19), de modo
que Sonarr/Radarr gestionan tus descargas como si fueran torrents, y exponiendo
además endpoints **Torznab** para la búsqueda.

Es una traducción a **Python** del proyecto original escrito en Kotlin. La
comunicación con aMule usa el protocolo binario **EC (External Connection)**,
portado igualmente a Python a partir de la librería
[jaMule](https://github.com/vexdev/jaMule), que sólo soporta aMule **2.3.1** a
**2.3.3**.

## Requisitos previos

- [aMule](https://www.amule.org/) versión **2.3.1** a **2.3.3** en marcha y
  configurado (con la conexión EC habilitada).
- [Sonarr](https://sonarr.tv/) o [Radarr](https://radarr.video/) en marcha.

**Amarr no incluye su propia instalación de aMule**: necesitas tener aMule
funcionando aparte (por ejemplo con la imagen Docker de
[ngosang](https://github.com/ngosang/docker-amule) o la de Adunanza de
[m4dfry](https://github.com/m4dfry/amule-adunanza-docker)).

## Instalación

Amarr se ejecuta como contenedor Docker. La imagen se publica en **GitHub
Container Registry (ghcr.io)**:

```
ghcr.io/<owner>/amarr:latest
```

(Sustituye `<owner>` por el usuario u organización de GitHub donde esté el
repositorio.)

### Variables de entorno

```
AMULE_HOST: aMule       # Host donde corre aMule (en Docker suele ser el nombre del contenedor)
AMULE_PORT: 4712        # Puerto EC de aMule
AMULE_PASSWORD: secret  # Contraseña de conexión a aMule

Opcionales:
AMULE_FINISHED_PATH: /finished  # Carpeta donde aMule deja los ficheros terminados
AMARR_PORT: 8080                # Puerto en el que escucha amarr (por defecto 8080)
AMARR_LOG_LEVEL: INFO           # Nivel de log: DEBUG, INFO, WARN, ERROR (por defecto INFO)
AMARR_CONFIG_PATH: /config      # Carpeta de configuración persistente (por defecto /config)
```

### Volúmenes

```
/config   # Carpeta donde amarr guarda su configuración; debe ser persistente
```

El contenedor expone el puerto **8080**, donde amarr publica la API qBittorrent
y el servidor Torznab para Sonarr/Radarr.

### Ejemplo `docker-compose.yml`

```yaml
services:
  amarr:
    image: ghcr.io/<owner>/amarr:latest
    container_name: amarr
    environment:
      - AMULE_HOST=aMule
      - AMULE_PORT=4712
      - AMULE_PASSWORD=secret
    volumes:
      - /path/to/amarr/config:/config
    ports:
      - 8080:8080
```

## Configuración de Radarr/Sonarr (2 pasos)

### 1. Configurar amarr como cliente de descargas

Añade un nuevo cliente de descargas de tipo **qBittorrent** con estos ajustes
(pulsa antes "Show advanced settings"):

```
Name: el que quieras
Host: amarr      # Host donde corre amarr (en Docker, el nombre del contenedor)
Port: 8080       # Puerto donde escucha amarr
Priority: 50     # Prioridad más baja posible para que se prefieran otros clientes
```

### 2. Configurar amarr como indexador Torznab

Añade un nuevo **indexador Torznab** con estos ajustes:

```
Name: el que quieras
Url: http://amarr:8080/indexer/amule
Download Client: el nombre que diste a amarr en el paso anterior
```

## Indexadores

### `amule`

Busca ficheros en aMule a través de la red kad/eD2k. Es lento y poco fiable, y
los ficheros de esa red no están bien revisados (puedes acabar descargando
ficheros falsos). No requiere configuración adicional.

> **Nota:** el indexador `ddunlimitednet` del proyecto original **no** se ha
> incluido en este port a Python.

## Desarrollo

Requiere Python 3.11 o superior.

```bash
# Instala las dependencias (incluidas las de desarrollo)
pip install -e ".[dev]"

# Ejecuta las pruebas
pytest

# Arranca el servidor en local (lee la configuración del entorno)
AMULE_HOST=localhost AMULE_PORT=4712 AMULE_PASSWORD=secret python -m amarr.app
```

## Notas de arquitectura (port a Python)

- **Servidor web:** se usa **FastAPI + uvicorn** en lugar de Ktor. La API
  qBittorrent responde en JSON/texto y la Torznab en XML.
- **Cliente EC síncrono:** el protocolo EC se ha portado de forma **síncrona**
  (sockets + `struct` + `hashlib` + `zlib`), protegido con un cerrojo. Los
  handlers de FastAPI que tocan aMule son funciones `def` (no `async`), así que
  Starlette las ejecuta en su *threadpool* y no bloquean el bucle de eventos.
- **Modelos:** se usa **pydantic v2** (equivalente a las `data class`
  serializables del original).
- **Compatibilidad de protocolo:** la implementación se ha validado byte a byte
  contra los vectores de prueba de jaMule (autenticación, búsqueda, estado y
  hash de contraseña).
- **Publicación:** la imagen se publica en **ghcr.io** mediante GitHub Actions
  (`.github/workflows/release.yml`), usando el `GITHUB_TOKEN` integrado.

## Licencia

MIT.
