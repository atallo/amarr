#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI de busqueda en un servidor eD2k. Toda la logica vive en el paquete `ed2k`."""
import argparse
import logging
import sys

from amarr.ed2k import ServerSearch, print_results, setup_utf8_output


def main():
    ap = argparse.ArgumentParser(
        description="Micro-cliente eD2k (eDonkey2000) 100% Python: busca por palabra "
                    "clave en un servidor.",
        epilog="Ejemplos:\n"
               "  python ed2k_search.py ubuntu\n"
               '  python ed2k_search.py "ubuntu 24.04 amd64" -n 20\n'
               "  python ed2k_search.py debian -s 45.82.80.155:5687\n"
               "  python ed2k_search.py debian --highid        # HighID, puerto aleatorio\n"
               "  python ed2k_search.py debian --highid 4662    # HighID en el puerto 4662\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", default=None, help="texto a buscar")
    ap.add_argument("-s", "--server", default="45.82.80.155:5687",
                    help="servidor eD2k host:puerto (def. 45.82.80.155:5687)")
    ap.add_argument("-n", "--max", type=int, default=50,
                    help="maximo de resultados a mostrar (def. 50)")
    ap.add_argument("-t", "--timeout", type=float, default=15.0,
                    help="timeout de socket en segundos (def. 15)")
    ap.add_argument("--highid", nargs="?", const=0, type=int, default=None, metavar="PUERTO",
                    help="intentar HighID: abre el puerto (UPnP) y escucha la conexion de "
                         "verificacion del servidor. Sin valor usa un puerto aleatorio; "
                         "o indica uno, p.ej. --highid 4662")
    ap.add_argument("--no-upnp", action="store_true",
                    help="con --highid, no intentar abrir el puerto por UPnP")
    ap.add_argument("-v", "--verbose", action="store_true", help="traza de paquetes")
    args = ap.parse_args()

    setup_utf8_output()
    if not args.query or not args.query.strip():
        ap.print_help()
        return 1

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(message)s", stream=sys.stdout)
    try:
        results = ServerSearch(args.server, timeout=args.timeout).search(
            args.query, highid_port=args.highid, use_upnp=not args.no_upnp)
    except (ConnectionError, OSError) as e:
        print("[!] %s" % e)
        return 1
    print_results(results, args.max)
    return 0


if __name__ == "__main__":
    sys.exit(main())
