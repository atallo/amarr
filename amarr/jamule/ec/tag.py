"""EC protocol tag system: types, encoding and parsing.

Gathers in a single module the port of:

* ``jamule/ec/tag/Tag.kt``        -> :class:`Tag` class and subclasses.
* ``jamule/ec/tag/TagEncoder.kt`` -> :class:`TagEncoder`.
* ``jamule/ec/tag/TagParser.kt``  -> :class:`TagParser`.
* The typed accessors that in Kotlin lived in ``Packet.Companion``
  (``Iterable<Tag<*>>.byte(name)`` etc.).

An EC tag is serialized as::

    [name+subtags_flag : uint16] [type : uint8] [length : uint32]
    [ (if it has subtags) subtag_count : uint16  subtags... ] [value]

where the header numbers go in binary or in UTF-8 depending on the packet's UTF8
flag (see :mod:`amarr.jamule.ec.encoding`). The ``length`` is computed
**always with fixed header sizes** (not UTF-8): it is the "theoretical length"
shared by encoder and parser. This convention, though peculiar, is the one
aMule uses and is respected as is.
"""

from __future__ import annotations

import logging
from typing import Optional

from .codes import ECTagName, ECTagType
from . import encoding as enc

_logger = logging.getLogger(__name__)

# Sentinel to distinguish "unset value" from a legitimate value (e.g. 0).
_UNSET = object()

# Fixed header sizes used for the "theoretical length" (TagParser.kt)
TAG_NAME_SIZE = enc.LEN_USHORT
TAG_TYPE_SIZE = enc.LEN_UBYTE
TAG_LENGTH_SIZE = enc.LEN_UINT
SUBTAG_COUNT_SIZE = enc.LEN_USHORT


class Tag:
    """Base class for all tags. Do not instantiate directly."""

    type: ECTagType = ECTagType.EC_TAGTYPE_UNKNOWN

    def __init__(
        self,
        name: ECTagName,
        subtags: Optional[list["Tag"]] = None,
        name_value: Optional[int] = None,
        value: object = _UNSET,
    ) -> None:
        self.name = name
        self.subtags: list[Tag] = subtags if subtags is not None else []
        # ``name_value`` keeps the raw value of the name (relevant when the
        # name is not recognized and ``name`` stays as EC_TAG_UNKNOWN).
        self.name_value = name_value if name_value is not None else name.value
        self._value = value

    # --- value management ---------------------------------------------------
    def get_value(self):
        return self._value

    def set_value(self, value) -> None:
        if self._value is not _UNSET:
            raise RuntimeError("Tag value already set")
        self._value = value

    # --- serialization (to be implemented by subclasses) --------------------
    def parse_value(self, data: bytes) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def encode_value(self) -> bytes:  # pragma: no cover - abstract
        raise NotImplementedError

    # --- numeric interface (only valid in numeric subclasses) ---------------
    def get_short(self) -> int:
        raise TypeError(f"{type(self).__name__} is not numeric")

    def get_int(self) -> int:
        raise TypeError(f"{type(self).__name__} is not numeric")

    def get_long(self) -> int:
        raise TypeError(f"{type(self).__name__} is not numeric")

    def __repr__(self) -> str:
        val = self._value if self._value is not _UNSET else "<unset>"
        return f"{type(self).__name__}({self.name.name}, value={val!r})"

    def __eq__(self, other: object) -> bool:
        # Parity with Kotlin's ``data class``: ``equals`` is generated over
        # ``name``, ``subtags`` and ``nameValue``, but **not** over the value (which
        # is a private field outside the primary constructor). That is why two tags
        # with the same name and subtags are considered equal even if their value
        # differs. The value is compared explicitly with ``get_value()``.
        if type(self) is not type(other):
            return False
        assert isinstance(other, Tag)
        return (
            self.name == other.name
            and self.name_value == other.name_value
            and self.subtags == other.subtags
        )


class _NumericTag(Tag):
    """Marker mixin for the integer tags (``NumericTag`` in Kotlin)."""


class CustomTag(Tag):
    """Tag of opaque bytes (``EC_TAGTYPE_CUSTOM``)."""

    type = ECTagType.EC_TAGTYPE_CUSTOM

    def encode_value(self) -> bytes:
        return bytes(self.get_value())

    def parse_value(self, data: bytes) -> None:
        self.set_value(bytes(data))


