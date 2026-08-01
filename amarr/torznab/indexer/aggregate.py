"""Aggregator indexer: combines the results of several engines (``all`` endpoint).

Runs the active indexers in parallel (each search is blocking), deduplicates
by the enclosure URL (the magnet, deterministic by hash/name/size) and
paginates, just like the multi-query merge in ``torznab/api.py:_perform_queries``.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Sequence

from ...jamule.response import SearchFile
from ..models import Channel, Feed, Response
from .base import Indexer, _empty_query_response


class AggregateIndexer(Indexer):
    """Combines the results of several indexers into a single feed."""

    server_title = "Amarr (all)"

    def __init__(
        self, indexers: Sequence[Indexer], logger: Optional[logging.Logger] = None
    ) -> None:
        super().__init__(logger or logging.getLogger("amarr.torznab.all"))
        self._indexers = list(indexers)

    def search(
        self, query: str, offset: int, limit: int, cat: List[int], base_url: str = ""
    ) -> Feed:
        if not query.strip():
            return _empty_query_response()

        # Each engine is queried from 0 up to offset+limit, merged,
        # deduplicated by URL and paginated (same pattern as the TV search).
        raw_limit = offset + limit
        feeds: List[Feed] = []
        with ThreadPoolExecutor(max_workers=max(1, len(self._indexers))) as executor:
            futures = [
                executor.submit(ix.search, query, 0, raw_limit, cat, base_url)
                for ix in self._indexers
            ]
            # Submission order (deterministic): the first active engine has
            # priority in the deduplication.
            for ix, future in zip(self._indexers, futures):
                try:
                    feeds.append(future.result())
                except Exception as exc:  # noqa: BLE001 - one engine doesn't take down the rest
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
        raise NotImplementedError("AggregateIndexer overrides search()")
