"""Tests de la API Torznab (portado de ``TorznabApiTest.kt``)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amarr.torznab.api import build_torznab_router
from amarr.torznab.indexer.amule import AmuleIndexer

from .helpers import FakeAmuleClient, make_search_file

_HASH = bytes(range(16))


def _client(amule=None):
    amule = amule or FakeAmuleClient()
    indexer = AmuleIndexer(amule)
    app = FastAPI()
    app.include_router(build_torznab_router(indexer))
    return TestClient(app, raise_server_exceptions=False), amule


def test_missing_action_returns_500():
    c, _ = _client()
    assert c.get("/api").status_code == 500


def test_unknown_action_returns_500():
    c, _ = _client()
    assert c.get("/api?t=unknown").status_code == 500


def test_caps_request():
    c, _ = _client()
    r = c.get("/api?t=caps")
    assert r.status_code == 200
    assert "<caps>" in r.text


def test_search_passes_params_to_indexer():
    c, amule = _client()
    amule.search_files = [make_search_file("test.mkv", _HASH)]
    r = c.get("/api?t=search&q=test&offset=0&limit=100")
    assert r.status_code == 200
    assert amule.last_query == "test"


def test_tv_search_without_season_is_plain():
    c, amule = _client()
    amule.search_files = []
    r = c.get("/api?t=tvsearch&q=show&offset=0&limit=100")
    assert r.status_code == 200
    assert amule.last_query == "show"


def test_tv_search_expands_episode_formats():
    c, amule = _client()
    amule.search_files = []
    # Registra cada query que recibe el cliente.
    queries = []
    original = amule.search_sync

    def record(query, *a, **k):
        queries.append(query)
        return original(query, *a, **k)

    amule.search_sync = record
    r = c.get("/api?t=tvsearch&q=show&season=1&episode=2&offset=0&limit=100")
    assert r.status_code == 200
    # El indexador normaliza la query antes de buscar (sin signos extra aquí).
    assert "show S01E02" in queries
    assert "show 1x02" in queries
    assert "show 102" in queries
