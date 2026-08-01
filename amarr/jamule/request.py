"""EC request builders (``jamule/request/*.kt``).

Each function/class produces a :class:`Packet` ready to send. In Kotlin they are
``data class``/``class`` that implement the ``Request`` interface with a
``packet()`` method; here they are modeled as factory functions (more idiomatic in
Python) except when it is convenient to keep parameters, in which case they are
functions with arguments. All the wire-format details live in :mod:`amarr.jamule.ec`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .ec.codes import (
    ECDetailLevel,
    ECOpCode,
    ECSearchType,
    ECTagName,
    EcPrefs,
    ProtocolVersion,
)
from .ec.packet import Flags, Packet
from .ec.tag import (
    CustomTag,
    Hash16Tag,
    StringTag,
    Tag,
    UByteTag,
    UIntTag,
    ULongTag,
    UShortTag,
)
from .model import AmuleCategory, DownloadCommand

# Client identification, same as ``AmuleClient.CLIENT_NAME`` and
# ``Build.VERSION`` in jaMule (supports aMule 2.3.1-2.3.3).
CLIENT_NAME = "jAmule"
CLIENT_VERSION = "for amule 2.3.3"


def salt_request() -> Packet:
    """EC_OP_AUTH_REQ: requests the *salt* to authenticate."""
    return Packet(
        ECOpCode.EC_OP_AUTH_REQ,
        [
            StringTag(ECTagName.EC_TAG_CLIENT_NAME, value=CLIENT_NAME),
            StringTag(ECTagName.EC_TAG_CLIENT_VERSION, value=CLIENT_VERSION),
            UShortTag(
                ECTagName.EC_TAG_PROTOCOL_VERSION,
                value=ProtocolVersion.EC_CURRENT_PROTOCOL_VERSION.value,
            ),
            CustomTag(ECTagName.EC_TAG_CAN_ZLIB, value=b""),
            CustomTag(ECTagName.EC_TAG_CAN_UTF8_NUMBERS, value=b""),
        ],
        Flags(),
    )


def auth_request(hashed_password: bytes) -> Packet:
    """EC_OP_AUTH_PASSWD: sends the password hash with the salt."""
    return Packet(
        ECOpCode.EC_OP_AUTH_PASSWD,
        [Hash16Tag(ECTagName.EC_TAG_PASSWD_HASH, value=hashed_password)],
        Flags(),
    )


def stats_request() -> Packet:
    """EC_OP_STAT_REQ: full core statistics."""
    return Packet(
        ECOpCode.EC_OP_STAT_REQ,
        [UByteTag(ECTagName.EC_TAG_DETAIL_LEVEL, value=ECDetailLevel.EC_DETAIL_FULL.value)],
        Flags(),
    )


def download_queue_request() -> Packet:
    """EC_OP_GET_DLOAD_QUEUE: download queue with full detail."""
    return Packet(
        ECOpCode.EC_OP_GET_DLOAD_QUEUE,
        [UByteTag(ECTagName.EC_TAG_DETAIL_LEVEL, value=ECDetailLevel.EC_DETAIL_FULL.value)],
    )


def shared_files_request() -> Packet:
    """EC_OP_GET_SHARED_FILES: shared files with full detail."""
    return Packet(
        ECOpCode.EC_OP_GET_SHARED_FILES,
        [UByteTag(ECTagName.EC_TAG_DETAIL_LEVEL, value=ECDetailLevel.EC_DETAIL_FULL.value)],
    )


def add_link_request(link: str) -> Packet:
    """EC_OP_ADD_LINK: adds a download from an ed2k link."""
    return Packet(
        ECOpCode.EC_OP_ADD_LINK,
        [StringTag(ECTagName.EC_TAG_PARTFILE_ED2K_LINK, value=link)],
    )


def search_status_request() -> Packet:
    """EC_OP_SEARCH_PROGRESS: progress (0..100%) of the ongoing search."""
    return Packet(ECOpCode.EC_OP_SEARCH_PROGRESS, [])


def search_results_request() -> Packet:
    """EC_OP_SEARCH_RESULTS: results of the ongoing search."""
    return Packet(ECOpCode.EC_OP_SEARCH_RESULTS, [])


def search_stop_request() -> Packet:
    """EC_OP_SEARCH_STOP: stops the ongoing search."""
    return Packet(ECOpCode.EC_OP_SEARCH_STOP, [])


def get_preferences_request(prefs: EcPrefs) -> Packet:
    """EC_OP_GET_PREFERENCES: reads a block of preferences from the core."""
    return Packet(
        ECOpCode.EC_OP_GET_PREFERENCES,
        [
            UByteTag(ECTagName.EC_TAG_DETAIL_LEVEL, value=ECDetailLevel.EC_DETAIL_FULL.value),
            UIntTag(ECTagName.EC_TAG_SELECT_PREFS, value=prefs.value),
        ],
    )


def download_command_request(file_hash: bytes, status: DownloadCommand) -> Packet:
    """Command on a download (pause, resume, delete...).

    The packet *opcode* is the one associated with the command (``status.value``).
    """
    return Packet(
        status.value,
        [Hash16Tag(ECTagName.EC_TAG_PARTFILE, value=file_hash)],
    )


def download_search_result_request(file_hash: bytes) -> Packet:
    """EC_OP_DOWNLOAD_SEARCH_RESULT: downloads a search result."""
    return Packet(
        ECOpCode.EC_OP_DOWNLOAD_SEARCH_RESULT,
        [Hash16Tag(ECTagName.EC_TAG_PARTFILE, value=file_hash)],
    )


def set_file_category_request(file_hash: bytes, category: int) -> Packet:
    """EC_OP_PARTFILE_SET_CAT: assigns a category to a download."""
    return Packet(
        ECOpCode.EC_OP_PARTFILE_SET_CAT,
        [
            Hash16Tag(
                ECTagName.EC_TAG_PARTFILE,
                value=file_hash,
                subtags=[ULongTag(ECTagName.EC_TAG_PARTFILE_CAT, value=category)],
            )
        ],
    )


def create_category_request(category: AmuleCategory) -> Packet:
    """EC_OP_CREATE_CATEGORY: creates a category in aMule."""
    return Packet(
        ECOpCode.EC_OP_CREATE_CATEGORY,
        [
            UIntTag(
                ECTagName.EC_TAG_CATEGORY,
                value=category.id,
                subtags=[
                    StringTag(ECTagName.EC_TAG_CATEGORY_TITLE, value=category.name),
                    StringTag(ECTagName.EC_TAG_CATEGORY_PATH, value=category.path),
                    StringTag(ECTagName.EC_TAG_CATEGORY_COMMENT, value=category.comment),
                    UByteTag(ECTagName.EC_TAG_CATEGORY_COLOR, value=category.color & 0xFF),
                    UIntTag(ECTagName.EC_TAG_CATEGORY_PRIO, value=category.priority),
                ],
            )
        ],
    )


class SearchType(Enum):
    """Scope of the search."""

    GLOBAL = ECSearchType.EC_SEARCH_GLOBAL
    KAD = ECSearchType.EC_SEARCH_KAD
    LOCAL = ECSearchType.EC_SEARCH_LOCAL
    WEB = ECSearchType.EC_SEARCH_WEB


@dataclass
class SearchFilters:
    """Optional filters for a search."""

    filetype: Optional[str] = None
    extension: Optional[str] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    availability: Optional[int] = None


def search_request(
    query: str,
    type: SearchType,
    filters: Optional[SearchFilters] = None,
) -> Packet:
    """EC_OP_SEARCH_START: starts an asynchronous search.

    The searched name goes as a subtag of the search-type tag; the filters
    (if any) go as sibling tags at the root level.
    """
    filters = filters or SearchFilters()
    tags: List[Tag] = [
        UByteTag(
            ECTagName.EC_TAG_SEARCH_TYPE,
            value=type.value.value,
            subtags=[StringTag(ECTagName.EC_TAG_SEARCH_NAME, value=query)],
        )
    ]
    if filters.filetype is not None:
        tags.append(StringTag(ECTagName.EC_TAG_SEARCH_FILE_TYPE, value=filters.filetype))
    if filters.extension is not None:
        tags.append(StringTag(ECTagName.EC_TAG_SEARCH_EXTENSION, value=filters.extension))
    if filters.min_size is not None:
        tags.append(ULongTag(ECTagName.EC_TAG_SEARCH_MIN_SIZE, value=filters.min_size))
    if filters.max_size is not None:
        tags.append(ULongTag(ECTagName.EC_TAG_SEARCH_MAX_SIZE, value=filters.max_size))
    if filters.availability is not None:
        tags.append(
            ULongTag(ECTagName.EC_TAG_SEARCH_AVAILABILITY, value=filters.availability)
        )
    return Packet(ECOpCode.EC_OP_SEARCH_START, tags)
