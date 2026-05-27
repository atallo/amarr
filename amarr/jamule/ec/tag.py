"""Sistema de tags del protocolo EC: tipos, codificación y parseo.

Reúne en un único módulo el port de:

* ``jamule/ec/tag/Tag.kt``        -> clases :class:`Tag` y subclases.
* ``jamule/ec/tag/TagEncoder.kt`` -> :class:`TagEncoder`.
* ``jamule/ec/tag/TagParser.kt``  -> :class:`TagParser`.
* Los accesores tipados que en Kotlin vivían en ``Packet.Companion``
  (``Iterable<Tag<*>>.byte(name)`` etc.).

Un tag EC se serializa como::

    [nombre+flag_subtags : uint16] [tipo : uint8] [longitud : uint32]
    [ (si tiene subtags) nº_subtags : uint16  subtags... ] [valor]

donde los números de cabecera van en binario o en UTF-8 según el flag UTF8 del
paquete (ver :mod:`amarr.jamule.ec.encoding`). La ``longitud`` se calcula
**siempre con tamaños de cabecera fijos** (no UTF-8): es la "longitud teórica"
que comparten codificador y parser. Esta convención, aunque peculiar, es la que
usa aMule y se respeta tal cual.
"""

from __future__ import annotations

import logging
from typing import Optional

from .codes import ECTagName, ECTagType
from . import encoding as enc

_logger = logging.getLogger(__name__)

# Centinela para distinguir "valor no asignado" de un valor legítimo (p.ej. 0).
_UNSET = object()

# Tamaños fijos de cabecera usados para la "longitud teórica" (TagParser.kt)
TAG_NAME_SIZE = enc.LEN_USHORT
TAG_TYPE_SIZE = enc.LEN_UBYTE
TAG_LENGTH_SIZE = enc.LEN_UINT
SUBTAG_COUNT_SIZE = enc.LEN_USHORT


class Tag:
    """Clase base de todos los tags. No instanciar directamente."""

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
        # ``name_value`` conserva el valor crudo del nombre (relevante cuando el
        # nombre no se reconoce y ``name`` queda como EC_TAG_UNKNOWN).
        self.name_value = name_value if name_value is not None else name.value
        self._value = value

    # --- gestión de valor ---------------------------------------------------
    def get_value(self):
        return self._value

    def set_value(self, value) -> None:
        if self._value is not _UNSET:
            raise RuntimeError("Tag value already set")
        self._value = value

    # --- serialización (a implementar por subclases) ------------------------
    def parse_value(self, data: bytes) -> None:  # pragma: no cover - abstracto
        raise NotImplementedError

    def encode_value(self) -> bytes:  # pragma: no cover - abstracto
        raise NotImplementedError

    # --- interfaz numérica (solo válida en subclases numéricas) -------------
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
        # Paridad con las ``data class`` de Kotlin: ``equals`` se genera sobre
        # ``name``, ``subtags`` y ``nameValue``, pero **no** sobre el valor (que
        # es un campo privado fuera del constructor primario). Por eso dos tags
        # del mismo nombre y subtags se consideran iguales aunque su valor
        # difiera. El valor se compara explícitamente con ``get_value()``.
        if type(self) is not type(other):
            return False
        assert isinstance(other, Tag)
        return (
            self.name == other.name
            and self.name_value == other.name_value
            and self.subtags == other.subtags
        )


class _NumericTag(Tag):
    """Mixin marcador para los tags enteros (``NumericTag`` en Kotlin)."""


class CustomTag(Tag):
    """Tag de bytes opacos (``EC_TAGTYPE_CUSTOM``)."""

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
        # Paridad con Kotlin: un uint32 no puede degradarse a short.
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
    """Entero de 128 bits (``EC_TAGTYPE_UINT128``).

    No se usa en amarr (los hashes llegan como :class:`Hash16Tag`), pero se porta
    por completitud. Se replica el comportamiento de ``java.math.BigInteger``:
    representación en complemento a dos, big-endian, mínima.
    """

    type = ECTagType.EC_TAGTYPE_UINT128

    def encode_value(self) -> bytes:
        value: int = self.get_value()
        if value == 0:
            return b"\x00"
        length = (value.bit_length() + 8) // 8  # +1 bit de signo
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
        # aMule serializa el double como su representación textual.
        return repr(float(self.get_value())).encode("utf-8") + b"\x00"

    def parse_value(self, data: bytes) -> None:
        if len(data) == 0 or data[-1] != 0x00:
            raise ValueError("DoubleTag value must be null terminated")
        self.set_value(float(bytes(data).decode("utf-8").rstrip("\x00")))


class Ipv4:
    """Par dirección/puerto de un tag IPv4."""

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
        # Los 4 primeros bytes son la IP, los 2 últimos el puerto.
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


# Mapa tipo -> constructor para el parser.
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


# --- Accesores tipados (Packet.Companion en Kotlin) ---------------------------

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


# --- Codificador --------------------------------------------------------------

class TagEncoder:
    """Serializa tags a bytes (``TagEncoder.kt``)."""

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
        """Longitud teórica del tag (valor propio + subtags con cabeceras fijas)."""
        total = len(tag.encode_value())
        for sub in tag.subtags:
            total += self._compute_tag_length(sub)
            total += TAG_NAME_SIZE + TAG_TYPE_SIZE + TAG_LENGTH_SIZE
            if sub.subtags:
                total += SUBTAG_COUNT_SIZE
        return total


# --- Parser -------------------------------------------------------------------

class TagParser:
    """Parsea tags desde un payload (``TagParser.kt``)."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or _logger

    def parse(self, payload: bytes, index: int, utf: bool) -> tuple[Tag, int]:
        """Devuelve ``(tag, end_index)`` donde ``end_index`` es el último byte del tag."""
        tag, _theoretical, end_index = self._parse_with_metadata(payload, index, utf)
        return tag, end_index

    def _parse_with_metadata(
        self, payload: bytes, tag_name_index: int, utf: bool
    ) -> tuple[Tag, int, int]:
        # Nombre + flag de subtags (último bit del nombre).
        tag_name_and_has_subtags = enc.read_uint16(payload, utf, tag_name_index)
        tag_name_raw = (tag_name_and_has_subtags >> 1) & 0xFFFF
        tag_name = ECTagName.from_value(tag_name_raw)
        has_subtags = (tag_name_and_has_subtags & 0x01) == 0x01

        # Tipo.
        tag_type_index = tag_name_index + enc.number_length(
            payload[tag_name_index], utf, TAG_NAME_SIZE
        )
        tag_type = ECTagType.from_value(payload[tag_type_index])

        # Longitud (contenido propio + hijos con cabeceras).
        tag_length_index = tag_type_index + TAG_TYPE_SIZE
        tag_length = enc.read_uint32(payload, utf, tag_length_index)

        # Primer byte del valor (puede desplazarse si hay subtags).
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
