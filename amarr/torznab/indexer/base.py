"""Interfaz de indexador y pipeline común de Torznab (``torznab/indexer/*.kt``).

``Indexer`` centraliza todo lo que comparten los motores de búsqueda
(normalización de la consulta, filtrado de vídeo, construcción del feed, caps y
manejo de errores). Cada motor concreto solo implementa :meth:`Indexer._raw_search`,
que devuelve una lista de :class:`SearchFile` (el modelo interno común).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from typing import List, Optional

from ...jamule.response import SearchFile
from ...magnet import MagnetLink
from ..models import Caps, Channel, Enclosure, Feed, Item, Response, TorznabAttribute


class ThrottledException(Exception):
    """El indexador limita las peticiones (se traduce a HTTP 403)."""


class UnauthorizedException(Exception):
    """Credenciales inválidas (se traduce a HTTP 401)."""


# Extensiones consideradas vídeo.
_VIDEO_EXTENSIONS = {
    "avi", "m2ts", "m4v", "mkv", "mov", "mp4",
    "mpeg", "mpg", "ts", "webm", "wmv",
}
# Extensiones excluidas explícitamente.
_EXCLUDED_EXTENSIONS = {
    "ass", "cue", "gif", "jpg", "jpeg", "m3u", "mp3",
    "nfo", "png", "rar", "srt", "sub", "txt", "zip",
}
# Tamaño mínimo para aceptar un fichero sin extensión como vídeo (50 MiB).
_MIN_VIDEO_SIZE_BYTES = 50 * 1024 * 1024

_NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")

# Errores de los motores que no deben tumbar la respuesta a Sonarr/Radarr: se
# registran y se devuelve un feed vacío (un servidor eD2k caído o un nodes.dat
# inválido no deben provocar un 500).
_SEARCH_ERRORS = (OSError, ValueError)


class Indexer(ABC):
    """Fuente de resultados de búsqueda en formato Torznab.

    Implementa el pipeline común; las subclases solo aportan ``_raw_search``.
    """

    #: Título anunciado en las capacidades (``caps``); las subclases lo afinan.
    server_title: str = "Amarr"

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger("amarr.torznab.indexer")

    # --- API pública --------------------------------------------------------

    def search(self, query: str, offset: int, limit: int, cat: List[int]) -> Feed:
        self._log.debug(
            "Starting search for query: %s, offset: %s, limit: %s", query, offset, limit
        )
        if not query.strip():
            self._log.debug("Empty query, returning empty response")
            return _empty_query_response()
        clean_query = self._normalize_search_query(query)
        self._log.debug("Consulta normalizada: %r -> %r", query, clean_query)
        try:
            results = self._raw_search(clean_query)
        except _SEARCH_ERRORS as exc:
            # En DEBUG se incluye el traceback completo para depurar.
            self._log.warning(
                "La búsqueda falló (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=self._log.isEnabledFor(logging.DEBUG),
            )
            return self._build_feed([], offset, limit)
        relevant = [f for f in results if self._is_relevant_video_result(f)]
        self._log.debug(
            "Resultados de %r: %d crudos, %d relevantes tras el filtro de vídeo",
            clean_query,
            len(results),
            len(relevant),
        )
        return self._build_feed(relevant, offset, limit)

    def capabilities(self) -> Caps:
        return Caps(server_title=self.server_title)

    # --- a implementar por cada motor --------------------------------------

    @abstractmethod
    def _raw_search(self, query: str) -> List[SearchFile]:
        """Ejecuta la búsqueda cruda en el motor concreto (la consulta ya viene
        normalizada). Puede lanzar errores de red/datos; el pipeline los captura.
        """

    # --- helpers compartidos ------------------------------------------------

    @staticmethod
    def _is_relevant_video_result(file: SearchFile) -> bool:
        if "." in file.file_name:
            extension = file.file_name.rsplit(".", 1)[-1].lower()
        else:
            extension = ""
        if extension in _EXCLUDED_EXTENSIONS:
            return False
        return extension in _VIDEO_EXTENSIONS or (
            extension == "" and file.size_full >= _MIN_VIDEO_SIZE_BYTES
        )

    @staticmethod
    def _normalize_search_query(query: str) -> str:
        # NFD + eliminación de diacríticos (toda marca combinante), sustitución de
        # símbolos por espacios y colapso de espacios. Equivale al original en
        # Kotlin y a ``core._fold`` de la librería ed2k.
        decomposed = unicodedata.normalize("NFD", query)
        without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
        spaced = _NON_WORD_RE.sub(" ", without_marks)
        collapsed = _WHITESPACE_RE.sub(" ", spaced)
        return collapsed.strip()

    @staticmethod
    def _build_feed(items: List[SearchFile], offset: int, limit: int) -> Feed:
        page = items[offset : offset + limit]
        feed_items = [
            Item(
                title=result.file_name,
                enclosure=Enclosure(
                    url=str(
                        MagnetLink.for_amarr(
                            result.hash, result.file_name, result.size_full
                        )
                    ),
                    length=result.size_full,
                ),
                attributes=[
                    TorznabAttribute("category", "1"),
                    TorznabAttribute("seeders", str(result.complete_source_count)),
                    TorznabAttribute("peers", str(result.source_count)),
                    TorznabAttribute("size", str(result.size_full)),
                ],
            )
            for result in page
        ]
        return Feed(
            channel=Channel(
                response=Response(offset=offset, total=len(items)),
                item=feed_items,
            )
        )


def _empty_query_response() -> Feed:
    return Feed(
        channel=Channel(
            response=Response(offset=0, total=1),
            item=[
                Item(
                    title="No query provided",
                    enclosure=Enclosure("http://mock.url", 0),
                    attributes=[
                        TorznabAttribute("category", "1"),
                        TorznabAttribute("size", "0"),
                    ],
                )
            ],
        )
    )
