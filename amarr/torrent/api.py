"""Router FastAPI que emula la WebAPI de qBittorrent (``TorrentApi.kt``).

Sonarr/Radarr usan estas rutas creyendo que hablan con qBittorrent v2.8.19.
Los handlers son **síncronos** (``def``) a propósito: el cliente aMule es
bloqueante (sockets), así que Starlette los ejecuta en su threadpool y no
bloquean el bucle de eventos.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from ..category.store import CategoryStore
from ..jamule.client import AmuleClient
from .models import Category, Preferences
from .service import TorrentService

_log = logging.getLogger("amarr.torrent.api")


def build_torrent_router(
    amule_client: AmuleClient,
    category_store: CategoryStore,
    finished_path: str,
) -> APIRouter:
    service = TorrentService(amule_client, category_store, finished_path, _log)
    router = APIRouter()

    @router.get("/api/v2/app/webapiVersion")
    def webapi_version() -> PlainTextResponse:
        # Emula la versión de la API de qBittorrent 2.8.19.
        return PlainTextResponse("2.8.19")

    @router.post("/api/v2/auth/login")
    def login(
        username: Optional[str] = Form(default=None),
        password: Optional[str] = Form(default=None),
    ) -> PlainTextResponse:
        # TODO: implementar algún tipo de autenticación (igual que el original).
        return PlainTextResponse("Ok.")

    @router.get("/api/v2/app/preferences")
    def preferences() -> JSONResponse:
        prefs = Preferences(save_path=finished_path)
        return JSONResponse(prefs.model_dump())

    @router.post("/api/v2/torrents/add")
    def add_torrent(
        urls: Optional[str] = Form(default=None),
        category: Optional[str] = Form(default=None),
        paused: Optional[str] = Form(default=None),
    ) -> PlainTextResponse:
        url_list = None
        if urls is not None:
            url_list = [u for u in urls.split("\n") if u.strip()]
        _log.debug(
            "Received add torrent request with urls: %s, category: %s, paused: %s",
            url_list,
            category,
            paused,
        )
        service.add_torrent(url_list, category, paused)
        return PlainTextResponse("Ok.")

    @router.post("/api/v2/torrents/createCategory")
    def create_category(
        category: str = Form(...),
        savePath: Optional[str] = Form(default=""),
    ) -> PlainTextResponse:
        cat = Category(category, savePath or "")
        _log.debug("Received create category request with category: %s", cat)
        service.add_category(cat)
        return PlainTextResponse("Ok.")

    @router.get("/api/v2/torrents/categories")
    def categories() -> JSONResponse:
        cats = service.get_categories()
        return JSONResponse({name: c.to_json() for name, c in cats.items()})

    @router.get("/api/v2/torrents/info")
    def torrents_info(category: Optional[str] = Query(default=None)) -> JSONResponse:
        infos = service.get_torrent_info(category)
        return JSONResponse([t.model_dump() for t in infos])

    @router.post("/api/v2/torrents/delete")
    def delete_torrent(
        hashes: str = Form(...),
        deleteFiles: Optional[str] = Form(default=None),
    ) -> PlainTextResponse:
        hash_list = hashes.split("|")
        _log.debug(
            "Received delete torrent request with hashes: %s, deleteFiles: %s",
            hash_list,
            deleteFiles,
        )
        if len(hash_list) == 1 and hash_list[0] == "all":
            service.delete_all_torrents(deleteFiles)
        else:
            service.delete_torrent(hash_list, deleteFiles)
        return PlainTextResponse("Ok.")

    @router.get("/api/v2/torrents/files")
    def torrent_files(hash: str = Query(...)) -> JSONResponse:
        _log.debug("Received get files request with hash: %s", hash)
        response = [service.get_file(hash).model_dump()]
        return JSONResponse(response)

    @router.get("/api/v2/torrents/properties")
    def torrent_properties(hash: str = Query(...)) -> JSONResponse:
        _log.debug("Received get properties request with hash: %s", hash)
        return JSONResponse(service.get_torrent_properties(hash).model_dump())

    return router
