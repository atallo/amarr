"""Interfaz de indexador y excepciones de Torznab (``torznab/indexer/*.kt``)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..models import Caps, Feed


class ThrottledException(Exception):
    """El indexador limita las peticiones (se traduce a HTTP 403)."""


class UnauthorizedException(Exception):
    """Credenciales inválidas (se traduce a HTTP 401)."""


class Indexer(ABC):
    """Fuente de resultados de búsqueda en formato Torznab."""

    @abstractmethod
    def search(self, query: str, offset: int, limit: int, cat: List[int]) -> Feed:
        """Devuelve un :class:`Feed` con los resultados paginados."""

    @abstractmethod
    def capabilities(self) -> Caps:
        """Devuelve las capacidades del indexador."""
