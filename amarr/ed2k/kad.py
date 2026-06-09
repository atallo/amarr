# -*- coding: utf-8 -*-
"""Cliente de busqueda en la red Kad (Kademlia de eMule), serverless sobre UDP.

API de alto nivel:
    from ed2k import KadSearch
    kad = KadSearch("nodes.dat")
    results = kad.search("ubuntu")                 # disponibilidad publicada
    results = kad.search("ubuntu", with_sources=True)  # fuentes reales (mas lento)

Flujo interno: bootstrap desde nodes.dat -> lookup iterativo hacia md4(keyword)
-> KADEMLIA2_SEARCH_KEY_REQ a los nodos cercanos -> parseo de resultados.
El progreso se emite por logging (logger 'ed2k.kad'); por defecto silencioso.
"""
import logging
import os
import socket
import struct
import time
import zlib

from .md4 import md4
from .core import (read_tag, filter_by_query, SearchResult,
                   FT_FILENAME, FT_FILESIZE, FT_FILESIZE_HI, FT_SOURCES)

log = logging.getLogger("ed2k.kad")

# --- Bytes de protocolo Kad ---
PR_KAD = 0xE4
PR_KAD_PACKED = 0xE5

# --- Opcodes Kad2 ---
KADEMLIA2_BOOTSTRAP_REQ = 0x01
KADEMLIA2_BOOTSTRAP_RES = 0x09
KADEMLIA2_HELLO_REQ = 0x11
KADEMLIA2_HELLO_RES = 0x19
KADEMLIA2_REQ = 0x21
KADEMLIA2_RES = 0x29
KADEMLIA2_SEARCH_KEY_REQ = 0x33
KADEMLIA2_SEARCH_SOURCE_REQ = 0x34
KADEMLIA2_SEARCH_RES = 0x3B
KADEMLIA2_PING = 0x60
KADEMLIA2_PONG = 0x61

KAD_FIND_NODE = 0x0B  # nº de contactos a pedir en un KADEMLIA2_REQ


# ======================= Identificadores Kad =======================
def kad_id_int(b):
    """Interpreta los 16 bytes de un ID Kad como el CUInt128 de eMule: 4 uint32 en
    little-endian con la PRIMERA palabra como la mas significativa. Es la metrica
    de distancia XOR de eMule (big-endian crudo descoloca las palabras)."""
    w = struct.unpack("<4I", b)
    return (w[0] << 96) | (w[1] << 64) | (w[2] << 32) | w[3]


def word_reverse(b16):
    """Invierte los bytes dentro de cada palabra de 32 bits (4 grupos de 4)."""
    return b"".join(b16[i:i + 4][::-1] for i in range(0, 16, 4))


def keyword_target(keyword):
    """Hash de keyword para enrutar en Kad: MD4(UTF-8) con cada palabra de 32 bits
    invertida. eMule construye el CUInt128 con SetValueBE, lo que en el cable
    equivale a invertir cada grupo de 4 bytes del MD4."""
    return word_reverse(md4(keyword.encode("utf-8")))


# ======================= nodes.dat =======================
def ip_to_str(ipval, order):
    fmt = ">I" if order == "be" else "<I"
    return socket.inet_ntoa(struct.pack(fmt, ipval))


def parse_nodes_dat(path, ip_order="be"):
    """Lee un nodes.dat -> (contactos, version, bytes_por_contacto)."""
    with open(path, "rb") as f:
        d = f.read()
    marker, = struct.unpack_from("<I", d, 0)
    off = 4
    version = 0
    if marker == 0:
        version, = struct.unpack_from("<I", d, off); off += 4
        count, = struct.unpack_from("<I", d, off); off += 4
    else:
        count = marker  # formato legacy
    rest = len(d) - off
    per = rest // count if count else 0
    contacts = []
    for _ in range(count):
        if off + 25 > len(d):
            break
        kid = d[off:off + 16]; off += 16
        ip, = struct.unpack_from("<I", d, off); off += 4
        udp, tcp = struct.unpack_from("<HH", d, off); off += 4
        cver = d[off]; off += 1
        if per >= 34:      # v2/v3: clave UDP (8) + verified (1)
            off += 9
        elif per >= 26:
            off += 1
        contacts.append({
            "id": kid, "id_int": kad_id_int(kid),
            "ip": ip_to_str(ip, ip_order), "udp": udp, "tcp": tcp, "ver": cver,
        })
    return contacts, version, per


