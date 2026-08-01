# -*- coding: utf-8 -*-
"""Shared eD2k/Kad primitives: tag types and their parser, text utilities
(robust decoding, name sanitizing, search filter), human-readable size and
the `SearchResult` result model. No external dependencies (stdlib only)."""
import struct
import sys
import unicodedata
from dataclasses import dataclass, field

# --- Tag types (eD2k/eMule binary format) ---
TT_HASH = 0x01
TT_STRING = 0x02
TT_UINT32 = 0x03
TT_FLOAT = 0x04
TT_BOOL = 0x05
TT_BOOLARRAY = 0x06
TT_BLOB = 0x07
TT_UINT16 = 0x08
TT_UINT8 = 0x09
TT_BSOB = 0x0A
TT_UINT64 = 0x0B
TT_STR1 = 0x11
TT_STR16 = 0x20

# --- File tags (search results) ---
FT_FILENAME = 0x01
FT_FILESIZE = 0x02
FT_FILETYPE = 0x03
FT_FILESIZE_HI = 0x3A
FT_SOURCES = 0x15
FT_COMPLETE_SOURCES = 0x30


# ======================= Text =======================
def decode_str(raw):
    """Names in eD2k/Kad are not always valid UTF-8. Strategy:
    1) Strict UTF-8 if it is valid.
    2) If it fails but the text is UTF-8 with a few broken bytes (there are
       valid decodable accents), UTF-8 is used and the broken bytes become '�'.
    3) Otherwise, CP1252/Latin-1 is assumed (legacy server data)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    u = raw.decode("utf-8", "replace")
    if any(ord(c) > 127 and c != "�" for c in u):
        return u
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        return raw.decode("latin-1")  # never fails


_INVALID_FN_CHARS = set('<>:"/\\|?*') | {chr(c) for c in range(32)} | {"�"}


def sanitize_filename(name, repl="_"):
    """Turns 'name' into a valid, cross-platform file name:
    replaces the Windows reserved characters (< > : " / \\ | ? *), the control
    ones and the invalid-byte marker with 'repl', and trims trailing dots/spaces.
    This way it works as a file as-is and does not break the ed2k link (where '|'
    is the separator)."""
    if not isinstance(name, str):
        name = str(name)
    s = "".join(repl if ch in _INVALID_FN_CHARS else ch for ch in name)
    s = s.rstrip(" .")
    return s or "no_name"


def _fold(s):
    """Normalizes for comparison: removes accents (ñ->n, á->a) and lowercases.
    This way the search is accent-insensitive, just like the eD2k server."""
    nfkd = unicodedata.normalize("NFKD", s)
    base = "".join(c for c in nfkd if not unicodedata.combining(c))
    return base.casefold()


def filter_by_query(results, query):
    """Filters (hash, tags) so the name contains ALL the searched words.
    Case- and ACCENT-insensitive: searching 'campaña' also accepts 'campana'
    and 'á' accepts 'a'."""
    words = [_fold(w) for w in query.split() if w.strip()]
    if not words:
        return results
    out = []
    for fhash, tags in results:
        name = tags.get(FT_FILENAME, "")
        low = _fold(name) if isinstance(name, str) else ""
        if all(w in low for w in words):
            out.append((fhash, tags))
    return out


def human_size(n):
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return ("%.0f %s" % (f, u)) if u == "B" else ("%.2f %s" % (f, u))
        f /= 1024


def setup_utf8_output():
    """Makes stdout display accents correctly. On Windows it sets the console
    to UTF-8 (code page 65001) so that ñ/á don't come out as mojibake ('Ã±')."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# ======================= Tags =======================
def read_tag(buf, off):
    """Reads an eD2k/Kad tag at 'off'. Returns (name, value, new_off).
    The name is int for special tags (1 byte) or str for long names."""
    ttype = buf[off]
    off += 1
    if ttype & 0x80:
        ttype &= 0x7F
        name = buf[off]
        off += 1
    else:
        nlen = struct.unpack_from("<H", buf, off)[0]
        off += 2
        if nlen == 1:
            name = buf[off]
            off += 1
        else:
            name = decode_str(buf[off:off + nlen])
            off += nlen

    if TT_STR1 <= ttype <= TT_STR16:
        slen = ttype - TT_STR1 + 1
        val = decode_str(buf[off:off + slen])
        off += slen
    elif ttype == TT_STRING:
        slen = struct.unpack_from("<H", buf, off)[0]
        off += 2
        val = decode_str(buf[off:off + slen])
        off += slen
    elif ttype == TT_UINT32:
        val = struct.unpack_from("<I", buf, off)[0]
        off += 4
    elif ttype == TT_UINT16:
        val = struct.unpack_from("<H", buf, off)[0]
        off += 2
    elif ttype == TT_UINT8:
        val = buf[off]
        off += 1
    elif ttype == TT_UINT64:
        val = struct.unpack_from("<Q", buf, off)[0]
        off += 8
    elif ttype == TT_FLOAT:
        val = struct.unpack_from("<f", buf, off)[0]
        off += 4
    elif ttype == TT_HASH:
        val = buf[off:off + 16]
        off += 16
    elif ttype == TT_BOOL:
        val = bool(buf[off])
        off += 1
    elif ttype == TT_BLOB:
        blen = struct.unpack_from("<I", buf, off)[0]
        off += 4
        val = buf[off:off + blen]
        off += blen
    elif ttype == TT_BSOB:  # 0x0A: uint8 length + bytes
        blen = buf[off]
        off += 1
        val = buf[off:off + blen]
        off += blen
    elif ttype == TT_BOOLARRAY:  # 0x06: uint16 bits + ceil(bits/8) bytes
        nbits = struct.unpack_from("<H", buf, off)[0]
        off += 2 + (nbits + 7) // 8
        val = None
    else:
        raise ValueError("Unknown tag type: 0x%02X" % ttype)
    return name, val, off


# ======================= Result =======================
@dataclass
class SearchResult:
    """A found file. `name` is already sanitized (valid as a file);
    `raw_name` is the original decoded name. `file_hash` is 16 bytes."""
    file_hash: bytes
    name: str
    raw_name: str
    size: int
    sources: object = None
    complete_sources: object = None
    tags: dict = field(default_factory=dict, repr=False)

    @property
    def hex_hash(self):
        return self.file_hash.hex()

    @property
    def ed2k_link(self):
        return "ed2k://|file|%s|%d|%s|/" % (self.name, self.size, self.hex_hash)

    @classmethod
    def from_tags(cls, file_hash, tags):
        raw = tags.get(FT_FILENAME, "")
        if not isinstance(raw, str) or not raw:
            raw = "(no name)"
        size = tags.get(FT_FILESIZE, 0)
        if FT_FILESIZE_HI in tags:
            size += tags[FT_FILESIZE_HI] << 32
        sources = tags.get("kad_sources", tags.get(FT_SOURCES))
        return cls(file_hash=file_hash, raw_name=raw, name=sanitize_filename(raw),
                   size=size, sources=sources,
                   complete_sources=tags.get(FT_COMPLETE_SOURCES), tags=tags)


def print_results(results, limit=50):
    """Prints a list of SearchResult (name, size, sources and ed2k link)."""
    if not results:
        print("[!] 0 results.")
        return
    extra = "" if len(results) <= limit else " (showing %d)" % limit
    print("[*] %d results%s:\n" % (len(results), extra))
    for r in results[:limit]:
        src = ""
        if r.sources is not None:
            src = "  sources=%s" % r.sources
            if r.complete_sources is not None:
                src += " (complete=%s)" % r.complete_sources
        print("  %s  [%s]%s" % (r.name, human_size(r.size), src))
        print("  %s\n" % r.ed2k_link)
