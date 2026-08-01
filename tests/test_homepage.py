"""Home page tests (GET /): lists only the active engines."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amarr.homepage import build_home_router

from .helpers import FakeAmuleClient, MemoryCategoryStore


def _client(backends):
    app = FastAPI()
    app.include_router(build_home_router(backends))
    return TestClient(app)


def test_home_is_responsive_html():
    r = _client(["amule"]).get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'name="viewport"' in r.text  # responsive (mobile + desktop)


def test_home_lists_only_active_backends():
    body = _client(["amule", "ed2k"]).get("/").text
    assert "/indexer/amule/api" in body
    assert "/indexer/ed2k/api" in body
    assert "/indexer/all/api" in body  # aggregator whenever there is at least one
    # Inactive engines are not shown.
    assert "/indexer/kad/api" not in body


def test_home_kad_only():
    body = _client(["kad"]).get("/").text
    assert "/indexer/kad/api" in body
    assert "/indexer/all/api" in body
    assert "/indexer/amule/api" not in body
    assert "/indexer/ed2k/api" not in body


def test_home_has_usage_example():
    body = _client(["ed2k"]).get("/").text
    assert "GET /indexer/ed2k/api?t=search" in body  # example request
    assert "&lt;rss" in body  # escaped XML response inside <pre>


def test_home_no_active_backends_is_graceful():
    body = _client([]).get("/").text
    assert "No active search engines" in body
    assert "/indexer/all/api" not in body


def test_details_page_shows_ed2k_and_magnet():
    app = FastAPI()
    app.include_router(build_home_router(["amule"]))
    c = TestClient(app)
    h = bytes(range(16)).hex()
    r = c.get(
        "/details",
        params={
            "hash": h,
            "name": "Ubuntu 24.04.mkv",
            "size": 2000,
            "seeders": 5,
            "peers": 9,
        },
    )
    assert r.status_code == 200
    assert f"ed2k://|file|Ubuntu 24.04.mkv|2000|{h}" in r.text  # eD2k link
    assert f"magnet:?xt=urn:ed2k:{h.upper()}" in r.text  # real eD2k magnet
    assert "urn:btih:" in r.text  # Fake Magnet Amarr (synthetic)
    assert "Fake Magnet Amarr" in r.text
    assert "Ubuntu 24.04.mkv" in r.text


def test_home_mounted_in_create_app():
    from amarr.app import create_app
    from amarr.torznab.indexer.amule import AmuleIndexer

    amule = FakeAmuleClient()
    app = create_app(
        amule, MemoryCategoryStore(), "/finished", {"amule": AmuleIndexer(amule)}
    )
    r = TestClient(app, raise_server_exceptions=False).get("/")
    assert r.status_code == 200
    assert "/indexer/amule/api" in r.text


def test_home_documents_qbittorrent_and_legacy():
    body = _client(["amule"]).get("/").text
    assert "Also responds at" in body  # legacy /api endpoint
    assert "/api/v2/torrents/add" in body  # qBittorrent section
    assert "/api/v2/torrents/info" in body
    assert "/status" in body
    assert "/openapi.json" in body


def test_home_documents_all_served_qbittorrent_routes():
    # The home page must not fall behind the real /api/v2/* routes.
    from amarr.app import create_app
    from amarr.torznab.indexer.amule import AmuleIndexer

    amule = FakeAmuleClient()
    app = create_app(
        amule, MemoryCategoryStore(), "/finished", {"amule": AmuleIndexer(amule)}
    )
    body = TestClient(app, raise_server_exceptions=False).get("/").text
    qbit_paths = sorted(
        {r.path for r in app.routes if getattr(r, "path", "").startswith("/api/v2/")}
    )
    assert qbit_paths, "no /api/v2/* routes were found mounted"
    for path in qbit_paths:
        assert path in body, f"endpoint served but not documented on the home page: {path}"


def test_home_has_examples_for_every_endpoint_kind():
    body = _client(["amule"]).get("/").text
    assert "<details>" in body          # collapsible examples
    assert "urls=magnet" in body        # POST /torrents/add example
    assert "2.8.19" in body             # /app/webapiVersion response
    assert "hashes=" in body            # POST /torrents/delete example
    assert "ed2kConnected" in body      # /status example
    # One <details> per: 10 qBittorrent + 1 /status + (amule + all) Torznab.
    assert body.count("<details>") >= 13