class UByteTag(_NumericTag):
    type = ECTagType.EC_TAGTYPE_UINT8

    def encode_value(self) -> bytes:
        return bytes([self.get_value() & 0xFF])

    def parse_value(self, data: bytes) -> None:
        if len(data) == 0:
            self.set_value(0)
        elif len(data) == 1:
            self.set_value(data[0])
        else:
            raise ValueError("UInt8Tag value must be 1 byte long")

    def get_short(self) -> int:
        return self.get_value()

    def get_int(self) -> int:
        return self.get_value()

    def get_long(self) -> int:
        return self.get_value()


class UShortTag(_NumericTag):
    type = ECTagType.EC_TAGTYPE_UINT16

    def encode_value(self) -> bytes:
        return enc.ushort_to_bytes(self.get_value())

    def parse_value(self, data: bytes) -> None:
        if len(data) == 0:
            self.set_value(0)
        elif len(data) == 2:
            self.set_value(enc.read_uint16(data, False, 0))
        else:
            raise ValueError("UInt16Tag value must be 2 bytes long")

    def get_short(self) -> int:
        return self.get_value()

    def get_int(self) -> int:
        return self.get_value()

    def get_long(self) -> int:
        return self.get_value()


class UIntTag(_NumericTag):
    type = ECTagType.EC_TAGTYPE_UINT32

    def encode_value(self) -> bytes:
        return enc.uint_to_bytes(self.get_value())

    def parse_value(self, data: bytes) -> None:
        if len(data) == 0:
            self.set_value(0)
        elif len(data) == 4:
            self.set_value(enc.read_uint32(data, False, 0))
        else:
            raise ValueError("UInt32Tag value must be 4 bytes long")

    def get_short(self) -> int:
        # Parity with Kotlin: a uint32 cannot be downcast to short.
        raise RuntimeError("Unsigned Integer cannot be cast to short")

    def get_int(self) -> int:
        return self.get_value()

    def get_long(self) -> int:
        return self.get_value()


class ULongTag(_NumericTag):
    type = ECTagType.EC_TAGTYPE_UINT64

    def encode_value(self) -> bytes:
        return enc.ulong_to_bytes(self.get_value())

    def parse_value(self, data: bytes) -> None:
        if len(data) == 0:
            self.set_value(0)
        elif len(data) == 8:
            self.set_value(enc.bytes_to_uint64(data))
        else:
            raise ValueError("UInt64Tag value must be 8 bytes long")

    def get_short(self) -> int:
        raise RuntimeError("Unsigned Long cannot be cast to short")

    def get_int(self) -> int:
        raise RuntimeError("Unsigned Long cannot be cast to int")

    def get_long(self) -> int:
        return self.get_value()


class UInt128Tag(Tag):
    """128-bit integer (``EC_TAGTYPE_UINT128``).

    Not used in amarr (hashes arrive as :class:`Hash16Tag`), but ported
    for completeness. It replicates ``java.math.BigInteger``'s behavior:
    two's-complement, big-endian, minimal representation.
    """

    type = ECTagType.EC_TAGTYPE_UINT128

    def encode_value(self) -> bytes:
        value: int = self.get_value()
        if value == 0:
            return b"\x00"
        length = (value.bit_length() + 8) // 8  # +1 sign bit
        return value.to_bytes(length, byteorder="big", signed=True)

    def parse_value(self, data: bytes) -> None:
        if len(data) == 0:
            self.set_value(0)
        else:
            self.set_value(int.from_bytes(bytes(data), byteorder="big", signed=True))


class StringTag(Tag):
    type = ECTagType.EC_TAGTYPE_STRING

    def encode_value(self) -> bytes:
        return self.get_value().encode("utf-8") + b"\x00"

    def parse_value(self, data: bytes) -> None:
        if len(data) == 0 or data[-1] != 0x00:
            raise ValueError("StringTag value must be null terminated")
        self.set_value(bytes(data).decode("utf-8").rstrip("\x00"))


class DoubleTag(Tag):
    type = ECTagType.EC_TAGTYPE_DOUBLE

    def encode_value(self) -> bytes:
        # aMule serializes the double as its textual representation.
        return repr(float(self.get_value())).encode("utf-8") + b"\x00"

    def parse_value(self, data: bytes) -> None:
        if len(data) == 0 or data[-1] != 0x00:
            raise ValueError("DoubleTag value must be null terminated")
        self.set_value(float(bytes(data).decode("utf-8").rstrip("\x00")))


