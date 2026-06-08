"""Tests de configuración: selección de motores y nivel de log."""
import logging

import pytest

from amarr.config import search_backends, set_log_level


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


# --- set_log_level ------------------------------------------------------------


def test_set_log_level_configures_amarr_and_ed2k_loggers():
    try:
        set_log_level("DEBUG")
        assert logging.getLogger("amarr").level == logging.DEBUG
        # La librería de búsqueda ed2k/kad también, para ver sus trazas.
        assert logging.getLogger("ed2k").level == logging.DEBUG
    finally:
        set_log_level("INFO")  # restaura para no afectar a otros tests


def test_set_log_level_rejects_unknown():
    with pytest.raises(ValueError):
        set_log_level("VERBOSE")
