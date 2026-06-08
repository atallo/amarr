#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI de busqueda en la red Kad. Toda la logica vive en el paquete `ed2k`."""
import argparse
import logging
import os
import sys

from amarr import ed2k as _ed2k_pkg
from amarr.ed2k import KadSearch, print_results, setup_utf8_output

# nodes.dat empaquetado con amarr (fallback por defecto).
_DEFAULT_NODES = os.path.join(os.path.dirname(_ed2k_pkg.__file__), "data", "nodes.dat")


def main():
    ap = argparse.ArgumentParser(
        description="Micro-cliente Kad (red Kademlia de eMule) 100% Python: busca por "
                    "palabra clave sin servidor (serverless, UDP).",
        epilog="Ejemplos:\n"
               "  python kad_search.py ubuntu\n"
               '  python kad_search.py "ubuntu 24.04" --nodes nodes.dat -n 20\n'
               "  python kad_search.py ubuntu --sources   # cuenta fuentes reales (lento)\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", default=None, help="texto a buscar")
    ap.add_argument("--nodes", default=_DEFAULT_NODES,
                    help="ruta a nodes.dat (def. el empaquetado con amarr)")
    ap.add_argument("--ip-order", choices=["be", "le"], default="be",
                    help="orden de bytes de las IPs en nodes.dat/paquetes")
    ap.add_argument("-n", "--max", type=int, default=50, help="max resultados a mostrar")
    ap.add_argument("--sources", action="store_true",
                    help="buscar fuentes reales por fichero (lento: lookup por fichero)")
    ap.add_argument("-v", "--verbose", action="store_true", help="traza de paquetes")
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
        print("[!] No encuentro %s. Descarga uno (p.ej. de emule-security.org)." % args.nodes)
        return 1
    except ValueError as e:
        print("[!] %s" % e)
        return 1

    results = kad.search(args.query, with_sources=args.sources, enrich_top=args.max)
    print_results(results, args.max)
    return 0


if __name__ == "__main__":
    sys.exit(main())
