"""Indexador agregador: combina los resultados de varios motores (endpoint ``all``).

Ejecuta los indexers activos en paralelo (cada búsqueda es bloqueante), deduplica
por la URL del enclosure (el magnet, determinista por hash/nombre/tamaño) y
pagina, igual que la fusión multi-consulta de ``torznab/api.py:_perform_queries``.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Sequence

from ...jamule.response import SearchFile
from ..models import Channel, Feed, Response
from .base import Indexer, _empty_query_response


class AggregateIndexer(Indexer):
    """Combina los resultados de varios indexers en un único feed."""

    server_title = "Amarr (todos)"

    def __init__(
        self, indexers: Sequence[Indexer], logger: Optional[logging.Logger] = None
    ) -> None:
        super().__init__(logger or logging.getLogger("amarr.torznab.all"))
        self._indexers = list(indexers)

    def search(self, query: str, offset: int, limit: int, cat: List[int]) -> Feed:
        if not query.strip():
            return _empty_query_response()

        # Se pide a cada motor desde 0 hasta offset+limit, se fusiona, se
        # deduplica por URL y se pagina (mismo patrón que la búsqueda TV).
        raw_limit = offset + limit
        feeds: List[Feed] = []
        with ThreadPoolExecutor(max_workers=max(1, len(self._indexers))) as executor:
            futures = [
                executor.submit(ix.search, query, 0, raw_limit, cat)
                for ix in self._indexers
            ]
            # Orden de envío (determinista): el primer motor activo tiene
            # prioridad en la deduplicación.
            for ix, future in zip(self._indexers, futures):
                try:
                    feeds.append(future.result())
                except Exception as exc:  # noqa: BLE001 - un motor no tumba al resto
                    self._log.warning("Indexer %s failed: %s", type(ix).__name__, exc)

        seen = set()
        merged = []
        for feed in feeds:
            for item in feed.channel.item:
                if item.enclosure.url not in seen:
                    seen.add(item.enclosure.url)
                    merged.append(item)

        page = merged[offset : offset + limit]
        return Feed(
            channel=Channel(
                response=Response(offset=offset, total=len(merged)),
                item=page,
            )
        )

    def _raw_search(self, query: str) -> List[SearchFile]:  # pragma: no cover
        raise NotImplementedError("AggregateIndexer sobrescribe search()")
