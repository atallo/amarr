#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kad network search CLI. All the logic lives in the `ed2k` package."""
import argparse
import logging
import os
import sys

from amarr import ed2k as _ed2k_pkg
from amarr.ed2k import KadSearch, print_results, setup_utf8_output

# nodes.dat bundled with amarr (default fallback).
_DEFAULT_NODES = os.path.join(os.path.dirname(_ed2k_pkg.__file__), "data", "nodes.dat")


def main():
    ap = argparse.ArgumentParser(
        description="Kad (eMule's Kademlia network) micro-client, 100% Python: keyword "
                    "search with no server (serverless, UDP).",
        epilog="Examples:\n"
               "  python kad_search.py ubuntu\n"
               '  python kad_search.py "ubuntu 24.04" --nodes nodes.dat -n 20\n'
               "  python kad_search.py ubuntu --sources   # counts real sources (slow)\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", default=None, help="text to search for")
    ap.add_argument("--nodes", default=_DEFAULT_NODES,
                    help="path to nodes.dat (default: the one bundled with amarr)")
    ap.add_argument("--ip-order", choices=["be", "le"], default="be",
                    help="byte order of the IPs in nodes.dat/packets")
    ap.add_argument("-n", "--max", type=int, default=50, help="max results to show")
    ap.add_argument("--sources", action="store_true",
                    help="search for real sources per file (slow: per-file lookup)")
    ap.add_argument("-v", "--verbose", action="store_true", help="packet trace")
    args = ap.parse_args()

    setup_utf8_output()
    if not args.query or not args.query.strip():
        ap.print_help()
        return 1

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(message)s", stream=sys.stdout)
    try:
        kad = KadSearch(args.nodes, ip_order=args.ip_order, verbose=args.verbose)
    except FileNotFoundError:
        print("[!] Can't find %s. Download one (e.g. from emule-security.org)." % args.nodes)
        return 1
    except ValueError as e:
        print("[!] %s" % e)
        return 1

    results = kad.search(args.query, with_sources=args.sources, enrich_top=args.max)
    print_results(results, args.max)
    return 0


if __name__ == "__main__":
    sys.exit(main())
