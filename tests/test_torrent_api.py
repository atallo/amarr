"""Tests de la API qBittorrent (portado de ``TorrentApiTest.kt``)."""
import json

from fastapi.testclient import TestClient

from amarr.jamule.model import DownloadCommand
from amarr.magnet import MagnetLink
from amarr.torrent.api import build_torrent_router
from fastapi import FastAPI

from .helpers import FakeAmuleClient, MemoryCategoryStore, make_part_file

_HASH = bytes(range(16))
_MAGNET = MagnetLink.for_amarr(_HASH, "test", 1)
_FINISHED = "/finished"


def _client(amule, store):
    app = FastAPI()
    app.include_router(build_torrent_router(amule, store, _FINISHED))
    return TestClient(app, raise_server_exceptions=False)


def test_get_preferences():
    c = _client(FakeAmuleClient(), MemoryCategoryStore())
    r = c.get("/api/v2/app/preferences")
    assert r.status_code == 200
    assert r.json()["save_path"] == _FINISHED


def test_get_api_version():
    c = _client(FakeAmuleClient(), MemoryCategoryStore())
    r = c.get("/api/v2/app/webapiVersion")
    assert r.status_code == 200
    assert r.text == "2.8.19"


def test_allow_login():
    c = _client(FakeAmuleClient(), MemoryCategoryStore())
    r = c.post("/api/v2/auth/login", data={"username": "test", "password": "test"})
    assert r.status_code == 200
    assert r.text == "Ok."


def test_add_torrent():
    amule = FakeAmuleClient()
    c = _client(amule, MemoryCategoryStore())
    r = c.post(
        "/api/v2/torrents/add",
        data={"urls": str(_MAGNET), "category": "test", "paused": "test"},
    )
    assert r.status_code == 200
    assert amule.downloaded_links == [_MAGNET.to_ed2k_link()]


def test_get_categories():
    c = _client(FakeAmuleClient(), MemoryCategoryStore())
    r = c.get("/api/v2/torrents/categories")
    assert r.status_code == 200


def test_create_category():
    store = MemoryCategoryStore()
    c = _client(FakeAmuleClient(), store)
    r = c.post(
        "/api/v2/torrents/createCategory",
        data={"category": "test", "savePath": "test"},
    )
    assert r.status_code == 200
    assert any(cat.name == "test" for cat in store.get_categories())


def test_delete_torrent_when_downloading():
    amule = FakeAmuleClient()
    store = MemoryCategoryStore()
    store.store("test", _MAGNET.amule_hex_hash())
    amule.download_queue = [
        make_part_file(
            file_hash_hex_string=_MAGNET.amule_hex_hash(),
            file_name=_MAGNET.name,
            size_full=_MAGNET.size,
        )
    ]
    c = _client(amule, store)
    r = c.post(
        "/api/v2/torrents/delete",
        data={"hashes": _MAGNET.amule_hex_hash(), "deleteFiles": "true"},
    )
    assert r.status_code == 200
    assert (_HASH, DownloadCommand.DELETE) in amule.delete_commands
    assert store.get_category(_MAGNET.amule_hex_hash()) is None


def test_delete_file_when_not_downloading(tmp_path):
    amule = FakeAmuleClient()
    store = MemoryCategoryStore()
    store.store("test", _MAGNET.amule_hex_hash())
    temp_file = tmp_path / "shared.bin"
    temp_file.write_text("data")
    amule.shared_files = [
        make_part_file(
            file_hash_hex_string=_MAGNET.amule_hex_hash(),
            file_name=_MAGNET.name,
            size_full=_MAGNET.size,
            file_path=str(temp_file),
        )
    ]
    amule.download_queue = []
    c = _client(amule, store)
    r = c.post(
        "/api/v2/torrents/delete",
        data={"hashes": _MAGNET.amule_hex_hash(), "deleteFiles": "true"},
    )
    assert r.status_code == 200
    assert (_HASH, DownloadCommand.DELETE) not in amule.delete_commands
    assert store.get_category(_MAGNET.amule_hex_hash()) is None
    assert not temp_file.exists()


def test_get_files():
    amule = FakeAmuleClient()
    amule.download_queue = [
        make_part_file(
            file_hash_hex_string=_MAGNET.amule_hex_hash(),
            file_name=_MAGNET.name,
            size_full=_MAGNET.size,
        )
    ]
    c = _client(amule, MemoryCategoryStore())
    r = c.get("/api/v2/torrents/files", params={"hash": _MAGNET.amule_hex_hash()})
    assert r.status_code == 200
    assert r.json()[0]["name"] == _MAGNET.name


def test_get_info_serializes_ratio_and_seeding_time():
    amule = FakeAmuleClient()
    amule.download_queue = [
        make_part_file(
            file_hash_hex_string=_MAGNET.amule_hex_hash(),
            file_name=_MAGNET.name,
            size_full=_MAGNET.size,
        )
    ]
    c = _client(amule, MemoryCategoryStore())
    r = c.get("/api/v2/torrents/info")
    assert r.status_code == 200
    torrent = r.json()[0]
    # kotlinx serializaba ratio (Double) como "1.0" y seeding_time (Int) como "1".
    assert torrent["ratio"] == 1.0
    assert torrent["seeding_time"] == 1


def test_get_info_handles_zero_size_without_crashing():
    """Regresión: un part-file con size_full=0 no debe provocar un 500.

    Antes se calculaba progress = size_done / size_full sin proteger el cero.
    """
    amule = FakeAmuleClient()
    amule.download_queue = [
        make_part_file(
            file_hash_hex_string=_MAGNET.amule_hex_hash(),
            file_name=_MAGNET.name,
            size_full=0,
            size_done=0,
        )
    ]
    c = _client(amule, MemoryCategoryStore())
    r = c.get("/api/v2/torrents/info")
    assert r.status_code == 200
    assert r.json()[0]["progress"] == 0.0


def test_get_properties():
    amule = FakeAmuleClient()
    amule.download_queue = [
        make_part_file(
            file_hash_hex_string=_MAGNET.amule_hex_hash(),
            file_name=_MAGNET.name,
            size_full=_MAGNET.size,
        )
    ]
    c = _client(amule, MemoryCategoryStore())
    r = c.get("/api/v2/torrents/properties", params={"hash": _MAGNET.amule_hex_hash()})
    assert r.status_code == 200
    assert r.json()["seeding_time"] == 1
