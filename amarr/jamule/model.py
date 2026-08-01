"""jaMule domain models.

Translation of ``jamule/model/*.kt`` and ``jamule/ec/tag/special/*.kt``.

In Kotlin ``AmuleFile`` and ``AmuleTransferringFile`` are *interfaces* and
``PartFileTag`` reuses ``SharedFileTag`` through delegation
(``AmuleFile by sharedFileTag``). In Python we model it with dataclasses:
``SharedFileTag`` contains all the fields of ``AmuleFile`` and ``PartFileTag``
inherits from it adding the fields of ``AmuleTransferringFile``. This way a
``PartFileTag`` is both a shared file and a transferring file,
just like in the original.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from .ec.codes import ECOpCode, ECTagName
from .ec.tag import (
    Tag,
    find_byte,
    find_hash16,
    find_numeric,
    find_string,
)


class FileStatus(Enum):
    """State of a part-file in aMule.

    The lowercase names match the textual value that aMule sends.
    """

    READY = 0
    EMPTY = 1
    WAITINGFORHASH = 2
    HASHING = 3
    ERROR = 4
    INSUFFICIENT = 5
    UNKNOWN = 6
    PAUSED = 7
    COMPLETING = 8
    COMPLETE = 9
    ALLOCATING = 10

    @classmethod
    def from_value(cls, value: int) -> "FileStatus":
        return cls(value)


class DownloadCommand(Enum):
    """Commands applicable to a download.

    Each command is associated with the ``ECOpCode`` used as the *opcode* of the
    request packet.
    """

    SWAP_A4AF_THIS = ECOpCode.EC_OP_PARTFILE_SWAP_A4AF_THIS
    SWAP_A4AF_THIS_AUTO = ECOpCode.EC_OP_PARTFILE_SWAP_A4AF_THIS_AUTO
    SWAP_A4AF_OTHERS = ECOpCode.EC_OP_PARTFILE_SWAP_A4AF_OTHERS
    PAUSE = ECOpCode.EC_OP_PARTFILE_PAUSE
    RESUME = ECOpCode.EC_OP_PARTFILE_RESUME
    STOP = ECOpCode.EC_OP_PARTFILE_STOP
    DELETE = ECOpCode.EC_OP_PARTFILE_DELETE


@dataclass
class AmuleCategory:
    """aMule category (``jamule/model/AmuleCategory.kt``)."""

    id: int
    name: str
    path: str = ""
    comment: str = ""
    color: int = 0
    priority: int = 0


def _to_signed_byte(value: int) -> int:
    """Converts a ``UByte`` (0..255) to Kotlin's signed range (-128..127)."""
    return value - 256 if value >= 128 else value


# aMule omits tags depending on the file state or version (e.g.
# HASHED_PART_COUNT in freshly added part-files); these accessors return a
# default value instead of assuming the tag always arrives — a missing tag
# took down /api/v2/torrents/info with a 500 (AttributeError on None).


def _byte_or(subtags: List[Tag], name: ECTagName, default: int = 0) -> int:
    tag = find_byte(subtags, name)
    return tag.get_value() if tag is not None else default


def _short_or(subtags: List[Tag], name: ECTagName, default: int = 0) -> int:
    tag = find_numeric(subtags, name)
    return tag.get_short() if tag is not None else default


def _int_or(subtags: List[Tag], name: ECTagName, default: int = 0) -> int:
    tag = find_numeric(subtags, name)
    return tag.get_int() if tag is not None else default


def _long_or(subtags: List[Tag], name: ECTagName, default: int = 0) -> int:
    tag = find_numeric(subtags, name)
    return tag.get_long() if tag is not None else default


