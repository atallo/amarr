"""Enlaces magnet y su conversión a ed2k (``amarr/MagnetLink.kt``).

amarr usa enlaces *magnet* como interfaz con Sonarr/Radarr (que creen estar
hablando con qBittorrent) y los traduce a enlaces ``ed2k://`` para aMule. El
hash se guarda como bytes: ed2k usa 16 bytes (128 bits), mientras que el magnet
``btih`` usa 20 bytes (160 bits, base32). Se rellena/recorta según haga falta.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import List
from urllib.parse import quote, unquote

# Tracker reservado que marca un magnet como "propio" de amarr.
AMARR_TRACKER = "http://amarr-reserved"


def _encode_url(value: str) -> str:
    """Equivalente a ``encodeURLParameter()`` de Ktor (espacio -> %20)."""
    return quote(value, safe="")


def _decode_url(value: str) -> str:
    return unquote(value)


@dataclass
class MagnetLink:
    """Representa un enlace magnet con su hash, nombre, tamaño y trackers."""

    hash: bytes
    name: str
    size: int
    trackers: List[str] = field(default_factory=list)

    def amule_hex_hash(self) -> str:
        """Hash de 16 bytes (128 bits) en hexadecimal, como usa ed2k."""
        return self.hash[:16].hex()

    def to_ed2k_link(self) -> str:
        return f"ed2k://|file|{_encode_url(self.name)}|{self.size}|{self.amule_hex_hash()}|/"

    def is_amarr(self) -> bool:
        return AMARR_TRACKER in self.trackers

    def __str__(self) -> str:
        # Se rellena el hash a 20 bytes (160 bits) para el formato btih/base32.
        padded = self.hash[:20].ljust(20, b"\x00")
        base32_hash = base64.b32encode(padded).decode("ascii")
        trackers = "&tr=".join(_encode_url(t) for t in self.trackers)
        return (
            "magnet:"
            f"?xt=urn:btih:{base32_hash}"
            f"&dn={_encode_url(self.name)}"
            f"&xl={self.size}"
            f"&tr={trackers}"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MagnetLink):
            return False
        return (
            self.hash == other.hash
            and self.name == other.name
            and self.size == other.size
            and self.trackers == other.trackers
        )

    def __hash__(self) -> int:
        return hash((self.hash, self.name, self.size, tuple(self.trackers)))

    # --- fábricas -----------------------------------------------------------

    @staticmethod
    def for_amarr(hash: bytes, name: str, size: int) -> "MagnetLink":
        return MagnetLink(hash=hash, name=name, size=size, trackers=[AMARR_TRACKER])

    @staticmethod
    def from_string(magnet: str) -> "MagnetLink":
        body = magnet.split("magnet:?", 1)[-1]
        params: List[tuple[str, str]] = []
        for part in body.split("&"):
            if re.fullmatch(r".+=.+", part):
                key, value = part.split("=", 1)
                params.append((key, value))

        xt = next(v for k, v in params if k == "xt")
        b32 = xt.split("urn:btih:", 1)[-1]
        hash_bytes = base64.b32decode(b32)
        name = next(v for k, v in params if k == "dn")
        size = next(v for k, v in params if k == "xl")
        trackers = [_decode_url(v) for k, v in params if k == "tr"]

        return MagnetLink(
            hash=hash_bytes,
            name=_decode_url(name),
            size=int(size),
            trackers=trackers,
        )

    @staticmethod
    def from_ed2k(ed2k: str) -> "MagnetLink":
        body = ed2k.split("ed2k://|file|", 1)[-1].split("|/", 1)[0]
        els = body.split("|")
        return MagnetLink(
            hash=bytes.fromhex(els[2]),
            name=_decode_url(els[0]),
            size=int(els[1]),
            trackers=[AMARR_TRACKER],
        )
