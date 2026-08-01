# -*- coding: utf-8 -*-
"""eD2k/eMule (eDonkey2000 + Kad) client, 100% Python, no external dependencies.

Quick usage:

    from ed2k import ServerSearch, KadSearch, print_results

    # Server search (TCP)
    results = ServerSearch("45.82.80.155:5687").search("ubuntu")

    # Kad search (serverless, UDP) from a nodes.dat
    results = KadSearch("nodes.dat").search("ubuntu", with_sources=True)

    for r in results:
        print(r.name, r.size, r.ed2k_link, r.sources)

Each result is a `SearchResult` (name/raw_name/size/file_hash/sources/ed2k_link).
Progress is emitted via logging ('ed2k.server' / 'ed2k.kad'); silent by default.
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
