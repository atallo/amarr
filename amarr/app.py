"""Fábrica de la aplicación FastAPI y punto de entrada (``amarr/App.kt``).

Conecta el cliente aMule, el almacén de categorías y los routers (qBittorrent,
Torznab y depuración). Los indexers Torznab activos se eligen con
``AMARR_SEARCH_BACKENDS`` (``amule``/``ed2k``/``kad``); la descarga siempre pasa
por aMule. Equivale a ``Application.app()`` de Kotlin.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from . import ed2k as _ed2k_pkg
from .amule.debug_api import build_debug_router
from .cache import SearchCache
from .category.store import CategoryStore, SqliteCategoryStore
from .config import (
    amarr_port,
    cache_ttl,
    optional_env,
    required_env,
    search_backends,
    search_idle_timeout,
    set_log_level,
)
from .ed2k import DEFAULT_SERVER
from .homepage import build_home_router
from .jamule.client import AmuleClient
from .torrent.api import build_torrent_router
from .torrent.service import NotFoundException
from .torznab.api import build_torznab_router
from .torznab.indexer.amule import AmuleIndexer
from .torznab.indexer.base import Indexer
from .torznab.indexer.ed2k_server import Ed2kServerIndexer
from .torznab.indexer.kad import KadIndexer

_log = logging.getLogger("amarr")

# nodes.dat empaquetado con amarr (fallback por defecto para Kad).
_PACKAGED_NODES = os.path.join(os.path.dirname(_ed2k_pkg.__file__), "data", "nodes.dat")


def create_app(
    amule_client: AmuleClient,
    category_store: CategoryStore,
    finished_path: str,
    indexers: dict[str, Indexer],
) -> FastAPI:
    """Construye la app a partir de sus dependencias (útil para tests)."""
    app = FastAPI(title="Amarr", docs_url=None, redoc_url=None)

    app.include_router(build_home_router(list(indexers.keys())))
    app.include_router(build_debug_router(amule_client))
    app.include_router(build_torznab_router(indexers))
    app.include_router(
        build_torrent_router(amule_client, category_store, finished_path)
    )

    @app.exception_handler(NotFoundException)
    async def _not_found_handler(request: Request, exc: NotFoundException):
        return PlainTextResponse(str(exc), status_code=404)

    return app


def build_client(logger: logging.Logger = _log) -> AmuleClient:
    """Crea el cliente aMule a partir de variables de entorno obligatorias."""
    return AmuleClient.connect(
        host=required_env("AMULE_HOST"),
        port=int(required_env("AMULE_PORT")),
        password=required_env("AMULE_PASSWORD"),
        logger=logger,
    )


def _kad_nodes_path() -> str:
    """Ruta del ``nodes.dat`` para Kad: ``AMARR_KAD_NODES`` si está definida; si
    no, ``<config>/nodes.dat`` si existe; en último término, el empaquetado."""
    explicit = optional_env("AMARR_KAD_NODES", "")
    if explicit:
        return explicit
    config_nodes = os.path.join(
        optional_env("AMARR_CONFIG_PATH", "/config"), "nodes.dat"
    )
    if os.path.exists(config_nodes):
        return config_nodes
    return _PACKAGED_NODES


def build_indexers(
    amule_client: AmuleClient, cache: Optional[SearchCache] = None
) -> dict[str, Indexer]:
    """Construye los indexers activos según ``AMARR_SEARCH_BACKENDS``."""
    idle = search_idle_timeout()
    indexers: dict[str, Indexer] = {}
    for name in search_backends():
        if name == "amule":
            indexers["amule"] = AmuleIndexer(amule_client, _log, cache=cache)
        elif name == "ed2k":
            indexers["ed2k"] = Ed2kServerIndexer(
                server=optional_env("AMARR_ED2K_SERVER", DEFAULT_SERVER),
                idle_seconds=idle,
                cache=cache,
            )
        elif name == "kad":
            indexers["kad"] = KadIndexer(
                nodes_path=_kad_nodes_path(),
                ip_order=optional_env("AMARR_KAD_IP_ORDER", "be"),
                with_sources=optional_env("AMARR_KAD_WITH_SOURCES", "false").lower()
                == "true",
                idle_seconds=idle,
                cache=cache,
            )
    return indexers


def build_app_from_env() -> FastAPI:
    """Construye la app leyendo toda la configuración del entorno."""
    set_log_level(optional_env("AMARR_LOG_LEVEL", "INFO"))
    config_path = optional_env("AMARR_CONFIG_PATH", "/config")
    amule_client = build_client(_log)
    category_store = SqliteCategoryStore(config_path)
    cache = SearchCache(config_path, cache_ttl())
    finished_path = optional_env("AMULE_FINISHED_PATH", "/finished")
    indexers = build_indexers(amule_client, cache)
    return create_app(amule_client, category_store, finished_path, indexers)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    port = amarr_port()
    app = build_app_from_env()
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