class Ipv4:
    """Address/port pair of an IPv4 tag."""

    def __init__(self, address: str, port: int) -> None:
        self.address = address
        self.port = port

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Ipv4)
            and self.address == other.address
            and self.port == other.port
        )

    def __repr__(self) -> str:
        return f"Ipv4({self.address}:{self.port})"


class Ipv4Tag(Tag):
    type = ECTagType.EC_TAGTYPE_IPV4

    def encode_value(self) -> bytes:
        ip: Ipv4 = self.get_value()
        octets = bytes(int(part) & 0xFF for part in ip.address.split("."))
        return octets + enc.ushort_to_bytes(ip.port)

    def parse_value(self, data: bytes) -> None:
        # The first 4 bytes are the IP, the last 2 the port.
        if len(data) != 6:
            raise ValueError("Ipv4Tag value must be 6 bytes long")
        address = f"{data[0]}.{data[1]}.{data[2]}.{data[3]}"
        self.set_value(Ipv4(address, enc.read_uint16(data, False, 4)))


class Hash16Tag(Tag):
    type = ECTagType.EC_TAGTYPE_HASH16

    def encode_value(self) -> bytes:
        return bytes(self.get_value())

    def parse_value(self, data: bytes) -> None:
        if len(data) == 16:
            self.set_value(bytes(data))
        else:
            raise ValueError("Hash16Tag value must be 16 bytes long")

    def _eq_value(self, other: "Tag") -> bool:
        return bytes(self.get_value()) == bytes(other.get_value())


# Type -> constructor map for the parser.
_TAG_BY_TYPE = {
    ECTagType.EC_TAGTYPE_CUSTOM: CustomTag,
    ECTagType.EC_TAGTYPE_UINT8: UByteTag,
    ECTagType.EC_TAGTYPE_UINT16: UShortTag,
    ECTagType.EC_TAGTYPE_UINT32: UIntTag,
    ECTagType.EC_TAGTYPE_UINT64: ULongTag,
    ECTagType.EC_TAGTYPE_UINT128: UInt128Tag,
    ECTagType.EC_TAGTYPE_DOUBLE: DoubleTag,
    ECTagType.EC_TAGTYPE_IPV4: Ipv4Tag,
    ECTagType.EC_TAGTYPE_HASH16: Hash16Tag,
    ECTagType.EC_TAGTYPE_STRING: StringTag,
}


# --- Typed accessors (Packet.Companion in Kotlin) -----------------------------

def _first_of_type(tags: list[Tag], name: ECTagName, cls) -> Optional[Tag]:
    for tag in tags:
        if tag.name == name:
            return tag if isinstance(tag, cls) else None
    return None


def find_byte(tags: list[Tag], name: ECTagName) -> Optional[UByteTag]:
    return _first_of_type(tags, name, UByteTag)  # type: ignore[return-value]


def find_short(tags: list[Tag], name: ECTagName) -> Optional[UShortTag]:
    return _first_of_type(tags, name, UShortTag)  # type: ignore[return-value]


def find_int(tags: list[Tag], name: ECTagName) -> Optional[UIntTag]:
    return _first_of_type(tags, name, UIntTag)  # type: ignore[return-value]


def find_long(tags: list[Tag], name: ECTagName) -> Optional[ULongTag]:
    return _first_of_type(tags, name, ULongTag)  # type: ignore[return-value]


def find_string(tags: list[Tag], name: ECTagName) -> Optional[StringTag]:
    return _first_of_type(tags, name, StringTag)  # type: ignore[return-value]


def find_hash16(tags: list[Tag], name: ECTagName) -> Optional[Hash16Tag]:
    return _first_of_type(tags, name, Hash16Tag)  # type: ignore[return-value]


def find_ipv4(tags: list[Tag], name: ECTagName) -> Optional[Ipv4Tag]:
    return _first_of_type(tags, name, Ipv4Tag)  # type: ignore[return-value]


def find_custom(tags: list[Tag], name: ECTagName) -> Optional[CustomTag]:
    return _first_of_type(tags, name, CustomTag)  # type: ignore[return-value]


def find_numeric(tags: list[Tag], name: ECTagName) -> Optional[_NumericTag]:
    return _first_of_type(tags, name, _NumericTag)  # type: ignore[return-value]


def as_ipv4(tag: Optional[Tag]) -> Optional[Ipv4Tag]:
    return tag if isinstance(tag, Ipv4Tag) else None


def as_numeric(tag: Optional[Tag]) -> Optional[_NumericTag]:
    return tag if isinstance(tag, _NumericTag) else None


def as_byte(tag: Optional[Tag]) -> Optional[UByteTag]:
    return tag if isinstance(tag, UByteTag) else None