@dataclass
class SharedFileTag:
    """Shared file known to aMule.

    Equivalent to the ``AmuleFile`` interface + the ``SharedFileTag`` parser.
    """

    file_hash_hex_string: Optional[str]
    file_name: Optional[str]
    file_path: Optional[str]
    size_full: Optional[int]
    file_ed2k_link: Optional[str]

    up_prio: int
    get_requests: int
    get_all_requests: int
    get_accepts: int
    get_all_accepts: int
    get_xferred: int
    get_all_xferred: int
    get_complete_sources_low: int
    get_complete_sources_high: int
    get_complete_sources: int
    get_on_queue: int
    get_comment: Optional[str]
    get_rating: Optional[int]

    @staticmethod
    def from_subtags(subtags: List[Tag]) -> "SharedFileTag":
        hash_tag = find_hash16(subtags, ECTagName.EC_TAG_PARTFILE_HASH)
        file_hash = hash_tag.get_value().hex() if hash_tag is not None else None

        name_tag = find_string(subtags, ECTagName.EC_TAG_PARTFILE_NAME)
        path_tag = find_string(subtags, ECTagName.EC_TAG_KNOWNFILE_FILENAME)
        ed2k_tag = find_string(subtags, ECTagName.EC_TAG_PARTFILE_ED2K_LINK)
        size_tag = find_numeric(subtags, ECTagName.EC_TAG_PARTFILE_SIZE_FULL)
        comment_tag = find_string(subtags, ECTagName.EC_TAG_KNOWNFILE_COMMENT)
        rating_tag = find_byte(subtags, ECTagName.EC_TAG_KNOWNFILE_RATING)

        return SharedFileTag(
            file_hash_hex_string=file_hash,
            file_name=name_tag.get_value() if name_tag is not None else None,
            file_path=path_tag.get_value() if path_tag is not None else None,
            size_full=size_tag.get_long() if size_tag is not None else None,
            file_ed2k_link=ed2k_tag.get_value() if ed2k_tag is not None else None,
            up_prio=_to_signed_byte(
                _byte_or(subtags, ECTagName.EC_TAG_KNOWNFILE_PRIO)
            ),
            get_requests=_short_or(subtags, ECTagName.EC_TAG_KNOWNFILE_REQ_COUNT),
            get_all_requests=_int_or(
                subtags, ECTagName.EC_TAG_KNOWNFILE_REQ_COUNT_ALL
            ),
            get_accepts=_short_or(subtags, ECTagName.EC_TAG_KNOWNFILE_ACCEPT_COUNT),
            get_all_accepts=_int_or(
                subtags, ECTagName.EC_TAG_KNOWNFILE_ACCEPT_COUNT_ALL
            ),
            get_xferred=_long_or(subtags, ECTagName.EC_TAG_KNOWNFILE_XFERRED),
            get_all_xferred=_long_or(subtags, ECTagName.EC_TAG_KNOWNFILE_XFERRED_ALL),
            get_complete_sources_low=_short_or(
                subtags, ECTagName.EC_TAG_KNOWNFILE_COMPLETE_SOURCES_LOW
            ),
            get_complete_sources_high=_short_or(
                subtags, ECTagName.EC_TAG_KNOWNFILE_COMPLETE_SOURCES_HIGH
            ),
            get_complete_sources=_short_or(
                subtags, ECTagName.EC_TAG_KNOWNFILE_COMPLETE_SOURCES
            ),
            get_on_queue=_short_or(subtags, ECTagName.EC_TAG_KNOWNFILE_ON_QUEUE),
            get_comment=comment_tag.get_value() if comment_tag is not None else None,
            get_rating=_to_signed_byte(rating_tag.get_value())
            if rating_tag is not None
            else None,
        )


