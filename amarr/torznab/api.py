"""FastAPI router for the Torznab API (``torznab/TorznabApi.kt``).

Exposes the endpoints Sonarr/Radarr use as an indexer. Returns XML.
The ddunlimitednet part of the original is deliberately omitted in this
migration.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response as FastAPIResponse

from .indexer.aggregate import AggregateIndexer
from .indexer.base import Indexer, ThrottledException, UnauthorizedException
from .models import Channel, Feed, Response as FeedResponse

_log = logging.getLogger("amarr.torznab.api")

_XML_MEDIA_TYPE = "application/xml"


class _SearchMode(Enum):
    DEFAULT = "default"
    TV = "tv"


def build_torznab_router(indexers: dict[str, Indexer]) -> APIRouter:
    """Mounts one Torznab endpoint per active engine, plus ``/indexer/all`` (which
    aggregates all active ones) and the legacy ``/api`` route.

    ``indexers`` maps the engine name (``amule``/``ed2k``/``kad``) to its
    :class:`Indexer`.
    """
    router = APIRouter()

    def handle(request: Request, indexer: Indexer) -> FastAPIResponse:
        _log.debug("Handling torznab request")
        action = request.query_params.get("t")
        if action is None:
            # Same as the original: missing action -> error -> HTTP 500.
            raise ValueError("Missing action")
        if action == "caps":
            _log.debug("Handling caps request")
            return FastAPIResponse(
                content=indexer.capabilities().to_xml(), media_type=_XML_MEDIA_TYPE
            )
        if action == "tvsearch":
            return _perform_search(request, indexer, _SearchMode.TV)
        if action == "movie":
            return _perform_search(request, indexer, _SearchMode.DEFAULT)
        if action == "search":
            return _perform_search(request, indexer, _SearchMode.DEFAULT)
        raise ValueError(f"Unknown action: {action}")

    def make_endpoint(indexer: Indexer):
        # Closure per indexer (avoids late-binding of the loop variable).
        def endpoint(request: Request) -> FastAPIResponse:
            return handle(request, indexer)

        return endpoint

    # One endpoint per active engine: /indexer/<name>/api
    for name, indexer in indexers.items():
        router.add_api_route(
            f"/indexer/{name}/api", make_endpoint(indexer), methods=["GET"]
        )

    # Aggregator endpoint: /indexer/all/api (combines the active engines).
    aggregate = AggregateIndexer(list(indexers.values()))
    router.add_api_route("/indexer/all/api", make_endpoint(aggregate), methods=["GET"])

    # Legacy route: /api -> amule if active, otherwise the aggregator.
    legacy = indexers.get("amule", aggregate)
    router.add_api_route("/api", make_endpoint(legacy), methods=["GET"])

    return router


def _perform_search(
    request: Request, indexer: Indexer, mode: _SearchMode
) -> FastAPIResponse:
    params = request.query_params
    query = params.get("q", "")
    offset = _to_int(params.get("offset"), 0)
    limit = _to_int(params.get("limit"), 100)
    cat_param = params.get("cat")
    cat = [int(c) for c in cat_param.split(",")] if cat_param else []

    queries = _search_queries(request, query, mode)
    base_url = str(request.base_url).rstrip("/")
    _log.debug(
        "Handling search request: %s, %s, %s, %s", queries, offset, limit, cat
    )
    try:
        feed = _perform_queries(indexer, queries, offset, limit, cat, base_url)
        return FastAPIResponse(content=feed.to_xml(), media_type=_XML_MEDIA_TYPE)
    except ThrottledException:
        _log.warning("Throttled, returning 403")
        return PlainTextResponse(
            "You are being throttled. Retry in a few minutes.", status_code=403
        )
    except UnauthorizedException:
        _log.warning("Unauthorized, returning 401")
        return PlainTextResponse(
            "Unauthorized, check your credentials.", status_code=401
        )


def _perform_queries(
    indexer: Indexer,
    queries: List[str],
    offset: int,
    limit: int,
    cat: List[int],
    base_url: str = "",
) -> Feed:
    if len(queries) == 1:
        return indexer.search(queries[0], offset, limit, cat, base_url)

    # For multiple queries (TV): all are requested from 0 up to offset+limit,
    # merged, deduplicated by URL and paginated manually.
    raw_limit = offset + limit
    seen = set()
    merged: List = []
    for q in queries:
        for item in indexer.search(q, 0, raw_limit, cat, base_url).channel.item:
            if item.enclosure.url not in seen:
                seen.add(item.enclosure.url)
                merged.append(item)
    page = merged[offset : offset + limit]
    return Feed(
        channel=Channel(
            response=FeedResponse(offset=offset, total=len(merged)),
            item=page,
        )
    )


def _search_queries(request: Request, query: str, mode: _SearchMode) -> List[str]:
    if mode != _SearchMode.TV or not query.strip():
        return [query]
    season = _to_int_or_none(request.query_params.get("season"))
    episode = _to_int_or_none(request.query_params.get("episode"))
    if season is None or episode is None:
        return [query]
    padded_season = str(season).zfill(2)
    padded_episode = str(episode).zfill(2)
    return [
        f"{query} S{padded_season}E{padded_episode}",
        f"{query} {season}x{padded_episode}",
        f"{query} {season}{padded_episode}",
    ]


def _to_int(value: Optional[str], default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _to_int_or_none(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
