"""Indexador Torznab que busca en un servidor eD2k (``amarr.ed2k.ServerSearch``).

Búsqueda 100% Python por TCP, independiente de aMule. La descarga sigue pasando
por aMule (el magnet resultante se le entrega vía la API qBittorrent).
"""
from __future__ import annotations

import logging
from typing import Callable, List, Optional

from ...ed2k import DEFAULT_SERVER, SearchResult
from ...ed2k_session import Ed2kServerSession
from ...jamule.response import SearchFile
from ._results import to_search_files
from .base import Indexer

# Firma del motor de búsqueda; inyectable para poder testear sin red.
SearchFn = Callable[[str], List[SearchResult]]


class Ed2kServerIndexer(Indexer):
    """Búsqueda por palabra clave en un servidor eD2k (TCP)."""

    server_title = "Amarr (eD2k servidor)"
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
        # Sesión TCP persistente: se reutiliza la conexión entre búsquedas.
        self._session = (
            None
            if search_fn is not None
            else Ed2kServerSession(server, timeout=timeout, idle_seconds=idle_seconds)
        )

    def _raw_search(self, query: str) -> List[SearchFile]:
        if self._search_fn is not None:
            results = self._search_fn(query)
        else:
            self._log.debug("eD2k: buscando %r (sesión persistente)", query)
            results = self._session.search(query)
        self._log.debug("eD2k: %d resultados crudos del servidor", len(results))
        return to_search_files(results)
