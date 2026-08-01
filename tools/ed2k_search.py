#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eD2k server search CLI. All the logic lives in the `ed2k` package."""
import argparse
import logging
import sys

from amarr.ed2k import ServerSearch, print_results, setup_utf8_output


def main():
    ap = argparse.ArgumentParser(
        description="eD2k (eDonkey2000) micro-client, 100% Python: keyword "
                    "search on a server.",
        epilog="Examples:\n"
               "  python ed2k_search.py ubuntu\n"
               '  python ed2k_search.py "ubuntu 24.04 amd64" -n 20\n'
               "  python ed2k_search.py debian -s 45.82.80.155:5687\n"
               "  python ed2k_search.py debian --highid        # HighID, random port\n"
               "  python ed2k_search.py debian --highid 4662    # HighID on port 4662\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", default=None, help="text to search for")
    ap.add_argument("-s", "--server", default="45.82.80.155:5687",
                    help="eD2k server host:port (default 45.82.80.155:5687)")
    ap.add_argument("-n", "--max", type=int, default=50,
                    help="maximum number of results to show (default 50)")
    ap.add_argument("-t", "--timeout", type=float, default=15.0,
                    help="socket timeout in seconds (default 15)")
    ap.add_argument("--highid", nargs="?", const=0, type=int, default=None, metavar="PORT",
                    help="attempt HighID: open the port (UPnP) and listen for the server's "
                         "verification connection. Without a value it uses a random port; "
                         "or specify one, e.g. --highid 4662")
    ap.add_argument("--no-upnp", action="store_true",
                    help="with --highid, don't try to open the port via UPnP")
    ap.add_argument("-v", "--verbose", action="store_true", help="packet trace")
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
