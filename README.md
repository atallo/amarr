# Amarr - aMule connector for *arr (Python port)

This connector lets you use **aMule** as a download client for
[Sonarr](https://sonarr.tv/) and [Radarr](https://radarr.video/). It works by
**emulating a torrent client** (the qBittorrent WebAPI v2.8.19), so that
Sonarr/Radarr manage your downloads as if they were torrents, and it also
exposes **Torznab** endpoints for search.

It is a **Python** translation of the original project written in Kotlin.
Communication with aMule uses the binary **EC (External Connection)** protocol,
also ported to Python from the
[jaMule](https://github.com/vexdev/jaMule) library.

## Prerequisites

- [aMule](https://www.amule.org/) running and configured (with the EC connection enabled).
  Tested with aMule 3.0.0 and some earlier versions.
- [Sonarr](https://sonarr.tv/) or [Radarr](https://radarr.video/) running.

**Amarr does not include its own aMule installation**: you need aMule running
separately (for example with the Docker image from
[ngosang](https://github.com/ngosang/docker-amule).

## Installation

Amarr runs as a Docker container. The image is published on **GitHub
Container Registry (ghcr.io)**:

```
ghcr.io/atallo/amarr:latest
```

### Environment variables

```
AMULE_HOST: aMule       # Host where aMule runs (in Docker it's usually the container name)
AMULE_PORT: 4712        # aMule EC port
AMULE_PASSWORD: secret  # aMule connection password

Optional:
AMULE_FINISHED_PATH: /finished  # Folder where aMule leaves finished files
AMARR_PORT: 8080                # Port amarr listens on (default 8080)
AMARR_LOG_LEVEL: INFO           # Log level: DEBUG, INFO, WARN, ERROR (default INFO)
AMARR_LOG_FILE:                 # If set (e.g. /config/amarr.log), the log goes to that file (with rotation) instead of stdout
AMARR_LOG_MAX_BYTES: 5242880    # Maximum log size before rotating (default 5 MiB)
AMARR_LOG_BACKUPS: 3            # Number of rotated log files to keep (default 3)
AMARR_CONFIG_PATH: /config      # Persistent configuration folder (default /config)

Search engines (see "Indexers and search engines"):
AMARR_SEARCH_BACKENDS: amule          # Active engines, comma-separated list: amule,ed2k,kad (default amule)
AMARR_ED2K_SERVER: 45.82.80.155:5687  # eD2k server for the "ed2k" engine (host:port)
AMARR_KAD_NODES: /config/nodes.dat    # nodes.dat for "kad" (default: /config/nodes.dat or the bundled one)
AMARR_KAD_IP_ORDER: be                # IP byte order in nodes.dat: be or le (default be)
AMARR_KAD_WITH_SOURCES: false         # Kad: count real sources per file (slow; default false)
AMARR_CACHE_TTL: 3600                 # Search cache in seconds (0 = disable; default 3600 = 1 h)
AMARR_SEARCH_IDLE_TIMEOUT: 600        # Keep the eD2k connection / Kad pool alive N s without searches (0 = no; default 600 = 10 min)
```

### Volumes

```
/config   # Persistent. Stores the SQLite category DB (amarr.db) and the
          # search cache (cache.db, regenerable).
```

> In earlier versions amarr used `categories.tsv`/`hashes.tsv` files. When
> starting with this version, those files are renamed to `*.tsv.bak` (they are
> not imported; the database starts empty).

The container exposes port **8080**, where amarr serves the qBittorrent API
and the Torznab server for Sonarr/Radarr.

### `docker-compose.yml` example

```yaml
services:
  amarr:
    image: ghcr.io/atallo/amarr:latest
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

## Radarr/Sonarr configuration (2 steps)

### 1. Configure amarr as a download client

Add a new download client of type **qBittorrent** with these settings
(click "Show advanced settings" first):

```
Name: whatever you like
Host: amarr      # Host where amarr runs (in Docker, the container name)
Port: 8080       # Port amarr listens on
Priority: 50     # Lowest possible priority so other clients are preferred
```

### 2. Configure amarr as a Torznab indexer

Add a new **Torznab indexer** with these settings:

```
Name: whatever you like
Url: http://amarr:8080/indexer/amule   # or /indexer/ed2k, /indexer/kad, /indexer/all (see Indexers)
Download Client: the name you gave amarr in the previous step
```

## Indexers and search engines

amarr can search with three engines, enabled via `AMARR_SEARCH_BACKENDS`
(comma-separated list, at least one):

- **`amule`** — Searches through an **external aMule** (EC protocol), as before.
  Requires aMule running.
- **`ed2k`** — Searches directly on an **eD2k server**, implemented by amarr
  (100% Python, no aMule needed for search). Server configurable with
  `AMARR_ED2K_SERVER`.
- **`kad`** — Searches the **Kad network** (serverless), implemented by amarr. Uses a
  `nodes.dat` (`AMARR_KAD_NODES`; a default one is bundled).

Each active engine exposes its own Torznab endpoint, and there is also an `all`
endpoint that **aggregates** the results of all active engines:

```
http://amarr:8080/indexer/amule    # aMule only
http://amarr:8080/indexer/ed2k     # eD2k server only
http://amarr:8080/indexer/kad      # Kad only
http://amarr:8080/indexer/all      # all active engines, combined
```

In Sonarr/Radarr, use the URL of whichever engine you want as the indexer URL
(or `all`). Whatever the search engine, **the download is always performed by
aMule**, so aMule must remain configured and running.

> Results from the eD2k/Kad network are not well moderated (you may end up
> downloading fake files). The `kad` engine can take a while per query.
>
> **Note:** the `ddunlimitednet` indexer from the original project has **not**
> been included in this Python port.

The results of each search are **cached** in `cache.db` for
`AMARR_CACHE_TTL` seconds (1 h by default), keyed by `(engine, query)`, so that
Sonarr/Radarr pagination and repeated searches don't re-run the query —
important especially for Kad, which is slow. Set `AMARR_CACHE_TTL=0`
to disable it.

In addition, the connection to the **eD2k server** is **kept open** between
searches (a single login instead of one per query — servers penalize repeated
logins as abuse) and the **Kad contact pool** is reused to avoid
re-bootstrapping. Both are closed/discarded after `AMARR_SEARCH_IDLE_TIMEOUT`
seconds without searches (10 min by default; `0` = connect/discard per query).

Each result also includes an **info link** (a `<comments>` element)
that Sonarr/Radarr show alongside the release; it opens a `GET /details` page in
amarr with the file data, the **eD2k** link and the **magnet**.

## Debugging

If a search returns no results, enable **DEBUG** mode and repeat it:

```
AMARR_LOG_LEVEL: DEBUG
```

In DEBUG, besides amarr's own logs, the following are included:

- The internal traces of the eD2k/Kad engines (`ed2k.*` loggers): connection and
  login to the eD2k server, Kad bootstrap and rounds, packets sent/received.
- The query after normalizing it and, per engine, how many **raw** results
  arrive and how many remain **after the video filter**. This pinpoints the
  source of the problem: if raw results arrive but 0 are relevant, it's the video
  filter; if 0 raw results arrive, it's the engine/server (e.g. eD2k server down,
  stale `nodes.dat` or aMule not connected to the network).
- The full *traceback* of caught errors.
- Whether the response came from the **cache** (`Cache HIT`) or the search was
  re-run (`Cache MISS`).

Logs go to standard output; in Docker, `docker logs -f amarr`.

If DEBUG mode floods the Docker log, set `AMARR_LOG_FILE` (e.g.
`/config/amarr.log`): the amarr/ed2k detail is written to that file (with
rotation, see `AMARR_LOG_MAX_BYTES`/`AMARR_LOG_BACKUPS`) and stops going to stdout.

## Development

Requires Python 3.11 or higher.

```bash
# Install the dependencies (including the development ones)
pip install -e ".[dev]"

# Run the tests
pytest

# Start the server locally (reads the configuration from the environment)
AMULE_HOST=localhost AMULE_PORT=4712 AMULE_PASSWORD=secret python -m amarr.app
```

## Architecture notes (Python port)

- **Web server:** **FastAPI + uvicorn** is used instead of Ktor. The qBittorrent
  API responds in JSON/text and the Torznab one in XML.
- **Synchronous EC client:** the EC protocol has been ported **synchronously**
  (sockets + `struct` + `hashlib` + `zlib`), protected with a lock. The
  FastAPI handlers that touch aMule are `def` (not `async`) functions, so
  Starlette runs them in its *threadpool* and they don't block the event loop.
- **Models:** **pydantic v2** is used (equivalent to the serializable
  `data class`es of the original).
- **Protocol compatibility:** the implementation has been validated byte by byte
  against the jaMule test vectors (authentication, search, status and
  password hash).
- **Publishing:** the image is published to **ghcr.io** via GitHub Actions
  (`.github/workflows/release.yml`), using the built-in `GITHUB_TOKEN`.

## License

MIT.
