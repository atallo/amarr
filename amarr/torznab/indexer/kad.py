"""Indexador Torznab que busca en la red Kad (``amarr.ed2k.KadSearch``).

Serverless (UDP), 100% Python, independiente de aMule. Carga ``nodes.dat`` de
forma perezosa en la primera búsqueda y reutiliza el cliente Kad después. La
descarga sigue pasando por aMule.
"""
from __future__ import annotations

import logging
from typing import Callable, List, Optional

from ...ed2k import KadSearch, SearchResult
from ...jamule.response import SearchFile
from ._results import to_search_files
from .base import Indexer

# Firma del motor de búsqueda; inyectable para poder testear sin red.
SearchFn = Callable[[str], List[SearchResult]]


class KadIndexer(Indexer):
    """Búsqueda por palabra clave en la red Kad (Kademlia, UDP)."""

    server_title = "Amarr (Kad)"

    def __init__(
        self,
        nodes_path: str,
        ip_order: str = "be",
        with_sources: bool = False,
        search_fn: Optional[SearchFn] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(logger or logging.getLogger("amarr.torznab.kad"))
        self._nodes_path = nodes_path
        self._ip_order = ip_order
        self._with_sources = with_sources
        self._search_fn = search_fn
        self._kad: Optional[KadSearch] = None

    def _raw_search(self, query: str) -> List[SearchFile]:
        if self._search_fn is not None:
            results = self._search_fn(query)
        else:
            if self._kad is None:
                # KadSearch puede lanzar FileNotFoundError/ValueError al cargar
                # nodes.dat; lo captura el pipeline de Indexer (feed vacío).
                self._log.debug("Kad: cargando nodes.dat de %s", self._nodes_path)
                self._kad = KadSearch(self._nodes_path, ip_order=self._ip_order)
            self._log.debug(
                "Kad: buscando %r (with_sources=%s)", query, self._with_sources
            )
            results = self._kad.search(query, with_sources=self._with_sources)
        self._log.debug("Kad: %d resultados crudos de la red", len(results))
        return to_search_files(results)
