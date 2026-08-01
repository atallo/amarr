# -*- coding: utf-8 -*-
"""eD2k (eDonkey2000) server search client over TCP.

High-level API:
    from ed2k import ServerSearch
    results = ServerSearch("45.82.80.155:5687").search("ubuntu")
    for r in results:
        print(r.name, r.size, r.ed2k_link)

Progress is emitted via logging (logger 'ed2k.server'); silent by default.
"""
import logging
import os
import random
import socket
import struct
import threading
import time
import zlib

from .core import (read_tag, filter_by_query, SearchResult,
                   TT_STRING, TT_UINT32, FT_FILENAME, FT_FILESIZE)

log = logging.getLogger("ed2k.server")

# --- Bytes de protocolo ---
PR_ED2K = 0xE3
PR_EMULE = 0xC5
PR_PACKED = 0xD4  # zlib-compressed payload

# --- Opcodes client -> server ---
OP_LOGINREQUEST = 0x01
OP_SEARCHREQUEST = 0x16

# --- Opcodes server -> client ---
OP_REJECT = 0x05
OP_SERVERLIST = 0x32
OP_SEARCHRESULT = 0x33
OP_SERVERSTATUS = 0x34
OP_SERVERMESSAGE = 0x38
OP_IDCHANGE = 0x40
OP_SERVERIDENT = 0x41

# --- Client tags (login) ---
CT_NAME = 0x01
CT_PORT = 0x0F
CT_VERSION = 0x11
CT_SERVER_FLAGS = 0x20
CT_EMULE_VERSION = 0xFB

# --- Capabilities advertised to the server ---
SRVCAP_ZLIB = 0x0001
SRVCAP_NEWTAGS = 0x0008
SRVCAP_UNICODE = 0x0010
SRVCAP_LARGEFILES = 0x0100

EDONKEYVERSION = 0x3C  # 60
# Packed eMule version (eMule 0.50a): (mjr<<17)|(min<<10)|(upd<<7)
EMULE_VERSION = (0 << 17) | (50 << 10) | (1 << 7)

DEFAULT_SERVER = "45.82.80.155:5687"


# ======================= Packet building =======================
def _old_tag(ttype, name_byte, value_bytes):
    return bytes([ttype]) + struct.pack("<H", 1) + bytes([name_byte]) + value_bytes


def _str_tag(name_byte, s):
    d = s.encode("utf-8")
    return _old_tag(TT_STRING, name_byte, struct.pack("<H", len(d)) + d)


def _u32_tag(name_byte, v):
    return _old_tag(TT_UINT32, name_byte, struct.pack("<I", v))


def build_search_tree(query):
    """Serializes the eD2k search tree (AND of the words)."""
    words = query.split()

    def term(w):
        d = w.encode("utf-8")
        return bytes([0x01]) + struct.pack("<H", len(d)) + d

    if len(words) <= 1:
        return term(query.strip())
    tree = term(words[0])
    for w in words[1:]:
        tree = bytes([0x00, 0x00]) + tree + term(w)  # AND(prev, w)
    return tree


def read_string(payload, off=0):
    slen = struct.unpack_from("<H", payload, off)[0]
    from .core import decode_str
    return decode_str(payload[off + 2:off + 2 + slen])


def parse_search_result(payload):
    """Parses an OP_SEARCHRESULT -> list of (file_hash, tags)."""
    off = 0
    count = struct.unpack_from("<I", payload, off)[0]
    off += 4
    results = []
    for _ in range(count):
        if off + 26 > len(payload):  # 16 hash + 4 id + 2 port + 4 tagcount
            break
        fhash = payload[off:off + 16]
        off += 16 + 4 + 2  # hash + client ID + client port
        ntags = struct.unpack_from("<I", payload, off)[0]
        off += 4
        tags = {}
        for _ in range(ntags):
            name, val, off = read_tag(payload, off)
            tags[name] = val
        results.append((fhash, tags))
    return results


# ======================= Low-level connection =======================
class Ed2kConnection:
    def __init__(self, host, port, timeout=15.0):
        self.host = host
        self.port = port
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = bytearray()

    def _read_exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("The server closed the connection")
            self.buf += chunk
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def recv_packet(self):
        proto = self._read_exact(1)[0]
        size = struct.unpack("<I", self._read_exact(4))[0]
        body = self._read_exact(size)
        opcode = body[0]
        payload = body[1:]
        if proto == PR_PACKED:
            payload = zlib.decompress(payload)
        log.debug("    <- proto=0x%02X op=0x%02X len=%d", proto, opcode, len(payload))
        return opcode, payload

    def send_packet(self, opcode, payload=b"", proto=PR_ED2K):
        body = bytes([opcode]) + payload
        pkt = bytes([proto]) + struct.pack("<I", len(body)) + body
        self.sock.sendall(pkt)
        log.debug("    -> proto=0x%02X op=0x%02X len=%d", proto, opcode, len(payload))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def login(self, nick="hydra", client_port=4662):
        h = bytearray(os.urandom(16))
        h[5] = 14  # eMule client marker
        h[14] = 111
        payload = bytes(h)
        payload += struct.pack("<I", 0)  # client ID (0 at startup)
        payload += struct.pack("<H", client_port)
        flags = SRVCAP_NEWTAGS | SRVCAP_UNICODE | SRVCAP_LARGEFILES | SRVCAP_ZLIB
        tags = [
            _str_tag(CT_NAME, nick),
            _u32_tag(CT_VERSION, EDONKEYVERSION),
            _u32_tag(CT_SERVER_FLAGS, flags),
            _u32_tag(CT_PORT, client_port),
            _u32_tag(CT_EMULE_VERSION, EMULE_VERSION),
        ]
        payload += struct.pack("<I", len(tags)) + b"".join(tags)
        self.send_packet(OP_LOGINREQUEST, payload)

    def search(self, query):
        self.send_packet(OP_SEARCHREQUEST, build_search_tree(query))