@dataclass
class PartFileTag(SharedFileTag):
    """File being transferred.

    Equivalent to ``AmuleTransferringFile`` (which extends ``AmuleFile``). Inherits
    from :class:`SharedFileTag` and adds the download-specific fields.
    """

    part_met_id: Optional[int] = None
    size_xfer: Optional[int] = None
    size_done: Optional[int] = None
    file_status: FileStatus = FileStatus.UNKNOWN
    stopped: bool = False
    source_count: int = 0
    source_not_curr_count: int = 0
    source_xfer_count: int = 0
    source_count_a4af: int = 0
    speed: Optional[int] = None
    down_prio: int = 0
    file_cat: int = 0
    last_seen_complete: int = 0
    last_date_changed: int = 0
    download_active_time: int = 0
    available_part_count: int = 0
    a4af_auto: bool = False
    hashing_progress: bool = False
    get_lost_due_to_corruption: int = 0
    get_gain_due_to_compression: int = 0
    total_packets_saved_due_to_ich: int = 0

    @staticmethod
    def from_subtags(subtags: List[Tag]) -> "PartFileTag":
        base = SharedFileTag.from_subtags(subtags)

        def num(name: ECTagName):
            return find_numeric(subtags, name)

        part_met = num(ECTagName.EC_TAG_PARTFILE_PARTMETID)
        size_xfer = num(ECTagName.EC_TAG_PARTFILE_SIZE_XFER)
        size_done = num(ECTagName.EC_TAG_PARTFILE_SIZE_DONE)
        speed = num(ECTagName.EC_TAG_PARTFILE_SPEED)

        return PartFileTag(
            # Fields inherited from SharedFileTag.
            file_hash_hex_string=base.file_hash_hex_string,
            file_name=base.file_name,
            file_path=base.file_path,
            size_full=base.size_full,
            file_ed2k_link=base.file_ed2k_link,
            up_prio=base.up_prio,
            get_requests=base.get_requests,
            get_all_requests=base.get_all_requests,
            get_accepts=base.get_accepts,
            get_all_accepts=base.get_all_accepts,
            get_xferred=base.get_xferred,
            get_all_xferred=base.get_all_xferred,
            get_complete_sources_low=base.get_complete_sources_low,
            get_complete_sources_high=base.get_complete_sources_high,
            get_complete_sources=base.get_complete_sources,
            get_on_queue=base.get_on_queue,
            get_comment=base.get_comment,
            get_rating=base.get_rating,
            # Fields specific to AmuleTransferringFile.
            part_met_id=part_met.get_short() if part_met is not None else None,
            size_xfer=size_xfer.get_long() if size_xfer is not None else None,
            size_done=size_done.get_long() if size_done is not None else None,
            file_status=FileStatus.from_value(
                _byte_or(
                    subtags,
                    ECTagName.EC_TAG_PARTFILE_STATUS,
                    FileStatus.UNKNOWN.value,
                )
            ),
            stopped=_byte_or(subtags, ECTagName.EC_TAG_PARTFILE_STOPPED) != 0,
            source_count=_short_or(subtags, ECTagName.EC_TAG_PARTFILE_SOURCE_COUNT),
            source_not_curr_count=_short_or(
                subtags, ECTagName.EC_TAG_PARTFILE_SOURCE_COUNT_NOT_CURRENT
            ),
            source_xfer_count=_short_or(
                subtags, ECTagName.EC_TAG_PARTFILE_SOURCE_COUNT_XFER
            ),
            source_count_a4af=_short_or(
                subtags, ECTagName.EC_TAG_PARTFILE_SOURCE_COUNT_A4AF
            ),
            speed=speed.get_long() if speed is not None else None,
            down_prio=_to_signed_byte(
                _byte_or(subtags, ECTagName.EC_TAG_PARTFILE_PRIO)
            ),
            file_cat=_long_or(subtags, ECTagName.EC_TAG_PARTFILE_CAT),
            last_seen_complete=_long_or(
                subtags, ECTagName.EC_TAG_PARTFILE_LAST_SEEN_COMP
            ),
            last_date_changed=_long_or(subtags, ECTagName.EC_TAG_PARTFILE_LAST_RECV),
            download_active_time=_int_or(
                subtags, ECTagName.EC_TAG_PARTFILE_DOWNLOAD_ACTIVE
            ),
            available_part_count=_short_or(
                subtags, ECTagName.EC_TAG_PARTFILE_AVAILABLE_PARTS
            ),
            a4af_auto=_byte_or(subtags, ECTagName.EC_TAG_PARTFILE_A4AFAUTO) != 0,
            hashing_progress=_byte_or(
                subtags, ECTagName.EC_TAG_PARTFILE_HASHED_PART_COUNT
            )
            != 0,
            get_lost_due_to_corruption=_long_or(
                subtags, ECTagName.EC_TAG_PARTFILE_LOST_CORRUPTION
            ),
            get_gain_due_to_compression=_long_or(
                subtags, ECTagName.EC_TAG_PARTFILE_GAINED_COMPRESSION
            ),
            total_packets_saved_due_to_ich=_int_or(
                subtags, ECTagName.EC_TAG_PARTFILE_SAVED_ICH
            ),
        )


# Type aliases: amarr uses the interface names.
AmuleFile = SharedFileTag
AmuleTransferringFile = PartFileTag
