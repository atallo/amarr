"""Respuestas EC y su parser (``jamule/response/*.kt``).

``ResponseParser.parse(packet)`` recorre los deserializadores en orden y
devuelve la primera respuesta cuyo ``can_deserialize`` acepta el paquete, igual
que en Kotlin. Las respuestas se modelan como dataclasses; las que en Kotlin son
``data object`` (sin estado) se representan como instancias únicas (singletons).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .ec.codes import ECOpCode, ECSearchFileDownloadStatus, ECTagName
from .ec.packet import Packet
from .ec.tag import (
    Ipv4,
    StringTag,
    Tag,
    as_byte,
    as_ipv4,
    as_numeric,
    find_byte,
    find_custom,
    find_hash16,
    find_int,
    find_long,
    find_numeric,
    find_short,
    find_string,
)
from .exceptions import CommunicationException, ServerException
from .model import AmuleCategory


class Response:
    """Marcador base para todas las respuestas (sealed interface en Kotlin)."""


# --- Respuestas simples -------------------------------------------------------


@dataclass
class AuthFailedResponse(Response, Exception):
    reason: str

    def __post_init__(self) -> None:
        Exception.__init__(self, self.reason)


@dataclass
class AuthOkResponse(Response):
    version: str


@dataclass
class AuthSaltResponse(Response):
    salt: int


@dataclass
class ErrorResponse(Response, Exception):
    """Error del servidor (EC_OP_FAILED). Se eleva como :class:`ServerException`."""

    server_message: str

    def __post_init__(self) -> None:
        Exception.__init__(self, self.server_message)


@dataclass
class StringsResponse(Response):
    string: str


class _Singleton(Response):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


class MiscDataResponse(_Singleton):
    """EC_OP_MISC_DATA (data object en Kotlin)."""


class NoopResponse(_Singleton):
    """EC_OP_NOOP (data object en Kotlin)."""


class EmptyPreferencesResponse(_Singleton):
    """EC_OP_SET_PREFERENCES sin tags."""


@dataclass
class PrefsCategoriesResponse(Response):
    categories: List[AmuleCategory]


# --- Búsqueda -----------------------------------------------------------------


class SearchFileDownloadStatus(Enum):
    NEW = ECSearchFileDownloadStatus.NEW
    DOWNLOADED = ECSearchFileDownloadStatus.DOWNLOADED
    QUEUED = ECSearchFileDownloadStatus.QUEUED
    CANCELED = ECSearchFileDownloadStatus.CANCELED
    QUEUEDCANCELED = ECSearchFileDownloadStatus.QUEUEDCANCELED

    @classmethod
    def from_ec_status(cls, ec_status: ECSearchFileDownloadStatus) -> "SearchFileDownloadStatus":
        return next(s for s in cls if s.value == ec_status)


@dataclass
class SearchFile:
    file_name: str
    hash: bytes
    size_full: int
    download_status: SearchFileDownloadStatus
    complete_source_count: int
    source_count: int


@dataclass
class SearchResultsResponse(Response):
    files: List[SearchFile]


@dataclass
class SearchStatusResponse(Response):
    status: float


# --- Cola de descargas / ficheros compartidos ---------------------------------


@dataclass
class DownloadQueueResponse(Response):
    part_files: List["PartFileTag"]  # type: ignore[name-defined]


@dataclass
class SharedFilesResponse(Response):
    shared_files: List["SharedFileTag"]  # type: ignore[name-defined]


# --- Estadísticas -------------------------------------------------------------


class BuddyState(Enum):
    Disconnected = 0
    Connecting = 1
    Connected = 2

    @classmethod
    def from_byte(cls, value: int) -> Optional["BuddyState"]:
        try:
            return cls(value)
        except ValueError:
            return None


@dataclass
class ConnectionState:
    ed2k_connected: bool
    ed2k_connecting: bool
    kad_connected: bool
    kad_firewalled: bool
    kad_running: bool
    server_ipv4: Optional[Ipv4]
    server_ping: Optional[int]
    server_prio: Optional[int]
    server_failed: Optional[int]
    server_static: Optional[bool]
    server_version: Optional[str]
    server_description: Optional[str]
    server_users: Optional[int]
    server_users_max: Optional[int]
    server_files: Optional[int]
    ed2k_id: Optional[int]
    kad_id: Optional[int]
    client_id: Optional[int]

    @staticmethod
    def from_con_state_tag(tag: Tag) -> "ConnectionState":
        byte = as_byte(tag).get_value()
        server_tag = next(
            (t for t in tag.subtags if t.name == ECTagName.EC_TAG_SERVER), None
        )

        def sub_num(t: Optional[Tag], name: ECTagName):
            if t is None:
                return None
            found = find_numeric(t.subtags, name)
            return found.get_int() if found is not None else None

        def sub_str(t: Optional[Tag], name: ECTagName):
            if t is None:
                return None
            found = find_string(t.subtags, name)
            return found.get_value() if found is not None else None

        static_raw = sub_num(server_tag, ECTagName.EC_TAG_SERVER_STATIC)

        server_ipv4 = None
        if server_tag is not None:
            ipv4_tag = as_ipv4(server_tag)
            if ipv4_tag is not None:
                server_ipv4 = ipv4_tag.get_value()

        ed2k_id = find_numeric(tag.subtags, ECTagName.EC_TAG_ED2K_ID)
        kad_id = find_numeric(tag.subtags, ECTagName.EC_TAG_KAD_ID)
        client_id = find_numeric(tag.subtags, ECTagName.EC_TAG_CLIENT_ID)

        return ConnectionState(
            ed2k_connected=(byte & 0x01) != 0,
            ed2k_connecting=(byte & 0x02) != 0,
            kad_connected=(byte & 0x04) != 0,
            kad_firewalled=(byte & 0x08) != 0,
            kad_running=(byte & 0x10) != 0,
            ed2k_id=ed2k_id.get_int() if ed2k_id is not None else None,
            kad_id=kad_id.get_int() if kad_id is not None else None,
            client_id=client_id.get_int() if client_id is not None else None,
            server_ipv4=server_ipv4,
            server_ping=sub_num(server_tag, ECTagName.EC_TAG_SERVER_PING),
            server_prio=sub_num(server_tag, ECTagName.EC_TAG_SERVER_PRIO),
            server_failed=sub_num(server_tag, ECTagName.EC_TAG_SERVER_FAILED),
            server_static=(static_raw != 0) if static_raw is not None else None,
            server_version=sub_str(server_tag, ECTagName.EC_TAG_SERVER_VERSION),
            server_description=sub_str(server_tag, ECTagName.EC_TAG_SERVER_DESC),
            server_users=sub_num(server_tag, ECTagName.EC_TAG_SERVER_USERS),
            server_users_max=sub_num(server_tag, ECTagName.EC_TAG_SERVER_USERS_MAX),
            server_files=sub_num(server_tag, ECTagName.EC_TAG_SERVER_FILES),
        )


@dataclass
class StatsResponse(Response):
    connection_state: Optional[ConnectionState]
    upload_overhead: int
    download_overhead: int
    banned_count: int
    logger_message: List[str]
    total_sent_bytes: int
    total_received_bytes: int
    shared_file_count: int
    upload_speed: int
    download_speed: int
    upload_speed_limit: int
    download_speed_limit: int
    upload_queue_length: int
    total_source_count: int
    ed2k_users: int
    kad_users: int
    ed2k_files: int
    kad_files: int
    kad_nodes: int
    kad_firewalled_udp: Optional[bool]
    kad_indexed_sources: Optional[int]
    kad_indexed_keywords: Optional[int]
    kad_indexed_notes: Optional[int]
    kad_indexed_load: Optional[int]
    kad_ip_address: Optional[str]
    kad_is_running_in_lan_mode: Optional[bool]
    buddy_status: Optional[BuddyState]
    buddy_ip: Optional[str]
    buddy_port: Optional[int]


def _int_to_ipv4(value: int) -> str:
    """Convierte un entero de 32 bits (big-endian) en ``a.b.c.d``."""
    packed = struct.pack(">I", value & 0xFFFFFFFF)
    return ".".join(str(b) for b in packed)


# --- ResponseParser -----------------------------------------------------------


def _num_or_zero(packet: Packet, name: ECTagName) -> int:
    tag = find_numeric(packet.tags, name)
    return tag.get_long() if tag is not None else 0


def _parse_stats(packet: Packet) -> StatsResponse:
    conn_tag = next(
        (t for t in packet.tags if t.name == ECTagName.EC_TAG_CONNSTATE), None
    )
    logger_tag = next(
        (t for t in packet.tags if t.name == ECTagName.EC_TAG_STATS_LOGGER_MESSAGE),
        None,
    )
    logger_message: List[str] = []
    if logger_tag is not None:
        logger_message = [
            t.get_value()
            for t in logger_tag.subtags
            if t.name == ECTagName.EC_TAG_STRING and isinstance(t, StringTag)
        ]

    fw_udp = find_byte(packet.tags, ECTagName.EC_TAG_STATS_KAD_FIREWALLED_UDP)
    lan = find_byte(packet.tags, ECTagName.EC_TAG_STATS_KAD_IN_LAN_MODE)
    buddy = find_byte(packet.tags, ECTagName.EC_TAG_STATS_BUDDY_STATUS)
    kad_ip = find_int(packet.tags, ECTagName.EC_TAG_STATS_KAD_IP_ADRESS)
    buddy_ip = find_int(packet.tags, ECTagName.EC_TAG_STATS_BUDDY_IP)
    buddy_port = find_short(packet.tags, ECTagName.EC_TAG_STATS_BUDDY_PORT)

    def opt_num(name: ECTagName) -> Optional[int]:
        tag = find_numeric(packet.tags, name)
        return tag.get_long() if tag is not None else None

    return StatsResponse(
        connection_state=ConnectionState.from_con_state_tag(conn_tag)
        if conn_tag is not None
        else None,
        upload_overhead=_num_or_zero(packet, ECTagName.EC_TAG_STATS_UP_OVERHEAD),
        download_overhead=_num_or_zero(packet, ECTagName.EC_TAG_STATS_DOWN_OVERHEAD),
        banned_count=_num_or_zero(packet, ECTagName.EC_TAG_STATS_BANNED_COUNT),
        logger_message=logger_message,
        total_sent_bytes=_num_or_zero(packet, ECTagName.EC_TAG_STATS_TOTAL_SENT_BYTES),
        total_received_bytes=_num_or_zero(
            packet, ECTagName.EC_TAG_STATS_TOTAL_RECEIVED_BYTES
        ),
        shared_file_count=_num_or_zero(
            packet, ECTagName.EC_TAG_STATS_SHARED_FILE_COUNT
        ),
        upload_speed=_num_or_zero(packet, ECTagName.EC_TAG_STATS_UL_SPEED),
        download_speed=_num_or_zero(packet, ECTagName.EC_TAG_STATS_DL_SPEED),
        upload_speed_limit=_num_or_zero(packet, ECTagName.EC_TAG_STATS_UL_SPEED_LIMIT),
        download_speed_limit=_num_or_zero(
            packet, ECTagName.EC_TAG_STATS_DL_SPEED_LIMIT
        ),
        upload_queue_length=_num_or_zero(packet, ECTagName.EC_TAG_STATS_UL_QUEUE_LEN),
        total_source_count=_num_or_zero(
            packet, ECTagName.EC_TAG_STATS_TOTAL_SRC_COUNT
        ),
        ed2k_users=_num_or_zero(packet, ECTagName.EC_TAG_STATS_ED2K_USERS),
        kad_users=_num_or_zero(packet, ECTagName.EC_TAG_STATS_KAD_USERS),
        ed2k_files=_num_or_zero(packet, ECTagName.EC_TAG_STATS_ED2K_FILES),
        kad_files=_num_or_zero(packet, ECTagName.EC_TAG_STATS_KAD_FILES),
        kad_nodes=_num_or_zero(packet, ECTagName.EC_TAG_STATS_KAD_NODES),
        kad_firewalled_udp=(fw_udp.get_value() != 0) if fw_udp is not None else None,
        kad_indexed_sources=opt_num(ECTagName.EC_TAG_STATS_KAD_INDEXED_SOURCES),
        kad_indexed_keywords=opt_num(ECTagName.EC_TAG_STATS_KAD_INDEXED_KEYWORDS),
        kad_indexed_notes=opt_num(ECTagName.EC_TAG_STATS_KAD_INDEXED_NOTES),
        kad_indexed_load=opt_num(ECTagName.EC_TAG_STATS_KAD_INDEXED_LOAD),
        kad_ip_address=_int_to_ipv4(kad_ip.get_value()) if kad_ip is not None else None,
        kad_is_running_in_lan_mode=(lan.get_value() != 0) if lan is not None else None,
        buddy_status=BuddyState.from_byte(buddy.get_value())
        if buddy is not None
        else None,
        buddy_ip=_int_to_ipv4(buddy_ip.get_value()) if buddy_ip is not None else None,
        buddy_port=buddy_port.get_value() if buddy_port is not None else None,
    )


def _parse_search_results(packet: Packet) -> SearchResultsResponse:
    files: List[SearchFile] = []
    for tag in packet.tags:
        if tag.name != ECTagName.EC_TAG_SEARCHFILE:
            raise CommunicationException(
                f"Unexpected tag {tag.name} in SearchResultsResponse"
            )
        size = find_numeric(tag.subtags, ECTagName.EC_TAG_PARTFILE_SIZE_FULL)
        xfer = find_numeric(tag.subtags, ECTagName.EC_TAG_PARTFILE_SOURCE_COUNT_XFER)
        src = find_numeric(tag.subtags, ECTagName.EC_TAG_PARTFILE_SOURCE_COUNT)
        status_byte = find_byte(tag.subtags, ECTagName.EC_TAG_PARTFILE_STATUS).get_value()
        files.append(
            SearchFile(
                file_name=find_string(
                    tag.subtags, ECTagName.EC_TAG_PARTFILE_NAME
                ).get_value(),
                hash=find_hash16(
                    tag.subtags, ECTagName.EC_TAG_PARTFILE_HASH
                ).get_value(),
                size_full=size.get_long() if size is not None else 0,
                download_status=SearchFileDownloadStatus.from_ec_status(
                    ECSearchFileDownloadStatus(status_byte)
                ),
                complete_source_count=xfer.get_int() if xfer is not None else 0,
                source_count=src.get_int() if src is not None else 0,
            )
        )
    return SearchResultsResponse(files)


def _parse_search_status(packet: Packet) -> SearchStatusResponse:
    num = find_numeric(packet.tags, ECTagName.EC_TAG_SEARCH_STATUS).get_int()
    # Búsquedas locales devuelven 0xFFFF; Kad devuelve 0xFFFE al terminar.
    status = 1.0 if num in (0xFFFF, 0xFFFE) else num / 100.0
    return SearchStatusResponse(status)


def _parse_prefs_categories(packet: Packet) -> PrefsCategoriesResponse:
    container = find_custom(packet.tags, ECTagName.EC_TAG_PREFS_CATEGORIES)
    categories: List[AmuleCategory] = []
    for cat in container.subtags:
        if cat.name != ECTagName.EC_TAG_CATEGORY:
            continue
        categories.append(
            AmuleCategory(
                id=as_numeric(cat).get_long(),
                name=find_string(cat.subtags, ECTagName.EC_TAG_CATEGORY_TITLE).get_value(),
                path=find_string(cat.subtags, ECTagName.EC_TAG_CATEGORY_PATH).get_value(),
                comment=find_string(
                    cat.subtags, ECTagName.EC_TAG_CATEGORY_COMMENT
                ).get_value(),
                priority=find_byte(
                    cat.subtags, ECTagName.EC_TAG_CATEGORY_PRIO
                ).get_value(),
                color=find_numeric(
                    cat.subtags, ECTagName.EC_TAG_CATEGORY_COLOR
                ).get_int(),
            )
        )
    return PrefsCategoriesResponse(categories)


def parse(packet: Packet) -> Response:
    """Devuelve la respuesta de dominio correspondiente al paquete.

    Importa los tags especiales de forma diferida para evitar un ciclo de
    importación con :mod:`amarr.jamule.model`.
    """
    from .model import PartFileTag, SharedFileTag

    op = packet.op_code

    if op == ECOpCode.EC_OP_AUTH_FAIL:
        return AuthFailedResponse(
            find_string(packet.tags, ECTagName.EC_TAG_STRING).get_value()
        )
    if op == ECOpCode.EC_OP_AUTH_OK:
        return AuthOkResponse(
            find_string(packet.tags, ECTagName.EC_TAG_SERVER_VERSION).get_value()
        )
    if op == ECOpCode.EC_OP_AUTH_SALT:
        return AuthSaltResponse(
            find_long(packet.tags, ECTagName.EC_TAG_PASSWD_SALT).get_value()
        )
    if op == ECOpCode.EC_OP_DLOAD_QUEUE:
        return DownloadQueueResponse(
            [
                PartFileTag.from_subtags(t.subtags)
                for t in packet.tags
                if t.name == ECTagName.EC_TAG_PARTFILE
            ]
        )
    if op == ECOpCode.EC_OP_SET_PREFERENCES and not packet.tags:
        return EmptyPreferencesResponse()
    if op == ECOpCode.EC_OP_FAILED:
        msg_tag = find_string(packet.tags, ECTagName.EC_TAG_STRING)
        return ErrorResponse(msg_tag.get_value() if msg_tag is not None else "Unknown error")
    if op == ECOpCode.EC_OP_MISC_DATA:
        return MiscDataResponse()
    if op == ECOpCode.EC_OP_NOOP:
        return NoopResponse()
    if op == ECOpCode.EC_OP_SET_PREFERENCES and find_custom(
        packet.tags, ECTagName.EC_TAG_PREFS_CATEGORIES
    ) is not None:
        return _parse_prefs_categories(packet)
    if op == ECOpCode.EC_OP_SEARCH_RESULTS:
        return _parse_search_results(packet)
    if op == ECOpCode.EC_OP_SEARCH_PROGRESS:
        return _parse_search_status(packet)
    if op == ECOpCode.EC_OP_SHARED_FILES:
        return SharedFilesResponse(
            [
                SharedFileTag.from_subtags(t.subtags)
                for t in packet.tags
                if t.name == ECTagName.EC_TAG_KNOWNFILE
            ]
        )
    if op == ECOpCode.EC_OP_STATS:
        return _parse_stats(packet)
    if op == ECOpCode.EC_OP_STRINGS:
        msg_tag = find_string(packet.tags, ECTagName.EC_TAG_STRING)
        return StringsResponse(msg_tag.get_value() if msg_tag is not None else "")

    raise CommunicationException(f"No deserializer found for opCode {op}")