# ======================= Motor de bajo nivel =======================
class KadClient:
    def __init__(self, ip_order="be", verbose=False, timeout=3.0):
        self.verbose = verbose
        self.ip_order = ip_order
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        self.sock.settimeout(timeout)
        self.my_id = os.urandom(16)
        self.alive = set()  # (ip, udp) que han respondido
        self.contacts = {}  # pool de contactos descubierto (lo reutiliza KadSession)
        self.stats = {"sent": 0, "boot_res": 0, "res": 0, "search_res": 0,
                      "encrypted": 0, "other": 0}

    def close(self):
        self.sock.close()

    def send(self, opcode, payload, ip, port):
        try:
            self.sock.sendto(bytes([PR_KAD, opcode]) + payload, (ip, port))
            self.stats["sent"] += 1
        except OSError:
            pass

    def send_bootstrap(self, contact):
        self.send(KADEMLIA2_BOOTSTRAP_REQ, b"", contact["ip"], contact["udp"])

    def send_req(self, target, contact):
        self.send(KADEMLIA2_REQ, bytes([KAD_FIND_NODE]) + target + contact["id"],
                  contact["ip"], contact["udp"])

    def send_search_key(self, target, contact):
        self.send(KADEMLIA2_SEARCH_KEY_REQ, target + struct.pack("<H", 0),
                  contact["ip"], contact["udp"])

    def recv_for(self, duration):
        """Recibe y despacha paquetes durante 'duration' s.
        Devuelve (contactos_nuevos, resultados_busqueda)."""
        end = time.time() + duration
        new_contacts, results = [], []
        while time.time() < end:
            self.sock.settimeout(max(0.05, end - time.time()))
            try:
                data, addr = self.sock.recvfrom(8192)
            except (socket.timeout, OSError):
                break
            if len(data) < 2:
                continue
            proto = data[0]
            if proto not in (PR_KAD, PR_KAD_PACKED):
                self.stats["encrypted"] += 1  # probablemente ofuscado/cifrado
                continue
            opcode, payload = data[1], data[2:]
            if proto == PR_KAD_PACKED:
                try:
                    payload = zlib.decompress(payload)
                except zlib.error:
                    continue
            self.alive.add(addr)
            if opcode == KADEMLIA2_RES:
                self.stats["res"] += 1
                new_contacts.extend(self._parse_res(payload))
            elif opcode == KADEMLIA2_BOOTSTRAP_RES:
                self.stats["boot_res"] += 1
                new_contacts.extend(self._parse_bootstrap(payload))
            elif opcode == KADEMLIA2_SEARCH_RES:
                self.stats["search_res"] += 1
                results.extend(self._parse_search_res(payload))
            else:
                self.stats["other"] += 1
        return new_contacts, results

    def _parse_bootstrap(self, payload):
        out = []
        try:
            off = 19  # id(16) + tcp(2) + ver(1)
            count, = struct.unpack_from("<H", payload, off); off += 2
            for _ in range(count):
                kid = payload[off:off + 16]; off += 16
                ip, = struct.unpack_from("<I", payload, off); off += 4
                udp, tcp = struct.unpack_from("<HH", payload, off); off += 4
                ver = payload[off]; off += 1
                out.append({"id": kid, "id_int": kad_id_int(kid),
                            "ip": ip_to_str(ip, self.ip_order),
                            "udp": udp, "tcp": tcp, "ver": ver})
        except (IndexError, struct.error):
            pass
        return out

    def _parse_res(self, payload):
        out = []
        try:
            off = 16  # target (echo)
            count = payload[off]; off += 1
            for _ in range(count):
                kid = payload[off:off + 16]; off += 16
                ip, = struct.unpack_from("<I", payload, off); off += 4
                udp, tcp = struct.unpack_from("<HH", payload, off); off += 4
                ver = payload[off]; off += 1
                out.append({"id": kid, "id_int": kad_id_int(kid),
                            "ip": ip_to_str(ip, self.ip_order),
                            "udp": udp, "tcp": tcp, "ver": ver})
        except (IndexError, struct.error):
            pass
        return out

    def _parse_search_res(self, payload):
        """SEARCH_RES: [source 16][target 16][count u16] luego por fichero
        [fileID 16][tagcount u8][tags]. Cabecera de 32; reintenta con 16."""
        for header in (32, 16):
            try:
                res = self._try_parse_search(payload, header)
                if res:
                    return res
            except (IndexError, struct.error):
                continue
        log.debug("    [!] SEARCH_RES no parseado, hex: %s", payload[:48].hex())
        return []

    def _try_parse_search(self, payload, header):
        off = header
        count, = struct.unpack_from("<H", payload, off); off += 2
        if count == 0 or count > 2000:
            return []
        out = []
        for _ in range(count):
            try:
                answer = payload[off:off + 16]; off += 16
                ntags = payload[off]; off += 1
                tags = {}
                for _ in range(ntags):
                    name, val, off = read_tag(payload, off)
                    tags[name] = val
                # answer ID es CUInt128; el hash ed2k es la version word-reversed.
                out.append({"hash": word_reverse(answer), "tags": tags})
            except (IndexError, struct.error, ValueError):
                break
        return out

    def enrich_sources(self, results, contacts, top, rounds=5, alpha=6,
                       per_file_nodes=15, gather=3.0):
        """Para los 'top' ficheros: lookup hacia el hash del fichero y luego
        KADEMLIA2_SEARCH_SOURCE_REQ, contando clientes distintos. Guarda el conteo
        en tags['kad_sources']."""
        base = list(contacts)
        log.info("[*] Buscando fuentes reales de %d ficheros (lookup por fichero)...",
                 min(top, len(results)))
        for fhash, tags in results[:top]:
            wire = word_reverse(fhash)
            tint = kad_id_int(wire)
            fsize = tags.get(FT_FILESIZE, 0) + (tags.get(FT_FILESIZE_HI, 0) << 32)
            pool = {c["id"]: c for c in base}
            queried = set()
            for _ in range(rounds):
                cand = sorted((c for k, c in pool.items() if k not in queried),
                              key=lambda c: c["id_int"] ^ tint)[:alpha]
                if not cand:
                    break
                for c in cand:
                    queried.add(c["id"])
                    self.send_req(wire, c)
                new, _ = self.recv_for(1.0)
                for c in new:
                    pool.setdefault(c["id"], c)
            closest = sorted(pool.values(), key=lambda c: c["id_int"] ^ tint)[:per_file_nodes]
            payload = wire + struct.pack("<H", 0) + struct.pack("<Q", fsize)
            for c in closest:
                self.send(KADEMLIA2_SEARCH_SOURCE_REQ, payload, c["ip"], c["udp"])
            srcs = set()
            end = time.time() + gather
            while time.time() < end:
                self.sock.settimeout(max(0.05, end - time.time()))
                try:
                    data, _ = self.sock.recvfrom(16384)
                except (socket.timeout, OSError):
                    break
                if (len(data) < 3 or data[0] not in (PR_KAD, PR_KAD_PACKED)
                        or data[1] != KADEMLIA2_SEARCH_RES):
                    continue
                p = data[2:]
                if data[0] == PR_KAD_PACKED:
                    try:
                        p = zlib.decompress(p)
                    except zlib.error:
                        continue
                if p[16:32] != wire:
                    continue
                try:
                    cnt, = struct.unpack_from("<H", p, 32); off = 34
                    for _ in range(cnt):
                        sid = p[off:off + 16]; off += 16
                        ntags = p[off]; off += 1
                        for _ in range(ntags):
                            _, _, off = read_tag(p, off)
                        srcs.add(sid)
                except (IndexError, struct.error, ValueError):
                    continue
            tags["kad_sources"] = len(srcs)

    def keyword_search(self, query, seeds, rounds=15, alpha=8, search_nodes=30,
                       gather=1.5, search_gather=5.0, enrich_top=25, do_sources=False):
        """Hace bootstrap + lookup + busqueda y devuelve lista de (hash, tags)."""
        words = query.lower().split()
        target = keyword_target(words[0])
        tint = kad_id_int(target)
        log.info("[*] Keyword '%s' -> target Kad=%s", words[0], target.hex())

        contacts = {c["id_int"]: c for c in seeds}
        for c in seeds:
            self.send_bootstrap(c)
        boot, _ = self.recv_for(5.0)
        for c in boot:
            contacts.setdefault(c["id_int"], c)
        log.info("[*] Bootstrap: %d respuestas, pool de %d contactos",
                 self.stats["boot_res"], len(contacts))

        queried = set()
        for rnd in range(rounds):
            cand = sorted((c for cid, c in contacts.items() if cid not in queried),
                          key=lambda c: c["id_int"] ^ tint)[:alpha]
            if not cand:
                break
            for c in cand:
                queried.add(c["id_int"])
                self.send_req(target, c)
            new, _ = self.recv_for(gather)
            added = 0
            for c in new:
                if c["id_int"] not in contacts:
                    contacts[c["id_int"]] = c
                    added += 1
            dmin = min((c["id_int"] ^ tint for c in contacts.values()), default=0)
            alive = [c for c in contacts.values() if (c["ip"], c["udp"]) in self.alive]
            amin = min((c["id_int"] ^ tint for c in alive), default=0)
            log.info("[*] Ronda %2d: +%d contactos (total %d, vivos %d), "
                     "dist min=%d bits (vivos=%d)", rnd + 1, added, len(contacts),
                     len(alive), dmin.bit_length(), amin.bit_length())

        alive = [c for c in contacts.values() if (c["ip"], c["udp"]) in self.alive]
        closest = sorted(alive or list(contacts.values()),
                         key=lambda c: c["id_int"] ^ tint)[:search_nodes]
        log.info("[*] Consultando %d nodos vivos cercanos con SEARCH_KEY_REQ...", len(closest))
        for c in closest:
            self.send_search_key(target, c)
        _, results = self.recv_for(search_gather)
        _, more = self.recv_for(2.0)
        results.extend(more)

        # Dedup por hash quedandonos con la mayor disponibilidad publicada.
        dedup = {}
        for r in results:
            h = r["hash"]
            if h not in dedup or r["tags"].get(FT_SOURCES, 0) > dedup[h].get(FT_SOURCES, 0):
                dedup[h] = r["tags"]

        out = filter_by_query(list(dedup.items()), query)
        out.sort(key=lambda r: r[1].get(FT_SOURCES, 0), reverse=True)

        # Exponer el pool de contactos descubierto (lo reutiliza KadSession).
        self.contacts = contacts

        if do_sources:
            self.enrich_sources(out, list(contacts.values()), min(enrich_top, 8))
            out.sort(key=lambda r: r[1].get("kad_sources", -1), reverse=True)
        return out


