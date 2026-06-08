"""Indexador Torznab respaldado por aMule (``torznab/indexer/AmuleIndexer.kt``).

Traduce las búsquedas de Sonarr/Radarr a búsquedas en un aMule externo (protocolo
EC) y delega en :class:`Indexer` el filtrado de vídeo y la construcción del feed.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from ...jamule.client import AmuleClient
from ...jamule.response import SearchFile
from .base import Indexer


class AmuleIndexer(Indexer):
    """Búsqueda a través de un aMule externo por la red kad/eD2k."""

    server_title = "Amarr (aMule)"

    def __init__(
        self, amule_client: AmuleClient, logger: Optional[logging.Logger] = None
    ) -> None:
        super().__init__(logger or logging.getLogger("amarr.torznab.amule"))
        self._amule = amule_client

    def _raw_search(self, query: str) -> List[SearchFile]:
        return self._amule.search_sync(query).files
