"""Indexador Torznab que busca en un servidor eD2k (``amarr.ed2k.ServerSearch``).

Búsqueda 100% Python por TCP, independiente de aMule. La descarga sigue pasando
por aMule (el magnet resultante se le entrega vía la API qBittorrent).
"""
from __future__ import annotations

import logging
from typing import Callable, List, Optional

from ...ed2k import DEFAULT_SERVER, SearchResult, ServerSearch
from ...jamule.response import SearchFile
from ._results import to_search_files
from .base import Indexer

# Firma del motor de búsqueda; inyectable para poder testear sin red.
SearchFn = Callable[[str], List[SearchResult]]


class Ed2kServerIndexer(Indexer):
    """Búsqueda por palabra clave en un servidor eD2k (TCP)."""

    server_title = "Amarr (eD2k servidor)"

    def __init__(
        self,
        server: str = DEFAULT_SERVER,
        timeout: float = 15.0,
        search_fn: Optional[SearchFn] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(logger or logging.getLogger("amarr.torznab.ed2k"))
        self._server = server
        self._timeout = timeout
        self._search_fn = search_fn

    def _raw_search(self, query: str) -> List[SearchFile]:
        if self._search_fn is not None:
            results = self._search_fn(query)
        else:
            results = ServerSearch(self._server, timeout=self._timeout).search(query)
        return to_search_files(results)
