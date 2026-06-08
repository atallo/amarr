# -*- coding: utf-8 -*-
"""Cliente eD2k/eMule (eDonkey2000 + Kad) 100% Python, sin dependencias externas.

Uso rapido:

    from ed2k import ServerSearch, KadSearch, print_results

    # Busqueda en servidor (TCP)
    results = ServerSearch("45.82.80.155:5687").search("ubuntu")

    # Busqueda en Kad (serverless, UDP) desde un nodes.dat
    results = KadSearch("nodes.dat").search("ubuntu", with_sources=True)

    for r in results:
        print(r.name, r.size, r.ed2k_link, r.sources)

Cada resultado es un `SearchResult` (name/raw_name/size/file_hash/sources/ed2k_link).
El progreso se emite via logging ('ed2k.server' / 'ed2k.kad'); por defecto silencioso.
"""
from .core import (
    SearchResult, print_results, sanitize_filename, decode_str, human_size,
    filter_by_query, setup_utf8_output,
)
from .md4 import md4
from .server import ServerSearch, Ed2kConnection, DEFAULT_SERVER
from .kad import KadSearch, KadClient, parse_nodes_dat, keyword_target, kad_id_int

__all__ = [
    "ServerSearch", "KadSearch", "SearchResult", "print_results",
    "Ed2kConnection", "KadClient", "parse_nodes_dat",
    "md4", "keyword_target", "kad_id_int",
    "sanitize_filename", "decode_str", "human_size", "filter_by_query",
    "setup_utf8_output", "DEFAULT_SERVER",
]
