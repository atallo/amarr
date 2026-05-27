"""Cliente de alto nivel para aMule (``jamule/AmuleClient.kt``).

En Kotlin cada método devuelve un ``Result<T>``; amarr siempre consume el
resultado con ``getOrThrow()``. Para mantener la misma semántica de forma
idiomática en Python, **estos métodos devuelven el valor en caso de éxito y
lanzan una excepción en caso de fallo** (equivalente exacto a ``getOrThrow()``).
"""
from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional

from .connection import AmuleConnection
from .ec.codes import EcPrefs
from .exceptions import CommunicationException
from .model import AmuleCategory, DownloadCommand, PartFileTag, SharedFileTag
from .request import (
    SearchFilters,
    SearchType,
    add_link_request,
    create_category_request,
    download_command_request,
    download_queue_request,
    download_search_result_request,
    get_preferences_request,
    search_request,
    search_results_request,
    search_status_request,
    search_stop_request,
    set_file_category_request,
    shared_files_request,
    stats_request,
)
from .response import (
    DownloadQueueResponse,
    EmptyPreferencesResponse,
    MiscDataResponse,
    NoopResponse,
    PrefsCategoriesResponse,
    SearchResultsResponse,
    SearchStatusResponse,
    SharedFilesResponse,
    StatsResponse,
    StringsResponse,
)

_logger = logging.getLogger("amarr.jamule.client")

CLIENT_NAME = "jAmule"


class AmuleClient:
    """Interfaz síncrona para hablar con el núcleo de aMule."""

    def __init__(
        self,
        connection: AmuleConnection,
        logger: Optional[logging.Logger] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._conn = connection
        self._logger = logger or _logger
        self._sleep = sleep

    @classmethod
    def connect(
        cls,
        host: str,
        port: int,
        password: str,
        timeout: float = 0,
        logger: Optional[logging.Logger] = None,
    ) -> "AmuleClient":
        conn = AmuleConnection.from_host(host, port, timeout, password, logger)
        return cls(conn, logger)

    def reconnect(self) -> None:
        self._conn.reconnect()

    # --- estadísticas -------------------------------------------------------

    def get_stats(self) -> StatsResponse:
        self._logger.info("Getting stats...")
        response = self._conn.send_request(stats_request())
        if isinstance(response, StatsResponse):
            return response
        raise CommunicationException(f"Unable to get stats, got response: {response}")

    # --- búsqueda -----------------------------------------------------------

    def search_async(
        self,
        query: str,
        search_type: SearchType = SearchType.GLOBAL,
        filters: Optional[SearchFilters] = None,
    ) -> str:
        self._logger.info("Searching for %s...", query)
        response = self._conn.send_request(
            search_request(query, search_type, filters or SearchFilters())
        )
        if isinstance(response, StringsResponse):
            return response.string
        raise CommunicationException(
            f"Unable to start search, got response: {response}"
        )

    def search_status(self) -> float:
        response = self._conn.send_request(search_status_request())
        if isinstance(response, SearchStatusResponse):
            return response.status
        raise CommunicationException(
            f"Unable to get search status, got response: {response}"
        )

    def search_results(self) -> SearchResultsResponse:
        response = self._conn.send_request(search_results_request())
        if isinstance(response, SearchResultsResponse):
            return response
        raise CommunicationException(
            f"Unable to get search results, got response: {response}"
        )

    def search_sync(
        self,
        query: str,
        search_type: SearchType = SearchType.GLOBAL,
        filters: Optional[SearchFilters] = None,
        timeout: float = 5.0,
    ) -> SearchResultsResponse:
        """Lanza una búsqueda y espera (bloqueando) a que termine.

        Replica la lógica de jaMule: 15 sondeos de 200 ms (el servidor devuelve
        siempre 100 % si no se espera un poco) y luego sondeo hasta status >= 1
        o hasta agotar ``timeout`` segundos.
        """
        self.search_async(query, search_type, filters or SearchFilters())
        for _ in range(15):
            self.search_status()
            self._sleep(0.2)
        start = time.monotonic()
        while self.search_status() < 1.0:
            if time.monotonic() - start > timeout:
                self._logger.error("Search timed out")
                break
            self._sleep(0.1)
        return self.search_results()

    def search_stop(self) -> None:
        response = self._conn.send_request(search_stop_request())
        if isinstance(response, MiscDataResponse):
            return
        raise CommunicationException(f"Unable to stop search, got response: {response}")

    def download_search_result(self, file_hash: bytes) -> None:
        response = self._conn.send_request(download_search_result_request(file_hash))
        if isinstance(response, StringsResponse):
            return
        raise CommunicationException(
            f"Unable to download search result, got response: {response}"
        )

    # --- descargas ----------------------------------------------------------

    def download_ed2k_link(self, link: str) -> None:
        """Añade una descarga a partir de un enlace ``ed2k://|file|...``."""
        self._logger.info("Downloading ed2k link...")
        response = self._conn.send_request(add_link_request(link))
        if isinstance(response, NoopResponse):
            return
        raise CommunicationException(
            f"Unable to download ed2k link, got response: {response}"
        )

    def get_download_queue(self) -> List[PartFileTag]:
        response = self._conn.send_request(download_queue_request())
        if isinstance(response, DownloadQueueResponse):
            return response.part_files
        raise CommunicationException(
            f"Unable to get download queue, got response: {response}"
        )

    def get_shared_files(self) -> List[SharedFileTag]:
        response = self._conn.send_request(shared_files_request())
        if isinstance(response, SharedFilesResponse):
            return response.shared_files
        raise CommunicationException(
            f"Unable to get shared files list, got response: {response}"
        )

    def send_download_command(
        self, file_hash: bytes, command: DownloadCommand
    ) -> None:
        response = self._conn.send_request(download_command_request(file_hash, command))
        if isinstance(response, NoopResponse):
            return
        raise CommunicationException(
            f"Unable to send download command, got response: {response}"
        )

    # --- categorías ---------------------------------------------------------

    def create_category(self, category: AmuleCategory) -> None:
        response = self._conn.send_request(create_category_request(category))
        if isinstance(response, NoopResponse):
            return
        raise CommunicationException(
            f"Unable to create category, got response: {response}"
        )

    def get_categories(self) -> List[AmuleCategory]:
        response = self._conn.send_request(
            get_preferences_request(EcPrefs.EC_PREFS_CATEGORIES)
        )
        if isinstance(response, PrefsCategoriesResponse):
            return response.categories
        if isinstance(response, EmptyPreferencesResponse):
            return []
        raise CommunicationException(
            f"Unable to get categories, got response: {response}"
        )

    def set_file_category(self, file_hash: bytes, category_id: int) -> None:
        """Asigna categoría a un fichero en descarga (debe estar en la cola)."""
        self._logger.info("Setting file category...")
        download_queue = self.get_download_queue()
        hash_hex = file_hash.hex()
        file = next(
            (f for f in download_queue if f.file_hash_hex_string == hash_hex), None
        )
        if file is None:
            self._logger.warning("File %s not found in download queue", hash_hex)
            raise CommunicationException(
                f"File {hash_hex} not found in download queue"
            )
        response = self._conn.send_request(
            set_file_category_request(file_hash, category_id)
        )
        if isinstance(response, NoopResponse):
            return
        raise CommunicationException(
            f"Unable to set file category, got response: {response}"
        )
