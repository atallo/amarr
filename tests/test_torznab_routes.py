"""Tests del montaje de rutas Torznab según los motores activos."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amarr.ed2k import SearchResult
from amarr.torznab.api import build_torznab_router
from amarr.torznab.indexer.amule import AmuleIndexer
from amarr.torznab.indexer.ed2k_server import Ed2kServerIndexer

from .helpers import FakeAmuleClient


def _client(indexers):
    app = FastAPI()
    app.include_router(build_torznab_router(indexers))
    return TestClient(app, raise_server_exceptions=False)


def test_active_engines_have_endpoints_inactive_404():
    c = _client(
        {
            "amule": AmuleIndexer(FakeAmuleClient()),
            "ed2k": Ed2kServerIndexer(search_fn=lambda q: []),
        }
    )
    assert c.get("/indexer/amule/api?t=caps").status_code == 200
    assert c.get("/indexer/ed2k/api?t=caps").status_code == 200
    assert c.get("/indexer/all/api?t=caps").status_code == 200
    assert c.get("/api?t=caps").status_code == 200  # legacy
    assert c.get("/indexer/kad/api?t=caps").status_code == 404  # no activo


def test_all_endpoint_aggregates_active_engines():
    h1, h2 = bytes(range(16)), bytes(range(16, 32))

    def mk(name, h):
        return SearchResult(
            file_hash=h, name=name, raw_name=name, size=1000,
            sources=1, complete_sources=1,
        )

    e1 = Ed2kServerIndexer(search_fn=lambda q: [mk("alpha.mkv", h1)])
    e2 = Ed2kServerIndexer(search_fn=lambda q: [mk("beta.mkv", h2)])
    c = _client({"ed2k": e1, "kad": e2})
    r = c.get("/indexer/all/api?t=search&q=x")
    assert r.status_code == 200
    assert "alpha.mkv" in r.text and "beta.mkv" in r.text


def test_legacy_api_falls_back_to_aggregate_without_amule():
    c = _client({"ed2k": Ed2kServerIndexer(search_fn=lambda q: [])})
    assert c.get("/api?t=caps").status_code == 200