# ======================= HighID (listener TCP) =======================
def pick_random_port():
    return random.randint(1100, 64000)


def start_callback_listener(port):
    """Listens on TCP 'port' (0 = free port assigned by the OS) and accepts the
    server's verification connection (grants HighID if accepted).
    Only grants HighID if the port is reachable (public IP or UPnP/port-forwarding).
    Returns (stop_event, hits, actual_port) or None if it could not listen."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
        srv.listen(5)
    except OSError as e:
        log.info("[!] Could not listen on TCP %d (HighID): %s", port, e)
        srv.close()
        return None
    actual = srv.getsockname()[1]
    stop = threading.Event()
    hits = []

    def loop():
        srv.settimeout(0.5)
        while not stop.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            hits.append(addr[0])
            try:
                conn.settimeout(2.0)
                conn.recv(1024)
            except OSError:
                pass
            finally:
                conn.close()
        srv.close()

    threading.Thread(target=loop, daemon=True).start()
    log.info("[*] Listening on TCP %d for HighID (requires a reachable port).", actual)
    return stop, hits, actual


def _try_upnp(port, host):
    try:
        from . import upnp
        m = upnp.PortMapping(port, "TCP", "ed2k-python")
        log.info("[*] UPnP: looking for a router to open port %d...", port)
        if m.open(server_host=host):
            log.info("[*] UPnP: port %d opened. Public IP=%s", port, m.public_ip or "?")
            return m
        log.info("[!] UPnP: %s", m.error)
    except Exception as e:
        log.info("[!] UPnP not available: %s", e)
    return None


# ======================= API de alto nivel =======================
class ServerSearch:
    """Keyword search on an eD2k server.

    server: "host:port" (default: the example server).
    """

    def __init__(self, server=DEFAULT_SERVER, timeout=15.0, nick="hydra"):
        host, _, p = server.partition(":")
        self.host = host
        self.port = int(p or "4661")
        self.timeout = timeout
        self.nick = nick

    def search(self, query, highid_port=None, use_upnp=True):
        """Searches 'query' and returns a list of SearchResult (all of them; the
        display limit is up to whoever prints them).

        highid_port: None = don't attempt HighID (random advertised port);
                     0 = HighID with a random port; N = HighID with port N.
        use_upnp: with HighID, try to open the port via UPnP.

        Raises ConnectionError if it cannot connect or the server rejects.
        """
        listener = mapping = None
        try:
            if highid_port is not None:
                listener = start_callback_listener(highid_port or 0)
                my_port = listener[2] if listener else (highid_port or pick_random_port())
                if listener and use_upnp:
                    mapping = _try_upnp(my_port, self.host)
            else:
                my_port = pick_random_port()

            log.info("[*] Connecting to %s:%d ...", self.host, self.port)
            conn = Ed2kConnection(self.host, self.port, timeout=self.timeout)
            try:
                conn.login(nick=self.nick, client_port=my_port)
                self._await_login(conn, bool(listener), bool(mapping), my_port)
                log.info("[*] Searching: %r", query)
                conn.search(query)
                pairs = self._await_results(conn)
            finally:
                conn.close()
        finally:
            if listener:
                listener[0].set()
            if mapping:
                mapping.close()

        pairs = filter_by_query(pairs, query)
        return [SearchResult.from_tags(h, t) for h, t in pairs]

    def _await_login(self, conn, has_listener, has_mapping, my_port):
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                op, payload = conn.recv_packet()
            except socket.timeout:
                break
            if op == OP_SERVERMESSAGE:
                log.info("[server] %s", read_string(payload))
            elif op == OP_SERVERSTATUS:
                users = struct.unpack_from("<I", payload, 0)[0]
                files = struct.unpack_from("<I", payload, 4)[0]
                log.info("[*] Status: %d users, %d files", users, files)
            elif op == OP_IDCHANGE:
                newid = struct.unpack_from("<I", payload, 0)[0]
                kind = "HighID" if newid >= 0x00FFFFFF else "LowID"
                log.info("[*] Login OK. ID=%d (%s)", newid, kind)
                if has_listener and kind == "LowID":
                    if has_mapping:
                        log.info("    (HighID failed despite the UPnP mapping. Possible ISP CG-NAT.)")
                    else:
                        log.info("    (HighID failed: the server could not connect to your "
                                 "port %d. UPnP or manual port-forwarding is needed.)", my_port)
                return
            elif op == OP_REJECT:
                raise ConnectionError("The server rejected the connection")
        log.info("[!] IDCHANGE did not arrive; searching anyway.")

    def _await_results(self, conn):
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                op, payload = conn.recv_packet()
            except socket.timeout:
                break
            if op == OP_SEARCHRESULT:
                return parse_search_result(payload)
            elif op == OP_SERVERMESSAGE:
                log.info("[server] %s", read_string(payload))
        log.info("[!] No results arrived (timeout).")
        return []
