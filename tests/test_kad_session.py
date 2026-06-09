"""Tests de KadSession: reutilización del pool de contactos e idle."""
import os

import amarr.ed2k as _ed2k_pkg
from amarr.ed2k.kad import KadClient
from amarr.kad_session import KadSession

# nodes.dat empaquetado (semillas reales para construir la sesión).
_NODES = os.path.join(os.path.dirname(_ed2k_pkg.__file__), "data", "nodes.dat")


def _contact(i):
    return {"id_int": i, "id": i.to_bytes(16, "big"), "ip": "1.2.3.4", "udp": 1, "tcp": 2}


def test_pool_accumulates_across_searches():
    seeds_seen = []

    def engine(query, seeds, with_sources):
        seeds_seen.append(len(seeds))
        # Descubre 3 contactos nuevos (ids que no están en nodes.dat).
        discovered = {i: _contact(i) for i in (10_000, 10_001, 10_002)}
        return discovered, []

    s = KadSession(_NODES, idle_seconds=600, search_engine=engine)
    s.search("euphoria")
    s.search("euphoria us")
    # La 2ª búsqueda parte de más semillas (nodes.dat + los 3 acumulados).
    assert seeds_seen[1] > seeds_seen[0]
    s.close()


def test_idle_clears_pool():
    def engine(query, seeds, with_sources):
        return {9999: _contact(9999)}, []

    s = KadSession(_NODES, idle_seconds=600, search_engine=engine)
    s.search("a")
    assert s._pool  # pool poblado
    s._idle_clear()
    assert not s._pool
    s.close()


def test_idle_zero_does_not_reuse_pool():
    def engine(query, seeds, with_sources):
        return {9999: _contact(9999)}, []

    s = KadSession(_NODES, idle_seconds=0, search_engine=engine)
    s.search("a")
    assert not s._pool  # con idle=0 el pool no se conserva entre búsquedas
    s.close()


def test_kadclient_exposes_contacts_attribute():
    cli = KadClient()
    try:
        assert hasattr(cli, "contacts") and cli.contacts == {}
    finally:
        cli.close()
