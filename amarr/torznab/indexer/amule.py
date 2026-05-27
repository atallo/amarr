"""Indexador Torznab respaldado por aMule (``torznab/indexer/AmuleIndexer.kt``).

Traduce las búsquedas de Sonarr/Radarr a búsquedas en aMule y filtra los
resultados para quedarse sólo con vídeo relevante.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import List, Optional

from ...jamule.client import AmuleClient
from ...jamule.response import SearchFile
from ...magnet import MagnetLink
from ..models import Channel, Enclosure, Feed, Item, Response, TorznabAttribute
from .base import Indexer

# Extensiones consideradas vídeo.
_VIDEO_EXTENSIONS = {
    "avi", "m2ts", "m4v", "mkv", "mov", "mp4",
    "mpeg", "mpg", "ts", "webm", "wmv",
}
# Extensiones excluidas explícitamente.
_EXCLUDED_EXTENSIONS = {
    "ass", "cue", "gif", "jpg", "jpeg", "m3u", "mp3",
    "nfo", "png", "rar", "srt", "sub", "txt", "zip",
}
# Tamaño mínimo para aceptar un fichero sin extensión como vídeo (50 MiB).
_MIN_VIDEO_SIZE_BYTES = 50 * 1024 * 1024

_COMBINING_RE = re.compile(r"[\u0300-\u036f]+")
_NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


class AmuleIndexer(Indexer):
    def __init__(
        self, amule_client: AmuleClient, logger: Optional[logging.Logger] = None
    ) -> None:
        self._amule = amule_client
        self._log = logger or logging.getLogger("amarr.torznab.amule")

    def search(self, query: str, offset: int, limit: int, cat: List[int]) -> Feed:
        self._log.debug(
            "Starting search for query: %s, offset: %s, limit: %s", query, offset, limit
        )
        if not query.strip():
            self._log.debug("Empty query, returning empty response")
            return _empty_query_response()
        clean_query = self._normalize_search_query(query)
        results = self._amule.search_sync(clean_query).files
        relevant = [f for f in results if self._is_relevant_video_result(f)]
        return self._build_feed(relevant, offset, limit)

    def capabilities(self):
        from ..models import Caps

        return Caps()

    # --- internos -----------------------------------------------------------

    def _is_relevant_video_result(self, file: SearchFile) -> bool:
        if "." in file.file_name:
            extension = file.file_name.rsplit(".", 1)[-1].lower()
        else:
            extension = ""
        if extension in _EXCLUDED_EXTENSIONS:
            return False
        return extension in _VIDEO_EXTENSIONS or (
            extension == "" and file.size_full >= _MIN_VIDEO_SIZE_BYTES
        )

    @staticmethod
    def _normalize_search_query(query: str) -> str:
        # NFD + eliminación de diacríticos, sustitución de símbolos por espacios
        # y colapso de espacios, igual que el original en Kotlin.
        decomposed = unicodedata.normalize("NFD", query)
        without_marks = _COMBINING_RE.sub("", decomposed)
        spaced = _NON_WORD_RE.sub(" ", without_marks)
        collapsed = _WHITESPACE_RE.sub(" ", spaced)
        return collapsed.strip()

    @staticmethod
    def _build_feed(items: List[SearchFile], offset: int, limit: int) -> Feed:
        page = items[offset : offset + limit]
        feed_items = [
            Item(
                title=result.file_name,
                enclosure=Enclosure(
                    url=str(
                        MagnetLink.for_amarr(
                            result.hash, result.file_name, result.size_full
                        )
                    ),
                    length=result.size_full,
                ),
                attributes=[
                    TorznabAttribute("category", "1"),
                    TorznabAttribute("seeders", str(result.complete_source_count)),
                    TorznabAttribute("peers", str(result.source_count)),
                    TorznabAttribute("size", str(result.size_full)),
                ],
            )
            for result in page
        ]
        return Feed(
            channel=Channel(
                response=Response(offset=offset, total=len(items)),
                item=feed_items,
            )
        )


def _empty_query_response() -> Feed:
    return Feed(
        channel=Channel(
            response=Response(offset=0, total=1),
            item=[
                Item(
                    title="No query provided",
                    enclosure=Enclosure("http://mock.url", 0),
                    attributes=[
                        TorznabAttribute("category", "1"),
                        TorznabAttribute("size", "0"),
                    ],
                )
            ],
        )
    )
