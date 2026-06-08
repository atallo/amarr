"""Adaptador de los resultados de la librería ``ed2k`` al modelo interno.

Los motores ed2k/kad devuelven :class:`amarr.ed2k.SearchResult`; el pipeline de
:class:`Indexer` opera sobre :class:`SearchFile`. Aquí se traduce uno a otro
(``sources``/``complete_sources`` pueden venir a ``None``, se normalizan a 0).
"""
from __future__ import annotations

from typing import Iterable, List

from ...ed2k import SearchResult
from ...jamule.response import SearchFile, SearchFileDownloadStatus


def to_search_file(result: SearchResult) -> SearchFile:
    return SearchFile(
        file_name=result.name,
        hash=result.file_hash,
        size_full=result.size,
        download_status=SearchFileDownloadStatus.NEW,
        complete_source_count=int(result.complete_sources or 0),
        source_count=int(result.sources or 0),
    )


def to_search_files(results: Iterable[SearchResult]) -> List[SearchFile]:
    return [to_search_file(r) for r in results]
