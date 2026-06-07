"""Tests de MagnetLink, validación de puerto y almacén de categorías."""
import os

import pytest

from amarr.category.store import FileCategoryStore
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


# --- FileCategoryStore --------------------------------------------------------


def test_store_and_get_category(tmp_path):
    store = FileCategoryStore(str(tmp_path))
    store.store("movies", "abc123")
    assert store.get_category("abc123") == "movies"


def test_get_category_reads_from_disk(tmp_path):
    store = FileCategoryStore(str(tmp_path))
    store.store("tv", "deadbeef")
    # Una instancia nueva (caché vacía) debe leer del fichero.
    fresh = FileCategoryStore(str(tmp_path))
    assert fresh.get_category("deadbeef") == "tv"


def test_delete_category(tmp_path):
    store = FileCategoryStore(str(tmp_path))
    store.store("movies", "abc")
    store.delete("abc")
    assert store.get_category("abc") is None


def test_delete_then_store_survives_reload(tmp_path):
    """Regresión: borrar y volver a añadir no debe corromper el fichero.

    El delete reescribía sin salto de línea final, así que el siguiente store
    se pegaba a la última entrada; tras reiniciar (caché fría) una categoría se
    leía mal y otra se perdía.
    """
    store = FileCategoryStore(str(tmp_path))
    store.store("cat1", "AAAA")
    store.store("cat2", "BBBB")
    store.store("cat3", "CCCC")
    store.delete("BBBB")
    store.store("cat4", "DDDD")

    # Instancia nueva => caché vacía => se lee del disco.
    fresh = FileCategoryStore(str(tmp_path))
    assert fresh.get_category("AAAA") == "cat1"
    assert fresh.get_category("CCCC") == "cat3"
    assert fresh.get_category("DDDD") == "cat4"
    assert fresh.get_category("BBBB") is None


def test_rejects_tab_characters(tmp_path):
    store = FileCategoryStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.store("bad\tname", "hash")


def test_add_and_get_categories(tmp_path):
    store = FileCategoryStore(str(tmp_path))
    store.add_category(Category("movies", "/movies"))
    cats = store.get_categories()
    assert Category("movies", "/movies") in cats
