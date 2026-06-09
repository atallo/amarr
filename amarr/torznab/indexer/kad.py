"""Indexador Torznab que busca en la red Kad (``amarr.ed2k.KadSearch``).

Serverless (UDP), 100% Python, independiente de aMule. Carga ``nodes.dat`` de
forma perezosa en la primera búsqueda y reutiliza el cliente Kad después. La
descarga sigue pasando por aMule.
"""
from __future__ import annotations

import logging
from typing import Callable, List, Optional

from ...ed2k import SearchResult
from ...jamule.response import SearchFile
from ...kad_session import KadSession
from ._results import to_search_files
from .base import Indexer

# Firma del motor de búsqueda; inyectable para poder testear sin red.
SearchFn = Callable[[str], List[SearchResult]]


class KadIndexer(Indexer):
    """Búsqueda por palabra clave en la red Kad (Kademlia, UDP)."""

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
                # KadSession carga nodes.dat (puede lanzar FileNotFoundError/
                # ValueError); lo captura el pipeline de Indexer (feed vacío).
                self._log.debug("Kad: cargando nodes.dat de %s", self._nodes_path)
                self._session = KadSession(
                    self._nodes_path,
                    ip_order=self._ip_order,
                    with_sources=self._with_sources,
                    idle_seconds=self._idle_seconds,
                )
            self._log.debug("Kad: buscando %r (pool reutilizado)", query)
            results = self._session.search(query)
        self._log.debug("Kad: %d resultados crudos de la red", len(results))
        return to_search_files(results)
