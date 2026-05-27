"""Lógica de negocio que traduce aMule <-> qBittorrent (``TorrentService.kt``).

Funde los ficheros compartidos y la cola de descargas de aMule en la vista de
"torrents" que esperan Sonarr/Radarr, y traduce las operaciones (añadir, borrar,
categorías) a comandos EC.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

from ..category.store import CategoryStore
from ..jamule.client import AmuleClient
from ..jamule.model import DownloadCommand, FileStatus, PartFileTag
from ..magnet import MagnetLink
from .models import (
    Category,
    TorrentFile,
    TorrentInfo,
    TorrentProperties,
    TorrentState,
)

# Valor que qBittorrent usa para indicar "sin ETA disponible".
_NO_ETA = 8640000


class NotFoundException(Exception):
    """Se traduce a HTTP 404 en la capa de API."""


class TorrentService:
    def __init__(
        self,
        amule_client: AmuleClient,
        category_store: CategoryStore,
        finished_path: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._amule = amule_client
        self._categories = category_store
        self._finished_path = finished_path
        self._log = logger or logging.getLogger("amarr.torrent")

    # --- consulta -----------------------------------------------------------

    def get_torrent_info(self, category: Optional[str]) -> List[TorrentInfo]:
        downloading_files = self._amule.get_download_queue()
        shared_files = self._amule.get_shared_files()
        downloading_hashes = {f.file_hash_hex_string for f in downloading_files}

        # Los ficheros en descarga también aparecen entre los compartidos; se
        # eliminan de estos para no duplicarlos.
        all_files = [
            f
            for f in shared_files
            if f.file_hash_hex_string not in downloading_hashes
        ] + list(downloading_files)

        all_files = [
            f
            for f in all_files
            if category is None
            or self._categories.get_category(f.file_hash_hex_string) == category
        ]

        result: List[TorrentInfo] = []
        for dl in all_files:
            if isinstance(dl, PartFileTag):
                result.append(self._transferring_to_info(dl, category))
            else:
                # Fichero ya descargado por completo (sólo compartido).
                result.append(
                    TorrentInfo(
                        hash=dl.file_hash_hex_string,
                        name=dl.file_name,
                        size=dl.size_full,
                        total_size=dl.size_full,
                        save_path=self._finished_path,
                        dlspeed=0,
                        downloaded=dl.size_full,
                        progress=1.0,
                        priority=0,
                        state=TorrentState.uploading,
                        category=category,
                        eta=0,
                        num_seeds=0,
                    )
                )
        return result

    def _transferring_to_info(
        self, dl: PartFileTag, category: Optional[str]
    ) -> TorrentInfo:
        if dl.source_xfer_count > 0:
            state = TorrentState.downloading
        elif dl.file_status == FileStatus.READY:
            state = TorrentState.metaDL
        elif dl.file_status == FileStatus.ERROR:
            state = TorrentState.error
        elif dl.file_status == FileStatus.COMPLETING:
            state = TorrentState.checkingDL
        elif dl.file_status == FileStatus.COMPLETE:
            state = TorrentState.uploading
        elif dl.file_status == FileStatus.PAUSED:
            state = TorrentState.pausedDL
        elif dl.file_status == FileStatus.ALLOCATING:
            state = TorrentState.allocating
        elif dl.file_status == FileStatus.INSUFFICIENT:
            self._log.error("Insufficient disk space")
            state = TorrentState.error
        else:
            state = TorrentState.unknown

        return TorrentInfo(
            hash=dl.file_hash_hex_string,
            name=dl.file_name,
            size=dl.size_full,
            total_size=dl.size_full,
            save_path=self._finished_path,
            downloaded=dl.size_done,
            progress=dl.size_done / dl.size_full,
            priority=dl.down_prio,
            state=state,
            category=category,
            dlspeed=dl.speed,
            num_seeds=dl.source_xfer_count,
            eta=self._compute_eta(dl.speed, dl.size_full, dl.size_done),
        )

    @staticmethod
    def _compute_eta(speed: int, size_full: int, size_done: int) -> int:
        remaining = size_full - size_done
        if speed == 0:
            return _NO_ETA
        return min(remaining // speed, _NO_ETA)

    # --- categorías ---------------------------------------------------------

    def get_categories(self) -> Dict[str, Category]:
        return {c.name: c for c in self._categories.get_categories()}

    def add_category(self, category: Category) -> None:
        self._categories.add_category(category)

    # --- altas/bajas --------------------------------------------------------

    def add_torrent(
        self,
        urls: Optional[List[str]],
        category: Optional[str],
        paused: Optional[str],
    ) -> None:
        if urls is None:
            self._log.error("No urls provided")
            raise self._non_amarr_link("No urls provided")
        for url in urls:
            try:
                magnet_link = MagnetLink.from_string(url)
            except Exception as exc:
                raise self._non_amarr_link(url) from exc
            if not magnet_link.is_amarr():
                raise self._non_amarr_link(url)
            self._amule.download_ed2k_link(magnet_link.to_ed2k_link())
            if category is not None:
                self._categories.store(category, magnet_link.amule_hex_hash())

    def delete_torrent(self, hashes: List[str], delete_files: Optional[str]) -> None:
        downloading_files = self._amule.get_download_queue()
        downloading_hashes = {f.file_hash_hex_string for f in downloading_files}
        for hash in hashes:
            if hash in downloading_hashes:
                self._amule.send_download_command(
                    bytes.fromhex(hash), DownloadCommand.DELETE
                )
            elif delete_files == "true":
                self._delete_shared_file_by_hash(hash)
            else:
                self._log.error(
                    "File with hash %s not found in downloading files", hash
                )
            self._categories.delete(hash)

    def delete_all_torrents(self, delete_files: Optional[str]) -> None:
        for file in self._amule.get_shared_files():
            self._amule.send_download_command(
                bytes.fromhex(file.file_hash_hex_string), DownloadCommand.DELETE
            )
            self._categories.delete(file.file_hash_hex_string)

    # --- ficheros / propiedades --------------------------------------------

    def get_file(self, hash: str) -> TorrentFile:
        info = next(t for t in self.get_torrent_info(None) if t.hash == hash)
        return TorrentFile(name=info.name)

    def get_torrent_properties(self, hash: str) -> TorrentProperties:
        info = next(t for t in self.get_torrent_info(None) if t.hash == hash)
        return TorrentProperties(
            hash=info.hash,
            save_path=info.save_path,
            seeding_time=info.seeding_time,
        )

    # --- internos -----------------------------------------------------------

    def _delete_shared_file_by_hash(self, hash: str) -> None:
        file = next(
            (
                f
                for f in self._amule.get_shared_files()
                if f.file_hash_hex_string == hash
            ),
            None,
        )
        if file is not None and file.file_path:
            try:
                os.remove(file.file_path)
            except OSError:
                self._log.error("Could not delete file %s", file.file_path)
        else:
            self._log.error("File with hash %s not found in shared files", hash)

    def _non_amarr_link(self, url: str) -> NotFoundException:
        self._log.error(
            "The provided link does not appear to be an Amarr link: %s. "
            "Have you configured Radarr/Sonarr's download client priority "
            "correctly? See README.md",
            url,
        )
        return NotFoundException(
            f"The provided link does not appear to be an Amarr link: {url}"
        )
