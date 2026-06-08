"""Tests de ``config.search_backends`` (selección de motores de búsqueda)."""
import pytest

from amarr.config import search_backends


def test_default_is_amule():
    assert search_backends({}) == ["amule"]


def test_parses_comma_list():
    assert search_backends({"AMARR_SEARCH_BACKENDS": "amule,ed2k,kad"}) == [
        "amule",
        "ed2k",
        "kad",
    ]


def test_emule_alias_dedup_and_whitespace():
    # 'emule' es alias de 'amule'; se recortan espacios y se eliminan duplicados.
    assert search_backends({"AMARR_SEARCH_BACKENDS": " emule , ed2k , amule "}) == [
        "amule",
        "ed2k",
    ]


def test_invalid_backend_raises():
    with pytest.raises(ValueError):
        search_backends({"AMARR_SEARCH_BACKENDS": "amule,foo"})


def test_empty_list_raises():
    with pytest.raises(ValueError):
        search_backends({"AMARR_SEARCH_BACKENDS": " , "})
