"""Torznab indexer backed by aMule (``torznab/indexer/AmuleIndexer.kt``).

Translates Sonarr/Radarr searches into searches on an external aMule (EC
protocol) and delegates video filtering and feed building to :class:`Indexer`.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from ...jamule.client import AmuleClient
from ...jamule.response import SearchFile
from .base import Indexer


class AmuleIndexer(Indexer):
    """Search through an external aMule over the kad/eD2k network."""

    server_title = "Amarr (aMule)"
    cache_key = "amule"

    def __init__(
        self,
        amule_client: AmuleClient,
        logger: Optional[logging.Logger] = None,
        cache=None,
    ) -> None:
        super().__init__(logger or logging.getLogger("amarr.torznab.amule"), cache)
        self._amule = amule_client

    def _raw_search(self, query: str) -> List[SearchFile]:
        return self._amule.search_sync(query).files
