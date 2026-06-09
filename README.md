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

Motores de búsqueda (ver "Indexadores y motores de búsqueda"):
AMARR_SEARCH_BACKENDS: amule          # Motores activos, lista por comas: amule,ed2k,kad (por defecto amule)
AMARR_ED2K_SERVER: 45.82.80.155:5687  # Servidor eD2k para el motor "ed2k" (host:puerto)
AMARR_KAD_NODES: /config/nodes.dat    # nodes.dat para "kad" (por defecto: /config/nodes.dat o el empaquetado)
AMARR_KAD_IP_ORDER: be                # Orden de bytes de IP en nodes.dat: be o le (por defecto be)
AMARR_KAD_WITH_SOURCES: false         # Kad: contar fuentes reales por fichero (lento; por defecto false)
AMARR_CACHE_TTL: 3600                 # Caché de búsquedas en segundos (0 = desactivar; por defecto 3600 = 1 h)
AMARR_SEARCH_IDLE_TIMEOUT: 600        # Mantener viva la conexión eD2k / el pool Kad N s sin búsquedas (0 = no; def. 600 = 10 min)
```

### Volúmenes

```
/config   # Persistente. Guarda la BD SQLite de categorías (amarr.db) y la
          # caché de búsquedas (cache.db, regenerable).
```

> En versiones anteriores amarr usaba ficheros `categories.tsv`/`hashes.tsv`. Al
> arrancar con esta versión, esos ficheros se renombran a `*.tsv.bak` (no se
> importan; la base de datos arranca vacía).

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
Url: http://amarr:8080/indexer/amule   # o /indexer/ed2k, /indexer/kad, /indexer/all (ver Indexadores)
Download Client: el nombre que diste a amarr en el paso anterior
```

## Indexadores y motores de búsqueda

amarr puede buscar con tres motores, activables con `AMARR_SEARCH_BACKENDS`
(lista por comas, al menos uno):

- **`amule`** — Busca a través de un **aMule externo** (protocolo EC), como hasta
  ahora. Requiere aMule en marcha.
- **`ed2k`** — Busca directamente en un **servidor eD2k**, implementado por amarr
  (100% Python, sin aMule para la búsqueda). Servidor configurable con
  `AMARR_ED2K_SERVER`.
- **`kad`** — Busca en la **red Kad** (serverless), implementado por amarr. Usa un
  `nodes.dat` (`AMARR_KAD_NODES`; se incluye uno por defecto).

Cada motor activo expone su propio endpoint Torznab, y además hay un endpoint
`all` que **agrupa** los resultados de todos los activos:

```
http://amarr:8080/indexer/amule    # solo aMule
http://amarr:8080/indexer/ed2k     # solo servidor eD2k
http://amarr:8080/indexer/kad      # solo Kad
http://amarr:8080/indexer/all      # todos los motores activos, combinados
```

En Sonarr/Radarr usa como URL del indexador la del motor que quieras (o `all`).
Sea cual sea el motor de búsqueda, **la descarga siempre la realiza aMule**, así
que aMule debe seguir configurado y en marcha.

> Los resultados de la red eD2k/Kad no están bien revisados (puedes acabar
> descargando ficheros falsos). El motor `kad` puede tardar bastante por consulta.
>
> **Nota:** el indexador `ddunlimitednet` del proyecto original **no** se ha
> incluido en este port a Python.

Los resultados de cada búsqueda se **cachean** en `cache.db` durante
`AMARR_CACHE_TTL` segundos (1 h por defecto), por `(motor, consulta)`, de modo
que la paginación de Sonarr/Radarr y las búsquedas repetidas no relanzan la
consulta — importante sobre todo para Kad, que es lento. Pon `AMARR_CACHE_TTL=0`
para desactivarla.

Además, la conexión al **servidor eD2k** se **mantiene abierta** entre búsquedas
(un único login en vez de uno por consulta — los servidores penalizan el login
repetido como abuso) y el **pool de contactos de Kad** se reutiliza para no
re-bootstrapear. Ambos se cierran/descartan tras `AMARR_SEARCH_IDLE_TIMEOUT`
segundos sin búsquedas (10 min por defecto; `0` = conectar/descartar por consulta).

Cada resultado incluye además un **enlace de información** (elemento `<comments>`)
que Sonarr/Radarr muestran junto al release; abre una página `GET /details` en
amarr con los datos del fichero, el enlace **eD2k** y el **magnet**.

## Depuración

Si una búsqueda no devuelve resultados, activa el modo **DEBUG** y repítela:

```
AMARR_LOG_LEVEL: DEBUG
```

En DEBUG, además de los logs de amarr, se incluyen:

- Las trazas internas de los motores eD2k/Kad (loggers `ed2k.*`): conexión y
  login al servidor eD2k, bootstrap y rondas de Kad, paquetes enviados/recibidos.
- La consulta tras normalizarla y, por motor, cuántos resultados **crudos**
  llegan y cuántos quedan **tras el filtro de vídeo**. Esto distingue el origen
  del problema: si llegan crudos pero 0 relevantes, es el filtro de vídeo; si
  llegan 0 crudos, es el motor/servidor (p. ej. servidor eD2k caído, `nodes.dat`
  obsoleto o aMule sin conexión a la red).
- El *traceback* completo de los errores capturados.
- Si la respuesta vino de la **caché** (`Caché HIT`) o se relanzó la búsqueda
  (`Caché MISS`).

Los logs salen por la salida estándar; en Docker, `docker logs -f amarr`.

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
