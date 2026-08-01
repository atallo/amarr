# Changelog

All notable changes to this project are documented here.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## v0.0.3 - 2026-08-01

First feature release on top of the Python port. It turns amarr from a plain
aMule proxy into a multi-engine search connector, adds a web UI and search
caching, and completes the English translation of the whole codebase.

### Added

- **Multi-engine search.** Choose the active engines with `AMARR_SEARCH_BACKENDS`
  (`amule`, `ed2k`, `kad`). Each active engine gets its own Torznab endpoint
  (`/indexer/amule`, `/indexer/ed2k`, `/indexer/kad`) plus an `/indexer/all`
  endpoint that aggregates and de-duplicates the results of all of them.
- **Built-in eD2k/Kad library** (`amarr/ed2k`), a 100% Python implementation of
  eD2k server search (TCP) and Kad search (serverless, UDP) with no external
  dependencies. Downloading still always goes through aMule.
- **Home page** (`GET /`) that documents only the active endpoints, with a
  collapsible request/response example for each one.
- **Details page** (`GET /details`) with the file data, the real **eD2k magnet**
  (`urn:ed2k`) and eD2k link, plus the synthetic *Fake Magnet* handed to
  Sonarr/Radarr. Each feed result now carries an **info link** (`<comments>`)
  pointing to it.
- **Search cache** (`cache.db`) keyed by `(engine, query)` with a configurable
  TTL (`AMARR_CACHE_TTL`, default 1 h), so pagination and repeated searches are
  served instantly — important for the slow Kad engine.
- **Persistent search sessions.** The eD2k connection is kept open between
  searches (a single login instead of one per query) and the Kad contact pool is
  reused to avoid re-bootstrapping; both are discarded after
  `AMARR_SEARCH_IDLE_TIMEOUT` (default 10 min).
- **DEBUG mode.** `AMARR_LOG_LEVEL=DEBUG` now also enables the internal traces of
  the eD2k/Kad engines and logs the normalized query, raw vs. video-filtered
  result counts, cache HIT/MISS and full tracebacks of caught errors.
- **Optional file logging with rotation** (`AMARR_LOG_FILE`,
  `AMARR_LOG_MAX_BYTES`, `AMARR_LOG_BACKUPS`) so DEBUG mode doesn't flood the
  Docker log; the log file is reopened if it is deleted or rotated externally.

### Fixed

- Category store corruption and a division-by-zero in progress calculation.
- Tolerate missing EC tags in part-files, which caused a 500 on
  `GET /api/v2/torrents/info` when there were active downloads.
- CI test compatibility with newer FastAPI: served routes are now enumerated from
  the OpenAPI schema instead of walking `app.routes`.

### Changed

- The whole repository (code comments, docstrings, UI/log strings, README and CI
  config) is now in **English**.

### New environment variables

`AMARR_SEARCH_BACKENDS`, `AMARR_ED2K_SERVER`, `AMARR_KAD_NODES`,
`AMARR_KAD_IP_ORDER`, `AMARR_KAD_WITH_SOURCES`, `AMARR_CACHE_TTL`,
`AMARR_SEARCH_IDLE_TIMEOUT`, `AMARR_LOG_FILE`, `AMARR_LOG_MAX_BYTES`,
`AMARR_LOG_BACKUPS`. See the README for details.

## v0.0.2 - 2026-05-27

- Initial **Python port** of the original Kotlin project: qBittorrent WebAPI
  emulation + Torznab indexer backed by an external aMule over the binary EC
  protocol.

## v0.0.1

- Legacy release of the original Kotlin implementation.
