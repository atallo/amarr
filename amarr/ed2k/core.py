# -*- coding: utf-8 -*-
"""Primitivas compartidas eD2k/Kad: tipos de tag y su parser, utilidades de texto
(decodificacion robusta, saneado de nombres, filtro de busqueda), tamano legible y
el modelo de resultado `SearchResult`. Sin dependencias externas (solo stdlib)."""
import struct
import sys
import unicodedata
from dataclasses import dataclass, field

# --- Tipos de tag (formato binario eD2k/eMule) ---
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

# --- Tags de fichero (resultados de busqueda) ---
FT_FILENAME = 0x01
FT_FILESIZE = 0x02
FT_FILETYPE = 0x03
FT_FILESIZE_HI = 0x3A
FT_SOURCES = 0x15
FT_COMPLETE_SOURCES = 0x30


# ======================= Texto =======================
def decode_str(raw):
    """Los nombres en eD2k/Kad no siempre son UTF-8 valido. Estrategia:
    1) UTF-8 estricto si es valido.
    2) Si falla pero el texto es UTF-8 con bytes sueltos rotos (hay acentos
       validos decodificables), se usa UTF-8 y los bytes rotos quedan como '�'.
    3) Si no, se asume CP1252/Latin-1 (datos legacy de servidor)."""
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
        return raw.decode("latin-1")  # nunca falla


_INVALID_FN_CHARS = set('<>:"/\\|?*') | {chr(c) for c in range(32)} | {"�"}


def sanitize_filename(name, repl="_"):
    """Convierte 'name' en un nombre de fichero valido y multiplataforma:
    sustituye los caracteres reservados de Windows (< > : " / \\ | ? *), los de
    control y el marcador de byte invalido por 'repl', y recorta puntos/espacios
    finales. Asi sirve tal cual como fichero y no rompe el enlace ed2k (donde '|'
    es el separador)."""
    if not isinstance(name, str):
        name = str(name)
    s = "".join(repl if ch in _INVALID_FN_CHARS else ch for ch in name)
    s = s.rstrip(" .")
    return s or "sin_nombre"


def _fold(s):
    """Normaliza para comparar: quita acentos (ñ->n, á->a) y pasa a minusculas.
    Asi la busqueda es insensible a acentos, igual que el servidor eD2k."""
    nfkd = unicodedata.normalize("NFKD", s)
    base = "".join(c for c in nfkd if not unicodedata.combining(c))
    return base.casefold()


def filter_by_query(results, query):
    """Filtra (hash, tags) para que el nombre contenga TODAS las palabras buscadas.
    Insensible a mayus/minus y a ACENTOS: buscar 'campaña' acepta tambien 'campana'
    y 'á' acepta 'a'."""
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
    """Hace que stdout muestre acentos correctamente. En Windows pone la consola
    en UTF-8 (code page 65001) para que ñ/á no salgan como mojibake ('Ã±')."""
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
    """Lee un tag eD2k/Kad en 'off'. Devuelve (nombre, valor, nuevo_off).
    El nombre es int para tags especiales (1 byte) o str para nombres largos."""
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
        raise ValueError("Tipo de tag desconocido: 0x%02X" % ttype)
    return name, val, off


# ======================= Resultado =======================
@dataclass
class SearchResult:
    """Un fichero encontrado. `name` ya viene saneado (valido como fichero);
    `raw_name` es el nombre original decodificado. `file_hash` son 16 bytes."""
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
            raw = "(sin nombre)"
        size = tags.get(FT_FILESIZE, 0)
        if FT_FILESIZE_HI in tags:
            size += tags[FT_FILESIZE_HI] << 32
        sources = tags.get("kad_sources", tags.get(FT_SOURCES))
        return cls(file_hash=file_hash, raw_name=raw, name=sanitize_filename(raw),
                   size=size, sources=sources,
                   complete_sources=tags.get(FT_COMPLETE_SOURCES), tags=tags)


def print_results(results, limit=50):
    """Imprime una lista de SearchResult (nombre, tamano, fuentes y enlace ed2k)."""
    if not results:
        print("[!] 0 resultados.")
        return
    extra = "" if len(results) <= limit else " (mostrando %d)" % limit
    print("[*] %d resultados%s:\n" % (len(results), extra))
    for r in results[:limit]:
        src = ""
        if r.sources is not None:
            src = "  fuentes=%s" % r.sources
            if r.complete_sources is not None:
                src += " (compl=%s)" % r.complete_sources
        print("  %s  [%s]%s" % (r.name, human_size(r.size), src))
        print("  %s\n" % r.ed2k_link)
