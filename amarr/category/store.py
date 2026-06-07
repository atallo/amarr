"""Almacén de categorías y su relación con los hashes de fichero.

Traducción de ``amarr/category/CategoryStore.kt`` y ``FileCategoryStore.kt``.
Persiste dos ficheros TSV en el directorio de configuración:

* ``categories.tsv``: ``nombre<TAB>savePath`` por línea.
* ``hashes.tsv``:      ``hash<TAB>categoría`` por línea.

El acceso está sincronizado con cerrojos (equivale a los ``synchronized`` de
Kotlin) y se cachea en memoria.
"""
from __future__ import annotations

import os
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set

from ..torrent.models import Category


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


_CATEGORIES_FILE = "categories.tsv"
_HASHES_FILE = "hashes.tsv"


class FileCategoryStore(CategoryStore):
    """Implementación respaldada por ficheros TSV, segura entre hilos."""

    def __init__(self, store_path: str) -> None:
        self._hashes_cache: Dict[str, str] = {}
        self._categories_cache: Optional[Set[Category]] = None
        self._categories_path = os.path.abspath(
            os.path.join(store_path, _CATEGORIES_FILE)
        )
        self._hashes_path = os.path.abspath(os.path.join(store_path, _HASHES_FILE))
        # Dos cerrojos independientes, uno por fichero, como en Kotlin.
        self._hashes_lock = threading.RLock()
        self._categories_lock = threading.RLock()

    # --- relación hash -> categoría ----------------------------------------

    def store(self, category: str, hash: str) -> None:
        with self._hashes_lock:
            if "\t" in category or "\t" in hash:
                raise ValueError("Category or hash contains tab character")
            os.makedirs(os.path.dirname(self._hashes_path), exist_ok=True)
            with open(self._hashes_path, "a", encoding="utf-8") as fh:
                fh.write(f"{hash}\t{category}\n")
            self._hashes_cache[hash] = category

    def get_category(self, hash: str) -> Optional[str]:
        with self._hashes_lock:
            if hash in self._hashes_cache:
                return self._hashes_cache[hash]
            if not os.path.exists(self._hashes_path):
                return None
            with open(self._hashes_path, encoding="utf-8") as fh:
                for line in fh.read().splitlines():
                    if line.split("\t")[0] == hash:
                        category = line.split("\t")[1]
                        self._hashes_cache[hash] = category
                        return category
            return None

    def delete(self, hash: str) -> None:
        with self._hashes_lock:
            if not os.path.exists(self._hashes_path):
                return
            with open(self._hashes_path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            target = next((ln for ln in lines if ln.split("\t")[0] == hash), None)
            if target is None:
                return
            remaining = [ln for ln in lines if ln != target]
            # Cada línea termina en "\n", igual que los append de store()/
            # add_category(). El original Kotlin usaba joinToString("\n") (sin
            # salto final), lo que corrompía el fichero: tras un delete la
            # última línea quedaba sin "\n" y el siguiente store se pegaba a
            # ella, fusionando dos entradas al releer con la caché fría.
            with open(self._hashes_path, "w", encoding="utf-8") as fh:
                for line in remaining:
                    fh.write(f"{line}\n")
            self._hashes_cache.pop(hash, None)

    # --- catálogo de categorías --------------------------------------------

    def add_category(self, category: Category) -> None:
        with self._categories_lock:
            if self._categories_cache is not None:
                self._categories_cache.add(category)
            os.makedirs(os.path.dirname(self._categories_path), exist_ok=True)
            with open(self._categories_path, "a", encoding="utf-8") as fh:
                fh.write(f"{category.name}\t{category.save_path}\n")

    def get_categories(self) -> Set[Category]:
        with self._categories_lock:
            if self._categories_cache is not None:
                return self._categories_cache
            if not os.path.exists(self._categories_path):
                return set()
            categories: Set[Category] = set()
            with open(self._categories_path, encoding="utf-8") as fh:
                for line in fh.read().splitlines():
                    split = line.split("\t")
                    categories.add(Category(split[0], split[1]))
            self._categories_cache = categories
            return self._categories_cache
