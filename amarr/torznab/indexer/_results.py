"""Adapter from the ``ed2k`` library results to the internal model.

The ed2k/kad engines return :class:`amarr.ed2k.SearchResult`; the
:class:`Indexer` pipeline operates on :class:`SearchFile`. Here one is translated
to the other (``sources``/``complete_sources`` may come as ``None``, normalized to 0).
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