# --- Encoder ------------------------------------------------------------------

class TagEncoder:
    """Serializes tags to bytes (``TagEncoder.kt``)."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or _logger

    def encode(self, tag: Tag, utf8: bool) -> bytes:
        tag_name_and_subtags = (tag.name.value << 1) | (0 if not tag.subtags else 1)
        header_name = enc.ushort_to_bytes_utf(tag_name_and_subtags & 0xFFFF, utf8)
        header_length = enc.uint_to_bytes_utf(self._compute_tag_length(tag), utf8)
        if tag.subtags:
            subtag_count = enc.ushort_to_bytes_utf(len(tag.subtags) & 0xFFFF, utf8)
        else:
            subtag_count = b""
        subtag_payload = b"".join(self.encode(sub, utf8) for sub in tag.subtags)
        return (
            header_name
            + bytes([tag.type.value])
            + header_length
            + subtag_count
            + subtag_payload
            + tag.encode_value()
        )

    def _compute_tag_length(self, tag: Tag) -> int:
        """Theoretical length of the tag (own value + subtags with fixed headers)."""
        total = len(tag.encode_value())
        for sub in tag.subtags:
            total += self._compute_tag_length(sub)
            total += TAG_NAME_SIZE + TAG_TYPE_SIZE + TAG_LENGTH_SIZE
            if sub.subtags:
                total += SUBTAG_COUNT_SIZE
        return total


# --- Parser -------------------------------------------------------------------

class TagParser:
    """Parses tags from a payload (``TagParser.kt``)."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or _logger

    def parse(self, payload: bytes, index: int, utf: bool) -> tuple[Tag, int]:
        """Returns ``(tag, end_index)`` where ``end_index`` is the last byte of the tag."""
        tag, _theoretical, end_index = self._parse_with_metadata(payload, index, utf)
        return tag, end_index

    def _parse_with_metadata(
        self, payload: bytes, tag_name_index: int, utf: bool
    ) -> tuple[Tag, int, int]:
        # Name + subtags flag (last bit of the name).
        tag_name_and_has_subtags = enc.read_uint16(payload, utf, tag_name_index)
        tag_name_raw = (tag_name_and_has_subtags >> 1) & 0xFFFF
        tag_name = ECTagName.from_value(tag_name_raw)
        has_subtags = (tag_name_and_has_subtags & 0x01) == 0x01

        # Type.
        tag_type_index = tag_name_index + enc.number_length(
            payload[tag_name_index], utf, TAG_NAME_SIZE
        )
        tag_type = ECTagType.from_value(payload[tag_type_index])

        # Length (own content + children with headers).
        tag_length_index = tag_type_index + TAG_TYPE_SIZE
        tag_length = enc.read_uint32(payload, utf, tag_length_index)

        # First byte of the value (may shift if there are subtags).
        value_start_index = tag_length_index + enc.number_length(
            payload[tag_length_index], utf, TAG_LENGTH_SIZE
        )

        subtags: list[Tag] = []
        theoretical_length = 0

        if not has_subtags:
            value_end_index = value_start_index + tag_length - 1
        else:
            subtag_count = enc.read_uint16(payload, utf, value_start_index)
            value_start_index += enc.number_length(
                payload[value_start_index], utf, SUBTAG_COUNT_SIZE
            )
            for _ in range(subtag_count):
                subtag, sub_theoretical, sub_end = self._parse_with_metadata(
                    payload, value_start_index, utf
                )
                subtags.append(subtag)
                value_start_index = sub_end + 1
                theoretical_length += sub_theoretical
            if len(subtags) > subtag_count:
                raise ValueError(
                    "Error parsing subtags list - "
                    f"Expected subtags {subtag_count} found subtags {len(subtags)}"
                )
            value_end_index = value_start_index + ((tag_length - theoretical_length) - 1)
            theoretical_length += SUBTAG_COUNT_SIZE

        tag_value = bytes(payload[value_start_index:value_end_index + 1])
        theoretical_length += len(tag_value)
        theoretical_length += TAG_NAME_SIZE + TAG_TYPE_SIZE + TAG_LENGTH_SIZE

        cls = _TAG_BY_TYPE.get(tag_type)
        if cls is None:
            raise ValueError(f"Unknown tag type: {tag_type}")
        tag = cls(tag_name, subtags=subtags, name_value=tag_name_raw)
        tag.parse_value(tag_value)
        return tag, theoretical_length, value_end_index
