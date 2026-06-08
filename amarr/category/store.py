"""Almacén de categorías en SQLite y su relación con los hashes de fichero.

Reemplaza la antigua persistencia en ficheros TSV (``categories.tsv`` /
``hashes.tsv``) por una base de datos **SQLite** (``amarr.db``) en el directorio
de configuración. Mantiene la interfaz :class:`CategoryStore`, así que el resto
de la app no cambia.

Esquema:

* ``categories(name PRIMARY KEY, save_path)``      — catálogo de categorías.
* ``file_categories(hash PRIMARY KEY, category)``  — asignación fichero→categoría.

Al construirse, si encuentra ficheros TSV de versiones anteriores los **aparta**
renombrándolos a ``<nombre>.bak`` (no se importan: se arranca con la BD vacía).
El acceso es seguro entre hilos (cerrojo + conexión compartida con
``check_same_thread=False``), apto para el threadpool de FastAPI.
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
    """Interfaz del almacén de categorías."""

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
# Ficheros TSV de versiones anteriores; se apartan a "<nombre>.bak".
_LEGACY_TSV = ("categories.tsv", "hashes.tsv")


class SqliteCategoryStore(CategoryStore):
    """Implementación respaldada por SQLite, segura entre hilos."""

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
        # No se importan los datos (se arranca con la BD vacía); solo se apartan
        # a "<nombre>.bak" como respaldo.
        for name in _LEGACY_TSV:
            path = os.path.join(store_path, name)
            if os.path.exists(path):
                try:
                    os.replace(path, path + ".bak")
                    _log.info("TSV heredado apartado: %s -> %s.bak", name, name)
                except OSError:
                    _log.warning("No se pudo apartar el TSV heredado %s", path)

    # --- relación hash -> categoría ----------------------------------------

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

    # --- catálogo de categorías --------------------------------------------

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
