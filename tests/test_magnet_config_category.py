"""Tests de MagnetLink, validación de puerto y almacén de categorías (SQLite)."""
import os

import pytest

from amarr.category.store import SqliteCategoryStore
from amarr.config import amarr_port
from amarr.magnet import AMARR_TRACKER, MagnetLink
from amarr.torrent.models import Category


# --- MagnetLink ---------------------------------------------------------------


def test_parse_sample_ed2k():
    ed2k = (
        "ed2k://|file|Dj%20Matrix%20&%20Matt%20Joe%20-%20Musica%20da%20giostra,"
        "%20Vol.%2010%20(2023).rar|152488462|0320C47B3BAA01F8D5F42CD7C05CE28D"
        "|h=O74TQQWUVF24E7WD25UD57Z45GHIDLZZ|/"
    )
    parsed = MagnetLink.from_ed2k(ed2k)
    assert parsed.is_amarr()
    assert parsed.name == "Dj Matrix & Matt Joe - Musica da giostra, Vol. 10 (2023).rar"
    assert parsed.size == 152488462
    assert parsed.amule_hex_hash().upper() == "0320C47B3BAA01F8D5F42CD7C05CE28D"


def test_create_and_parse_roundtrip():
    h = os.urandom(20)
    magnet = MagnetLink.for_amarr(h, "Some Movie (2024) & more", 999999999999)
    parsed = MagnetLink.from_string(str(magnet))
    assert parsed == magnet
    assert parsed.is_amarr()
    assert len(parsed.amule_hex_hash()) == 32
    assert AMARR_TRACKER in parsed.trackers


# --- config: amarr_port -------------------------------------------------------


def test_port_defaults_to_8080():
    assert amarr_port({}) == 8080


def test_port_read_from_env():
    assert amarr_port({"AMARR_PORT": "9090"}) == 9090


def test_port_rejects_non_integer():
    with pytest.raises(ValueError):
        amarr_port({"AMARR_PORT": "not-a-port"})


def test_port_rejects_out_of_range():
    with pytest.raises(ValueError):
        amarr_port({"AMARR_PORT": "70000"})


# --- SqliteCategoryStore ------------------------------------------------------


def test_store_and_get_category(tmp_path):
    store = SqliteCategoryStore(str(tmp_path))
    store.store("movies", "abc123")
    assert store.get_category("abc123") == "movies"


def test_creates_db_file(tmp_path):
    SqliteCategoryStore(str(tmp_path))
    assert (tmp_path / "amarr.db").exists()


def test_get_category_persists_across_instances(tmp_path):
    SqliteCategoryStore(str(tmp_path)).store("tv", "deadbeef")
    # Una instancia nueva (misma BD en disco) debe ver el dato.
    fresh = SqliteCategoryStore(str(tmp_path))
    assert fresh.get_category("deadbeef") == "tv"


def test_get_category_unknown_returns_none(tmp_path):
    assert SqliteCategoryStore(str(tmp_path)).get_category("nope") is None


def test_delete_category(tmp_path):
    store = SqliteCategoryStore(str(tmp_path))
    store.store("movies", "abc")
    store.delete("abc")
    assert store.get_category("abc") is None


def test_store_upserts_same_hash(tmp_path):
    store = SqliteCategoryStore(str(tmp_path))
    store.store("a", "h1")
    store.store("b", "h1")  # mismo hash -> reemplaza
    assert store.get_category("h1") == "b"


def test_add_and_get_categories(tmp_path):
    store = SqliteCategoryStore(str(tmp_path))
    store.add_category(Category("movies", "/movies"))
    assert Category("movies", "/movies") in store.get_categories()


def test_legacy_tsv_archived_not_imported(tmp_path):
    # Instalación previa con TSV: al arrancar con SQLite se aparta sin importar.
    (tmp_path / "categories.tsv").write_text("movies\t/movies\n", encoding="utf-8")
    (tmp_path / "hashes.tsv").write_text("abc\tmovies\n", encoding="utf-8")

    store = SqliteCategoryStore(str(tmp_path))

    # Datos NO importados (se empieza con la BD vacía).
    assert store.get_category("abc") is None
    assert store.get_categories() == set()
    # Los .tsv se apartan a .bak (respaldo).
    assert not (tmp_path / "categories.tsv").exists()
    assert not (tmp_path / "hashes.tsv").exists()
    assert (tmp_path / "categories.tsv.bak").exists()
    assert (tmp_path / "hashes.tsv.bak").exists()
