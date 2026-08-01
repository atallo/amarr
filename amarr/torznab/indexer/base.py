"""Indexer interface and common Torznab pipeline (``torznab/indexer/*.kt``).

``Indexer`` centralizes everything the search engines share
(query normalization, video filtering, feed building, caps and
error handling). Each concrete engine only implements :meth:`Indexer._raw_search`,
which returns a list of :class:`SearchFile` (the common internal model).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional
from urllib.parse import quote

from ...jamule.response import SearchFile
from ...magnet import MagnetLink
from ..models import Caps, Channel, Enclosure, Feed, Item, Response, TorznabAttribute

if TYPE_CHECKING:
    from ...cache import SearchCache


class ThrottledException(Exception):
    """The indexer is rate-limiting requests (translated to HTTP 403)."""


class UnauthorizedException(Exception):
    """Invalid credentials (translated to HTTP 401)."""


# Extensions considered video.
_VIDEO_EXTENSIONS = {
    "avi", "m2ts", "m4v", "mkv", "mov", "mp4",
    "mpeg", "mpg", "ts", "webm", "wmv",
}
# Explicitly excluded extensions.
_EXCLUDED_EXTENSIONS = {
    "ass", "cue", "gif", "jpg", "jpeg", "m3u", "mp3",
    "nfo", "png", "rar", "srt", "sub", "txt", "zip",
}
# Minimum size to accept an extensionless file as video (50 MiB).
_MIN_VIDEO_SIZE_BYTES = 50 * 1024 * 1024

_NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")

# Engine errors that must not take down the response to Sonarr/Radarr: they are
# logged and an empty feed is returned (a downed eD2k server or an invalid
# nodes.dat must not cause a 500).
_SEARCH_ERRORS = (OSError, ValueError)


class Indexer(ABC):
    """Source of search results in Torznab format.

    Implements the common pipeline; subclasses only provide ``_raw_search``.
    """

    #: Title advertised in the capabilities (``caps``); subclasses fine-tune it.
    server_title: str = "Amarr"
    #: Engine identifier for the cache; empty = not cached.
    cache_key: str = ""

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        cache: "Optional[SearchCache]" = None,
    ) -> None:
        self._log = logger or logging.getLogger("amarr.torznab.indexer")
        self._cache = cache

    # --- public API ---------------------------------------------------------

    def search(
        self, query: str, offset: int, limit: int, cat: List[int], base_url: str = ""
    ) -> Feed:
        self._log.debug(
            "Starting search for query: %s, offset: %s, limit: %s", query, offset, limit
        )
        if not query.strip():
            self._log.debug("Empty query, returning empty response")
            return _empty_query_response()
        clean_query = self._normalize_search_query(query)
        self._log.debug("Normalized query: %r -> %r", query, clean_query)
        results = self._raw_search_cached(clean_query)
        relevant = [f for f in results if self._is_relevant_video_result(f)]
        self._log.debug(
            "Results for %r: %d raw, %d relevant after the video filter",
            clean_query,
            len(results),
            len(relevant),
        )
        return self._build_feed(relevant, offset, limit, base_url)

    def _raw_search_cached(self, query: str) -> List[SearchFile]:
        """``_raw_search`` with a TTL cache keyed by ``(cache_key, query)``.

        Network/data errors are logged and return an empty list: they are **not**
        cached, so the next request retries.
        """
        use_cache = self._cache is not None and bool(self.cache_key)
        if use_cache:
            hit = self._cache.get(self.cache_key, query)
            if hit is not None:
                self._log.debug(
                    "Cache HIT (%s, %r): %d results", self.cache_key, query, len(hit)
                )
                return hit
        try:
            results = self._raw_search(query)
        except _SEARCH_ERRORS as exc:
            # In DEBUG the full traceback is included to help debug.
            self._log.warning(
                "The search failed (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=self._log.isEnabledFor(logging.DEBUG),
            )
            return []
        if use_cache:
            self._cache.put(self.cache_key, query, results)
            self._log.debug(
                "Cache MISS (%s, %r): stored %d results",
                self.cache_key,
                query,
                len(results),
            )
        return results

    def capabilities(self) -> Caps:
        return Caps(server_title=self.server_title)

    # --- to be implemented by each engine ----------------------------------

    @abstractmethod
    def _raw_search(self, query: str) -> List[SearchFile]:
        """Runs the raw search on the concrete engine (the query is already
        normalized). It may raise network/data errors; the pipeline catches them.
        """

    # --- shared helpers -----------------------------------------------------

    @staticmethod
    def _is_relevant_video_result(file: SearchFile) -> bool:
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
        # NFD + removal of diacritics (any combining mark), replacement of
        # symbols with spaces and whitespace collapsing. Equivalent to the Kotlin
        # original and to ``core._fold`` of the ed2k library.
        decomposed = unicodedata.normalize("NFD", query)
        without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
        spaced = _NON_WORD_RE.sub(" ", without_marks)
        collapsed = _WHITESPACE_RE.sub(" ", spaced)
        return collapsed.strip()

    @staticmethod
    def _build_feed(
        items: List[SearchFile], offset: int, limit: int, base_url: str = ""
    ) -> Feed:
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
                comments=_details_url(base_url, result),
            )
            for result in page
        ]
        return Feed(
            channel=Channel(
                response=Response(offset=offset, total=len(items)),
                item=feed_items,
            )
        )


def _details_url(base_url: str, result: SearchFile) -> str:
    """URL of amarr's details page for a result.

    Sonarr/Radarr show it as an *info link*. It is empty if there is no ``base_url``
    (e.g. in tests), in which case no ``<comments>`` is emitted.
    """
    if not base_url:
        return ""
    return (
        f"{base_url}/details?hash={result.hash.hex()}"
        f"&name={quote(result.file_name)}"
        f"&size={result.size_full}"
        f"&seeders={result.complete_source_count}"
        f"&peers={result.source_count}"
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
