"""Tests de la página de inicio (GET /): lista solo los motores activos."""
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
    assert 'name="viewport"' in r.text  # responsive (móvil + PC)


def test_home_lists_only_active_backends():
    body = _client(["amule", "ed2k"]).get("/").text
    assert "/indexer/amule/api" in body
    assert "/indexer/ed2k/api" in body
    assert "/indexer/all/api" in body  # agregador siempre que haya alguno
    # Los motores no activos no se muestran.
    assert "/indexer/kad/api" not in body


def test_home_kad_only():
    body = _client(["kad"]).get("/").text
    assert "/indexer/kad/api" in body
    assert "/indexer/all/api" in body
    assert "/indexer/amule/api" not in body
    assert "/indexer/ed2k/api" not in body


def test_home_has_usage_example():
    body = _client(["ed2k"]).get("/").text
    assert "GET /indexer/ed2k/api?t=search" in body  # request de ejemplo
    assert "&lt;rss" in body  # respuesta XML escapada dentro de <pre>


def test_home_no_active_backends_is_graceful():
    body = _client([]).get("/").text
    assert "No hay motores" in body
    assert "/indexer/all/api" not in body


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
    assert "También responde en" in body  # endpoint /api heredado
    assert "/api/v2/torrents/add" in body  # sección qBittorrent
    assert "/api/v2/torrents/info" in body
    assert "/status" in body
    assert "/openapi.json" in body


def test_home_documents_all_served_qbittorrent_routes():
    # La home no debe quedarse atrás respecto a las rutas /api/v2/* reales.
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
    assert qbit_paths, "no se encontraron rutas /api/v2/* montadas"
    for path in qbit_paths:
        assert path in body, f"endpoint servido pero no documentado en la home: {path}"


def test_home_has_examples_for_every_endpoint_kind():
    body = _client(["amule"]).get("/").text
    assert "<details>" in body          # ejemplos plegables
    assert "urls=magnet" in body        # ejemplo de POST /torrents/add
    assert "2.8.19" in body             # respuesta de /app/webapiVersion
    assert "hashes=" in body            # ejemplo de POST /torrents/delete
    assert "ed2kConnected" in body      # ejemplo de /status
    # Un <details> por: 10 qBittorrent + 1 /status + (amule + all) Torznab.
    assert body.count("<details>") >= 13
