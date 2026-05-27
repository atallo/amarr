"""Capa de paquetes del protocolo EC.

Reúne el port de:

* ``jamule/ec/packet/Flags.kt``        -> :class:`Flags`.
* ``jamule/ec/packet/Packet.kt``       -> :class:`Packet` (+ accesores tipados).
* ``jamule/ec/packet/PacketWriter.kt`` -> :class:`PacketWriter`.
* ``jamule/ec/packet/PacketParser.kt`` -> :class:`PacketParser`.

Estructura de un paquete en el cable::

    [flags : uint32] [ (si accepts) accept_flags : uint32 ] [longitud : uint32] [payload]

El ``payload`` es ``[opcode : uint8] [nº_tags : uint16] [tags...]`` y puede ir
comprimido con zlib si el flag correspondiente está activo.
"""

from __future__ import annotations

import io
import logging
import zlib
from typing import BinaryIO, Optional

from .codes import ECFlag, ECOpCode, ECTagName
from . import encoding as enc
from . import tag as tagmod
from .tag import Tag, TagEncoder, TagParser
from ..exceptions import InvalidECException

_logger = logging.getLogger(__name__)

# Índices/constantes del payload (PacketParser.kt)
_INDEX_TAG_COUNT = 1
_TAG_COUNT_SIZE = enc.LEN_USHORT
_MAX_DECOMPRESSED_SIZE = 50 * 1024 * 1024


class Flags:
    """Flags de transmisión de un paquete (``Flags.kt``)."""

    def __init__(
        self,
        zlib_compressed: bool = False,
        utf8: bool = True,
        has_id: bool = False,
        accepts: bool = False,
    ) -> None:
        self.zlib_compressed = zlib_compressed
        self.utf8 = utf8
        self.has_id = has_id
        self.accepts = accepts

    def to_uint(self) -> int:
        # El bit 5 (0x20) siempre se activa para distinguir de clientes pre-rc8.
        flags = 0x20
        if self.zlib_compressed:
            flags |= ECFlag.EC_FLAG_ZLIB.value
        if self.utf8:
            flags |= ECFlag.EC_FLAG_UTF8_NUMBERS.value
        if self.has_id:
            flags |= ECFlag.EC_FLAG_HAS_ID.value
        if self.accepts:
            flags |= ECFlag.EC_FLAG_ACCEPTS.value
        return flags

    @classmethod
    def from_uint(cls, flags: int) -> "Flags":
        return cls(
            zlib_compressed=flags & ECFlag.EC_FLAG_ZLIB.value != 0,
            utf8=flags & ECFlag.EC_FLAG_UTF8_NUMBERS.value != 0,
            has_id=flags & ECFlag.EC_FLAG_HAS_ID.value != 0,
            accepts=flags & ECFlag.EC_FLAG_ACCEPTS.value != 0,
        )

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Flags)
            and self.zlib_compressed == other.zlib_compressed
            and self.utf8 == other.utf8
            and self.has_id == other.has_id
            and self.accepts == other.accepts
        )

    def __repr__(self) -> str:
        return (
            f"Flags(zlib={self.zlib_compressed}, utf8={self.utf8}, "
            f"has_id={self.has_id}, accepts={self.accepts})"
        )


class Packet:
    """Un paquete EC: opcode + lista de tags + flags (``Packet.kt``)."""

    def __init__(
        self,
        op_code: ECOpCode = ECOpCode.EC_OP_NOOP,
        tags: Optional[list[Tag]] = None,
        flags: Optional[Flags] = None,
        accepts: Optional[Flags] = None,
        id: Optional[int] = None,
    ) -> None:
        self.op_code = op_code
        self.tags: list[Tag] = tags if tags is not None else []
        self.flags = flags if flags is not None else Flags()
        self.accepts = accepts
        self.id = id

    # Accesores tipados por nombre de tag (Packet.Companion).
    def byte(self, name: ECTagName):
        return tagmod.find_byte(self.tags, name)

    def short(self, name: ECTagName):
        return tagmod.find_short(self.tags, name)

    def int(self, name: ECTagName):
        return tagmod.find_int(self.tags, name)

    def long(self, name: ECTagName):
        return tagmod.find_long(self.tags, name)

    def string(self, name: ECTagName):
        return tagmod.find_string(self.tags, name)

    def hash16(self, name: ECTagName):
        return tagmod.find_hash16(self.tags, name)

    def ipv4(self, name: ECTagName):
        return tagmod.find_ipv4(self.tags, name)

    def custom(self, name: ECTagName):
        return tagmod.find_custom(self.tags, name)

    def numeric(self, name: ECTagName):
        return tagmod.find_numeric(self.tags, name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Packet):
            return False
        # ``accepts``/``id`` no se comparan, igual que en los tests de jamule,
        # que construyen los Packet esperados sin esos campos.
        return (
            self.op_code == other.op_code
            and self.tags == other.tags
            and self.flags == other.flags
        )

    def __repr__(self) -> str:
        return f"Packet({self.op_code.name}, tags={self.tags}, flags={self.flags})"


