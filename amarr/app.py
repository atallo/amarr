"""Fábrica de la aplicación FastAPI y punto de entrada (``amarr/App.kt``).

Conecta el cliente aMule, el almacén de categorías y los tres routers (qBittorrent,
Torznab y depuración). Equivale a ``Application.app()`` de Kotlin.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from .amule.debug_api import build_debug_router
from .category.store import CategoryStore, FileCategoryStore
from .config import amarr_port, optional_env, required_env, set_log_level
from .jamule.client import AmuleClient
from .torrent.api import build_torrent_router
from .torrent.service import NotFoundException
from .torznab.api import build_torznab_router
from .torznab.indexer.amule import AmuleIndexer

_log = logging.getLogger("amarr")


def create_app(
    amule_client: AmuleClient,
    category_store: CategoryStore,
    finished_path: str,
) -> FastAPI:
    """Construye la app a partir de sus dependencias (útil para tests)."""
    app = FastAPI(title="Amarr", docs_url=None, redoc_url=None)

    amule_indexer = AmuleIndexer(amule_client, _log)

    app.include_router(build_debug_router(amule_client))
    app.include_router(build_torznab_router(amule_indexer))
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


def build_app_from_env() -> FastAPI:
    """Construye la app leyendo toda la configuración del entorno."""
    set_log_level(optional_env("AMARR_LOG_LEVEL", "INFO"))
    amule_client = build_client(_log)
    category_store = FileCategoryStore(optional_env("AMARR_CONFIG_PATH", "/config"))
    finished_path = optional_env("AMULE_FINISHED_PATH", "/finished")
    return create_app(amule_client, category_store, finished_path)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    port = amarr_port()
    app = build_app_from_env()
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
