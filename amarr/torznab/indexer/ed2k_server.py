"""Torznab indexer that searches an eD2k server (``amarr.ed2k.ServerSearch``).

100% Python search over TCP, independent of aMule. Downloading still goes
through aMule (the resulting magnet is handed to it via the qBittorrent API).
"""
from __future__ import annotations

import logging
from typing import Callable, List, Optional

from ...ed2k import DEFAULT_SERVER, SearchResult
from ...ed2k_session import Ed2kServerSession
from ...jamule.response import SearchFile
from ._results import to_search_files
from .base import Indexer

# Search engine signature; injectable so it can be tested without a network.
SearchFn = Callable[[str], List[SearchResult]]


class Ed2kServerIndexer(Indexer):
    """Keyword search on an eD2k server (TCP)."""

    server_title = "Amarr (eD2k server)"
    cache_key = "ed2k"

    def __init__(
        self,
        server: str = DEFAULT_SERVER,
        timeout: float = 15.0,
        idle_seconds: int = 600,
        search_fn: Optional[SearchFn] = None,
        logger: Optional[logging.Logger] = None,
        cache=None,
    ) -> None:
        super().__init__(logger or logging.getLogger("amarr.torznab.ed2k"), cache)
        self._search_fn = search_fn
        # Persistent TCP session: the connection is reused between searches.
        self._session = (
            None
            if search_fn is not None
            else Ed2kServerSession(server, timeout=timeout, idle_seconds=idle_seconds)
        )

    def _raw_search(self, query: str) -> List[SearchFile]:
        if self._search_fn is not None:
            results = self._search_fn(query)
        else:
            self._log.debug("eD2k: searching %r (persistent session)", query)
            results = self._session.search(query)
        self._log.debug("eD2k: %d raw results from the server", len(results))
        return to_search_files(results)
