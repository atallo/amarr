"""Encoding and decoding of EC protocol integers.

Port of ``jamule/ec/Encoding.kt`` and ``jamule/ec/TypeSizes.kt``.

The EC protocol has a quirk: when the ``EC_FLAG_UTF8_NUMBERS`` flag
is active (the usual case), the **header numbers** (tag count, tag
name, tag length and subtag count) are not serialized as fixed-size
big-endian integers, but as the UTF-8 sequence of the codepoint whose value
is that number. This is more compact for small values. The **values** of
numeric tags, on the other hand, always go as fixed-size big-endian binary.
"""

from __future__ import annotations

import struct

# Sizes in bytes of the protocol types (TypeSizes.kt)
LEN_UBYTE = 1
LEN_USHORT = 2
LEN_UINT = 4
LEN_ULONG = 8
LEN_UINT128 = 16


# --- Fixed-size big-endian binary encoding ------------------------------------

def ushort_to_bytes(value: int) -> bytes:
    """2 bytes big-endian (equivalent to ``UShort.toUByteArray()``)."""
    return struct.pack(">H", value & 0xFFFF)


def uint_to_bytes(value: int) -> bytes:
    """4 bytes big-endian (equivalent to ``UInt.toUByteArray()``)."""
    return struct.pack(">I", value & 0xFFFFFFFF)


def ulong_to_bytes(value: int) -> bytes:
    """8 bytes big-endian (equivalent to ``ULong.toUByteArray()``)."""
    return struct.pack(">Q", value & 0xFFFFFFFFFFFFFFFF)


def bytes_to_uint64(data: bytes) -> int:
    """Reads 8 big-endian bytes as an unsigned integer (``toUInt64``)."""
    return struct.unpack(">Q", bytes(data[:8]))[0]


def _bytes_to_uint32(data: bytes) -> int:
    return struct.unpack(">I", bytes(data[:4]))[0]


def _bytes_to_uint16(data: bytes) -> int:
    return struct.unpack(">H", bytes(data[:2]))[0]


# --- UTF-8 numbers -------------------------------------------------------------

def number_to_utf8(value: int) -> bytes:
    """Encodes ``value`` as the UTF-8 sequence of its codepoint.

    Equivalent to ``ULong.toUtf8ByteArray()`` / ``String(intArrayOf(n)).toByteArray()``.
    """
    return chr(value).encode("utf-8")


def utf8_sequence_length(first_byte: int) -> int:
    """Length (1-4) of the UTF-8 sequence that starts with ``first_byte``.

    Port of ``UByte.utf8SequenceLength``.
    """
    if first_byte & 0x80 == 0:
        # ASCII character, 1 byte
        return 1
    length = 1
    mask = 0x40  # second most significant bit
    while first_byte & mask != 0:
        length += 1
        mask >>= 1
    if length < 2 or length > 4:
        raise ValueError(f"Invalid UTF-8 first byte: {first_byte}")
    return length


def read_utf8_number(data: bytes, offset: int) -> int:
    """Decodes the UTF-8 number that starts at ``offset`` and returns its codepoint.

    Port of ``UByteArray.readUtf8Number``. Instead of decoding the whole rest
    of the buffer (as the Kotlin version does), only the necessary sequence is
    decoded, which is equivalent for a single codepoint and avoids failing on
    later non-UTF8 bytes.
    """
    length = utf8_sequence_length(data[offset])
    return ord(bytes(data[offset:offset + length]).decode("utf-8"))


def number_length(first_byte: int, utf: bool, size: int) -> int:
    """Length in bytes of a header number (``UByte.numberLength``)."""
    return utf8_sequence_length(first_byte) if utf else size


# --- Reading header numbers (binary or UTF-8) ---------------------------------

def read_uint32(data: bytes, utf: bool, index: int) -> int:
    """Reads a header uint32 (``readUInt32``)."""
    if not utf:
        return _bytes_to_uint32(data[index:index + LEN_UINT])
    return read_utf8_number(data, index)


def read_uint16(data: bytes, utf: bool, index: int) -> int:
    """Reads a header uint16 (``readUint16``)."""
    if not utf:
        return _bytes_to_uint16(data[index:index + LEN_USHORT])
    return read_utf8_number(data, index)


def ushort_to_bytes_utf(value: int, utf: bool) -> bytes:
    """Encodes a header uint16, in binary or UTF-8 (``UShort.toUByteArray(utf)``)."""
    return number_to_utf8(value) if utf else ushort_to_bytes(value)


def uint_to_bytes_utf(value: int, utf: bool) -> bytes:
    """Encodes a header uint32, in binary or UTF-8 (``UInt.toUByteArray(utf)``)."""
    return number_to_utf8(value) if utf else uint_to_bytes(value)
