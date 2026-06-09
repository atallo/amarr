"""Caché de resultados de búsqueda en SQLite (``cache.db``).

Las búsquedas en eD2k/Kad son lentas (la red Kad puede tardar ~30 s) y
Sonarr/Radarr las repiten mucho (paginación, variantes de la consulta,
reintentos). Esta caché guarda los resultados crudos de cada búsqueda por
``(motor, consulta)`` durante ``ttl`` segundos, de modo que esas repeticiones se
sirven al instante sin relanzar la búsqueda.

Es un fichero aparte (``cache.db``) porque su contenido es **regenerable**; no se
mezcla con la base de datos de categorías (``amarr.db``). El acceso es seguro
entre hilos (cerrojo + conexión compartida con ``check_same_thread=False``).
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
    # Claves cortas: una búsqueda puede tener >1000 resultados.
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
    # ``download_status`` no se persiste (no lo usa el feed); se repone a NEW.
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
    """Caché TTL de resultados de búsqueda, respaldada por SQLite."""

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
        """Resultados cacheados para ``(backend, query)`` si existen y no han
        expirado; ``None`` en caso contrario (miss)."""
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
            return None  # expirado; se sobrescribirá en el próximo put
        try:
            return _deserialize(payload)
        except (ValueError, KeyError, TypeError):
            return None  # payload corrupto -> tratar como miss

    def put(self, backend: str, query: str, results: List[SearchFile]) -> None:
        if self._ttl <= 0:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO search_cache(backend, query, created_at, payload) "
                "VALUES (?, ?, ?, ?)",
                (backend, query, time.time(), _serialize(results)),
            )
