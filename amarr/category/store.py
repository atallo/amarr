"""Category store in SQLite and its relation to file hashes.

Replaces the old TSV-file persistence (``categories.tsv`` /
``hashes.tsv``) with a **SQLite** database (``amarr.db``) in the configuration
directory. It keeps the :class:`CategoryStore` interface, so the rest
of the app doesn't change.

Schema:

* ``categories(name PRIMARY KEY, save_path)``      — category catalog.
* ``file_categories(hash PRIMARY KEY, category)``  — file→category assignment.

On construction, if it finds TSV files from earlier versions it **sets them
aside** by renaming them to ``<name>.bak`` (they are not imported: it starts with
an empty DB). Access is thread-safe (lock + shared connection with
``check_same_thread=False``), suitable for the FastAPI threadpool.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from typing import Optional, Set

from ..torrent.models import Category

_log = logging.getLogger("amarr.category")


class CategoryStore(ABC):
    """Category store interface."""

    @abstractmethod
    def store(self, category: str, hash: str) -> None:
        ...

    @abstractmethod
    def get_category(self, hash: str) -> Optional[str]:
        ...

    @abstractmethod
    def delete(self, hash: str) -> None:
        ...

    @abstractmethod
    def add_category(self, category: Category) -> None:
        ...

    @abstractmethod
    def get_categories(self) -> Set[Category]:
        ...


_DB_FILE = "amarr.db"
# TSV files from earlier versions; set aside as "<name>.bak".
_LEGACY_TSV = ("categories.tsv", "hashes.tsv")


class SqliteCategoryStore(CategoryStore):
    """SQLite-backed implementation, thread-safe."""

    def __init__(self, store_path: str) -> None:
        os.makedirs(store_path, exist_ok=True)
        self._db_path = os.path.abspath(os.path.join(store_path, _DB_FILE))
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._init_schema()
        self._archive_legacy_tsv(store_path)

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS categories ("
                "name TEXT PRIMARY KEY, save_path TEXT NOT NULL DEFAULT '')"
            )
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS file_categories ("
                "hash TEXT PRIMARY KEY, category TEXT NOT NULL)"
            )

    @staticmethod
    def _archive_legacy_tsv(store_path: str) -> None:
        # The data is not imported (it starts with an empty DB); the files are
        # only set aside as "<name>.bak" as a backup.
        for name in _LEGACY_TSV:
            path = os.path.join(store_path, name)
            if os.path.exists(path):
                try:
                    os.replace(path, path + ".bak")
                    _log.info("Legacy TSV set aside: %s -> %s.bak", name, name)
                except OSError:
                    _log.warning("Could not set aside the legacy TSV %s", path)

    # --- hash -> category relation -----------------------------------------

    def store(self, category: str, hash: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO file_categories(hash, category) VALUES(?, ?)",
                (hash, category),
            )

    def get_category(self, hash: str) -> Optional[str]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT category FROM file_categories WHERE hash = ?", (hash,)
            )
            row = cur.fetchone()
        return row[0] if row is not None else None

    def delete(self, hash: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM file_categories WHERE hash = ?", (hash,))

    # --- category catalog --------------------------------------------------

    def add_category(self, category: Category) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO categories(name, save_path) VALUES(?, ?)",
                (category.name, category.save_path),
            )

    def get_categories(self) -> Set[Category]:
        with self._lock:
            cur = self._conn.execute("SELECT name, save_path FROM categories")
            rows = cur.fetchall()
        return {Category(name, save_path) for name, save_path in rows}
