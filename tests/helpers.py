"""Utilidades compartidas para los tests (fakes y fábricas)."""
from typing import Dict, List, Optional, Set

from amarr.category.store import CategoryStore
from amarr.jamule.model import FileStatus, PartFileTag
from amarr.jamule.response import SearchFile, SearchFileDownloadStatus
from amarr.torrent.models import Category


def make_part_file(
    file_hash_hex_string: Optional[str] = None,
    file_name: Optional[str] = None,
    size_full: Optional[int] = 0,
    size_done: Optional[int] = 0,
    speed: Optional[int] = 0,
    source_xfer_count: int = 0,
    file_status: FileStatus = FileStatus.UNKNOWN,
    file_path: Optional[str] = None,
) -> PartFileTag:
    """Equivalente al ``MockTransferringFile`` de los tests de Kotlin."""
    return PartFileTag(
        file_hash_hex_string=file_hash_hex_string,
        file_name=file_name,
        file_path=file_path,
        size_full=size_full,
        file_ed2k_link=None,
        up_prio=0,
        get_requests=0,
        get_all_requests=0,
        get_accepts=0,
        get_all_accepts=0,
        get_xferred=0,
        get_all_xferred=0,
        get_complete_sources_low=0,
        get_complete_sources_high=0,
        get_complete_sources=0,
        get_on_queue=0,
        get_comment=None,
        get_rating=0,
        part_met_id=0,
        size_xfer=0,
        size_done=size_done,
        file_status=file_status,
        stopped=False,
        source_count=0,
        source_not_curr_count=0,
        source_xfer_count=source_xfer_count,
        source_count_a4af=0,
        speed=speed,
        down_prio=0,
        file_cat=0,
        last_seen_complete=0,
        last_date_changed=0,
        download_active_time=0,
        available_part_count=0,
        a4af_auto=False,
        hashing_progress=False,
        get_lost_due_to_corruption=0,
        get_gain_due_to_compression=0,
        total_packets_saved_due_to_ich=0,
    )


def make_search_file(
    file_name: str,
    hash: bytes,
    size_full: int = 1000,
    complete_source_count: int = 1,
    source_count: int = 2,
) -> SearchFile:
    return SearchFile(
        file_name=file_name,
        hash=hash,
        size_full=size_full,
        download_status=SearchFileDownloadStatus.NEW,
        complete_source_count=complete_source_count,
        source_count=source_count,
    )


class FakeAmuleClient:
    """Cliente aMule de mentira, controlable desde los tests."""

    def __init__(self) -> None:
        self.download_queue: List[PartFileTag] = []
        self.shared_files: List[PartFileTag] = []
        self.search_files: List[SearchFile] = []
        self.downloaded_links: List[str] = []
        self.delete_commands: List[tuple] = []

    def get_download_queue(self) -> List[PartFileTag]:
        return self.download_queue

    def get_shared_files(self) -> List[PartFileTag]:
        return self.shared_files

    def search_sync(self, query: str, *args, **kwargs):
        self.last_query = query
        from amarr.jamule.response import SearchResultsResponse

        return SearchResultsResponse(self.search_files)

    def download_ed2k_link(self, link: str) -> None:
        self.downloaded_links.append(link)

    def send_download_command(self, file_hash: bytes, command) -> None:
        self.delete_commands.append((file_hash, command))


class MemoryCategoryStore(CategoryStore):
    """Almacén de categorías en memoria (equivalente al de los tests Kotlin)."""

    def __init__(self) -> None:
        self._categories: Set[Category] = set()
        self._hashes: Dict[str, str] = {}

    def store(self, category: str, hash: str) -> None:
        self._hashes[hash] = category

    def get_category(self, hash: str) -> Optional[str]:
        return self._hashes.get(hash)

    def delete(self, hash: str) -> None:
        self._hashes.pop(hash, None)

    def add_category(self, category: Category) -> None:
        self._categories.add(category)

    def get_categories(self) -> Set[Category]:
        return self._categories