# ======================= API de alto nivel =======================
class KadSearch:
    """Busqueda por palabra clave en la red Kad. Carga nodes.dat al construirse."""

    def __init__(self, nodes_path="nodes.dat", ip_order="be", timeout=3.0, verbose=False):
        self.seeds, self.version, self.per = parse_nodes_dat(nodes_path, ip_order)
        if not self.seeds:
            raise ValueError("nodes.dat sin contactos semilla: %s" % nodes_path)
        self.ip_order = ip_order
        self.timeout = timeout
        self.verbose = verbose
        log.info("[*] %s: %d contactos (formato v%d, %d bytes/contacto, ip=%s)",
                 nodes_path, len(self.seeds), self.version, self.per, ip_order)

    def search(self, query, with_sources=False, enrich_top=25):
        """Busca 'query' y devuelve lista de SearchResult (ordenada por fuentes).
        with_sources=True hace una busqueda de fuentes reales por fichero (lento)."""
        cli = KadClient(ip_order=self.ip_order, verbose=self.verbose, timeout=self.timeout)
        try:
            pairs = cli.keyword_search(query, seeds=self.seeds,
                                       enrich_top=enrich_top, do_sources=with_sources)
            log.info("[*] Stats: %s", cli.stats)
            if cli.stats["res"] == 0 and cli.stats["boot_res"] == 0:
                log.info("[!] Ningun nodo respondio. Prueba ip_order='le' o un nodes.dat valido.")
                if cli.stats["encrypted"]:
                    log.info("    Llegaron %d paquetes no-Kad (posible ofuscacion/cifrado UDP).",
                             cli.stats["encrypted"])
            elif not pairs:
                log.info("[!] 0 resultados. La red respondio pero ningun nodo cercano indexa "
                         "esta keyword (quiza no este publicada). Prueba otra palabra.")
            return [SearchResult.from_tags(h, t) for h, t in pairs]
        finally:
            cli.close()
