"""Search result cache in SQLite (``cache.db``).

eD2k/Kad searches are slow (the Kad network can take ~30 s) and
Sonarr/Radarr repeat them a lot (pagination, query variants,
retries). This cache stores the raw results of each search by
``(engine, query)`` for ``ttl`` seconds, so that those repetitions are
served instantly without re-running the search.

It is a separate file (``cache.db``) because its content is **regenerable**; it
is not mixed with the category database (``amarr.db``). Access is thread-safe
(lock + shared connection with ``check_same_thread=False``).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import List, Optional

from .jamule.response import SearchFile, SearchFileDownloadStatus

_log = logging.getLogger("amarr.cache")

_CACHE_FILE = "cache.db"


def _serialize(results: List[SearchFile]) -> str:
    # Short keys: a search can have >1000 results.
    return json.dumps(
        [
            {
                "n": r.file_name,
                "h": r.hash.hex(),
                "s": r.size_full,
                "c": r.complete_source_count,
                "p": r.source_count,
            }
            for r in results
        ]
    )


def _deserialize(payload: str) -> List[SearchFile]:
    # ``download_status`` is not persisted (the feed doesn't use it); reset to NEW.
    return [
        SearchFile(
            file_name=d["n"],
            hash=bytes.fromhex(d["h"]),
            size_full=d["s"],
            download_status=SearchFileDownloadStatus.NEW,
            complete_source_count=d["c"],
            source_count=d["p"],
        )
        for d in json.loads(payload)
    ]


class SearchCache:
    """TTL cache of search results, backed by SQLite."""

    def __init__(self, store_path: str, ttl_seconds: int) -> None:
        os.makedirs(store_path, exist_ok=True)
        self._ttl = ttl_seconds
        self._db_path = os.path.abspath(os.path.join(store_path, _CACHE_FILE))
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        with self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS search_cache ("
                "backend TEXT NOT NULL, query TEXT NOT NULL, created_at REAL NOT NULL, "
                "payload TEXT NOT NULL, PRIMARY KEY (backend, query))"
            )

    @property
    def ttl(self) -> int:
        return self._ttl

    def get(self, backend: str, query: str) -> Optional[List[SearchFile]]:
        """Cached results for ``(backend, query)`` if they exist and have not
        expired; ``None`` otherwise (miss)."""
        if self._ttl <= 0:
            return None
        with self._lock:
            cur = self._conn.execute(
                "SELECT created_at, payload FROM search_cache "
                "WHERE backend = ? AND query = ?",
                (backend, query),
            )
            row = cur.fetchone()
        if row is None:
            return None
        created_at, payload = row
        if time.time() - created_at > self._ttl:
            return None  # expired; it will be overwritten on the next put
        try:
            return _deserialize(payload)
        except (ValueError, KeyError, TypeError):
            return None  # corrupt payload -> treat as a miss

    def put(self, backend: str, query: str, results: List[SearchFile]) -> None:
        if self._ttl <= 0:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO search_cache(backend, query, created_at, payload) "
                "VALUES (?, ?, ?, ?)",
                (backend, query, time.time(), _serialize(results)),
            )
