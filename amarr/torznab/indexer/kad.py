"""Torznab indexer that searches the Kad network (``amarr.ed2k.KadSearch``).

Serverless (UDP), 100% Python, independent of aMule. Loads ``nodes.dat``
lazily on the first search and reuses the Kad client afterwards. Downloading
still goes through aMule.
"""
from __future__ import annotations

import logging
from typing import Callable, List, Optional

from ...ed2k import SearchResult
from ...jamule.response import SearchFile
from ...kad_session import KadSession
from ._results import to_search_files
from .base import Indexer

# Search engine signature; injectable so it can be tested without a network.
SearchFn = Callable[[str], List[SearchResult]]


class KadIndexer(Indexer):
    """Keyword search on the Kad network (Kademlia, UDP)."""

    server_title = "Amarr (Kad)"
    cache_key = "kad"

    def __init__(
        self,
        nodes_path: str,
        ip_order: str = "be",
        with_sources: bool = False,
        idle_seconds: int = 600,
        search_fn: Optional[SearchFn] = None,
        logger: Optional[logging.Logger] = None,
        cache=None,
    ) -> None:
        super().__init__(logger or logging.getLogger("amarr.torznab.kad"), cache)
        self._nodes_path = nodes_path
        self._ip_order = ip_order
        self._with_sources = with_sources
        self._idle_seconds = idle_seconds
        self._search_fn = search_fn
        self._session: Optional[KadSession] = None

    def _raw_search(self, query: str) -> List[SearchFile]:
        if self._search_fn is not None:
            results = self._search_fn(query)
        else:
            if self._session is None:
                # KadSession loads nodes.dat (may raise FileNotFoundError/
                # ValueError); the Indexer pipeline catches it (empty feed).
                self._log.debug("Kad: loading nodes.dat from %s", self._nodes_path)
                self._session = KadSession(
                    self._nodes_path,
                    ip_order=self._ip_order,
                    with_sources=self._with_sources,
                    idle_seconds=self._idle_seconds,
                )
            self._log.debug("Kad: searching %r (reused pool)", query)
            results = self._session.search(query)
        self._log.debug("Kad: %d raw results from the network", len(results))
        return to_search_files(results)