class PacketWriter:
    """Serializa un :class:`Packet` a un stream de salida (``PacketWriter.kt``)."""

    def __init__(self, tag_encoder: TagEncoder, logger: Optional[logging.Logger] = None) -> None:
        self._tag_encoder = tag_encoder
        self._logger = logger or _logger

    def write(self, packet: Packet, output: BinaryIO) -> None:
        if packet.flags.has_id and packet.id is None:
            raise InvalidECException("ID must be provided when packet has ID flag")
        self._write_transport(packet, output)

    def _write_transport(self, packet: Packet, output: BinaryIO) -> None:
        # Flags.
        output.write(enc.uint_to_bytes(packet.flags.to_uint()))

        # Accept flags, si procede.
        if packet.flags.accepts:
            if packet.accepts is None:
                raise InvalidECException(
                    "Accepts flags must be provided when packet has accepts flag"
                )
            output.write(enc.uint_to_bytes(packet.accepts.to_uint()))

        raw_payload = self._encode_payload(packet)
        payload = (
            self._compress_payload(raw_payload)
            if packet.flags.zlib_compressed
            else raw_payload
        )

        # Longitud + payload.
        output.write(enc.uint_to_bytes(len(payload)))
        output.write(payload)

    def _encode_payload(self, packet: Packet) -> bytes:
        op_code = bytes([packet.op_code.value])
        tag_count = enc.ushort_to_bytes_utf(len(packet.tags) & 0xFFFF, packet.flags.utf8)
        tags = b"".join(
            self._tag_encoder.encode(t, packet.flags.utf8) for t in packet.tags
        )
        return op_code + tag_count + tags

    @staticmethod
    def _compress_payload(data: bytes) -> bytes:
        return zlib.compress(data)


class PacketParser:
    """Parsea un :class:`Packet` desde un stream de entrada (``PacketParser.kt``)."""

    def __init__(self, tag_parser: TagParser, logger: Optional[logging.Logger] = None) -> None:
        self._tag_parser = tag_parser
        self._logger = logger or _logger

    def parse(self, stream: BinaryIO) -> Packet:
        flags, accepts_flags, _length, payload = self._parse_transport(stream)
        return self._parse_application(flags, accepts_flags, payload)

    def _parse_transport(self, stream: BinaryIO):
        flags = self._parse_flags(stream)
        accepts_flags = self._parse_flags(stream) if flags.accepts else None

        length = self._read_uint(stream)
        if length == 0:
            raise InvalidECException("Payload cannot be empty")

        if flags.zlib_compressed:
            payload = self._decompress_payload(stream, length)
        else:
            payload = self._read_n(stream, length)
        return flags, accepts_flags, length, payload

    def _parse_flags(self, stream: BinaryIO) -> Flags:
        flags = self._read_uint(stream)
        if flags & ECFlag.EC_FLAG_UNKNOWN_MASK.value != 0:
            raise InvalidECException("Unknown trasmission flags")
        return Flags.from_uint(flags)

    def _parse_application(
        self, flags: Flags, accepts_flags: Optional[Flags], payload: bytes
    ) -> Packet:
        tags_index = _INDEX_TAG_COUNT + enc.number_length(
            payload[_INDEX_TAG_COUNT], flags.utf8, _TAG_COUNT_SIZE
        )
        tags_count = enc.read_uint16(payload, flags.utf8, _INDEX_TAG_COUNT)
        op_code = ECOpCode.from_value(payload[0])

        tag_list: list[Tag] = []
        index = tags_index
        tag_counter = 0
        while index < len(payload) and tag_counter < tags_count:
            tag, end_index = self._tag_parser.parse(payload, index, flags.utf8)
            tag_list.append(tag)
            index = end_index + 1
            tag_counter += 1

        if index != len(payload):
            raise InvalidECException(
                f"Invalid tags size in packet, expected {len(payload)} found {index}"
            )
        if tag_counter != tags_count:
            raise InvalidECException(
                f"Error parsing tags list - Expected tags {tags_count} found tags {tag_counter}"
            )
        return Packet(op_code, tag_list, flags, accepts_flags)

    def _decompress_payload(self, stream: BinaryIO, length: int) -> bytes:
        compressed = self._read_n(stream, length)
        decompressor = zlib.decompressobj()
        try:
            out = io.BytesIO()
            chunk = decompressor.decompress(compressed, _MAX_DECOMPRESSED_SIZE + 1)
            out.write(chunk)
            # Si queda salida pendiente, supera el límite permitido.
            if decompressor.unconsumed_tail:
                raise InvalidECException(
                    f"Packet decompressed size exceeds limit {_MAX_DECOMPRESSED_SIZE}"
                )
            out.write(decompressor.flush())
            # Un flujo zlib truncado/incompleto no marca eof; decompressobj
            # lo tolera silenciosamente devolviendo bytes vacíos en vez de
            # lanzar. Lo tratamos como payload malformado.
            if not decompressor.eof:
                raise InvalidECException("Compressed payload is malformed")
            data = out.getvalue()
            if len(data) > _MAX_DECOMPRESSED_SIZE:
                raise InvalidECException(
                    f"Packet decompressed size {len(data)} exceeds limit {_MAX_DECOMPRESSED_SIZE}"
                )
            return data
        except zlib.error as exc:
            raise InvalidECException("Compressed payload is malformed") from exc

    @staticmethod
    def _read_uint(stream: BinaryIO) -> int:
        return enc.read_uint32(PacketParser._read_n(stream, 4), False, 0)

    @staticmethod
    def _read_n(stream: BinaryIO, n: int) -> bytes:
        """Lee exactamente ``n`` bytes o lanza si el stream se agota antes."""
        data = bytearray()
        while len(data) < n:
            chunk = stream.read(n - len(data))
            if not chunk:
                raise InvalidECException(
                    f"Stream ended before reading {n} bytes (got {len(data)})"
                )
            data.extend(chunk)
        return bytes(data)
