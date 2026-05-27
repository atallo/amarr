"""Codificación y decodificación de enteros del protocolo EC.

Port de ``jamule/ec/Encoding.kt`` y ``jamule/ec/TypeSizes.kt``.

El protocolo EC tiene una peculiaridad: cuando el flag ``EC_FLAG_UTF8_NUMBERS``
está activo (lo habitual), los **números de cabecera** (contador de tags, nombre
de tag, longitud de tag y contador de subtags) no se serializan como enteros
big-endian de tamaño fijo, sino como la secuencia UTF-8 del codepoint cuyo valor
es ese número. Esto es más compacto para valores pequeños. Los **valores** de
los tags numéricos, en cambio, siempre van en binario big-endian de tamaño fijo.
"""

from __future__ import annotations

import struct

# Tamaños en bytes de los tipos del protocolo (TypeSizes.kt)
LEN_UBYTE = 1
LEN_USHORT = 2
LEN_UINT = 4
LEN_ULONG = 8
LEN_UINT128 = 16


# --- Codificación binaria big-endian de tamaño fijo ---------------------------

def ushort_to_bytes(value: int) -> bytes:
    """2 bytes big-endian (equivale a ``UShort.toUByteArray()``)."""
    return struct.pack(">H", value & 0xFFFF)


def uint_to_bytes(value: int) -> bytes:
    """4 bytes big-endian (equivale a ``UInt.toUByteArray()``)."""
    return struct.pack(">I", value & 0xFFFFFFFF)


def ulong_to_bytes(value: int) -> bytes:
    """8 bytes big-endian (equivale a ``ULong.toUByteArray()``)."""
    return struct.pack(">Q", value & 0xFFFFFFFFFFFFFFFF)


def bytes_to_uint64(data: bytes) -> int:
    """Lee 8 bytes big-endian como entero sin signo (``toUInt64``)."""
    return struct.unpack(">Q", bytes(data[:8]))[0]


def _bytes_to_uint32(data: bytes) -> int:
    return struct.unpack(">I", bytes(data[:4]))[0]


def _bytes_to_uint16(data: bytes) -> int:
    return struct.unpack(">H", bytes(data[:2]))[0]


# --- Números UTF-8 ------------------------------------------------------------

def number_to_utf8(value: int) -> bytes:
    """Codifica ``value`` como la secuencia UTF-8 de su codepoint.

    Equivale a ``ULong.toUtf8ByteArray()`` / ``String(intArrayOf(n)).toByteArray()``.
    """
    return chr(value).encode("utf-8")


def utf8_sequence_length(first_byte: int) -> int:
    """Longitud (1-4) de la secuencia UTF-8 que empieza por ``first_byte``.

    Port de ``UByte.utf8SequenceLength``.
    """
    if first_byte & 0x80 == 0:
        # Carácter ASCII, 1 byte
        return 1
    length = 1
    mask = 0x40  # segundo bit más significativo
    while first_byte & mask != 0:
        length += 1
        mask >>= 1
    if length < 2 or length > 4:
        raise ValueError(f"Invalid UTF-8 first byte: {first_byte}")
    return length


def read_utf8_number(data: bytes, offset: int) -> int:
    """Decodifica el número UTF-8 que empieza en ``offset`` y devuelve su codepoint.

    Port de ``UByteArray.readUtf8Number``. En lugar de decodificar todo el resto
    del buffer (como hace la versión Kotlin) se decodifica únicamente la secuencia
    necesaria, lo que es equivalente para un único codepoint y evita fallar por
    bytes no-UTF8 posteriores.
    """
    length = utf8_sequence_length(data[offset])
    return ord(bytes(data[offset:offset + length]).decode("utf-8"))


def number_length(first_byte: int, utf: bool, size: int) -> int:
    """Longitud en bytes de un número de cabecera (``UByte.numberLength``)."""
    return utf8_sequence_length(first_byte) if utf else size


# --- Lectura de números de cabecera (binario o UTF-8) -------------------------

def read_uint32(data: bytes, utf: bool, index: int) -> int:
    """Lee un uint32 de cabecera (``readUInt32``)."""
    if not utf:
        return _bytes_to_uint32(data[index:index + LEN_UINT])
    return read_utf8_number(data, index)


def read_uint16(data: bytes, utf: bool, index: int) -> int:
    """Lee un uint16 de cabecera (``readUint16``)."""
    if not utf:
        return _bytes_to_uint16(data[index:index + LEN_USHORT])
    return read_utf8_number(data, index)


def ushort_to_bytes_utf(value: int, utf: bool) -> bytes:
    """Codifica un uint16 de cabecera, en binario o UTF-8 (``UShort.toUByteArray(utf)``)."""
    return number_to_utf8(value) if utf else ushort_to_bytes(value)


def uint_to_bytes_utf(value: int, utf: bool) -> bytes:
    """Codifica un uint32 de cabecera, en binario o UTF-8 (``UInt.toUByteArray(utf)``)."""
    return number_to_utf8(value) if utf else uint_to_bytes(value)
