"""Tests de configuración: selección de motores y nivel de log."""
import logging

import pytest

from amarr.config import (
    search_backends,
    search_idle_timeout,
    set_log_level,
    setup_file_logging,
)


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


# --- search_idle_timeout ------------------------------------------------------


def test_search_idle_timeout_default_and_parsing():
    assert search_idle_timeout({}) == 600
    assert search_idle_timeout({"AMARR_SEARCH_IDLE_TIMEOUT": "0"}) == 0
    assert search_idle_timeout({"AMARR_SEARCH_IDLE_TIMEOUT": "1200"}) == 1200


def test_search_idle_timeout_rejects_invalid():
    with pytest.raises(ValueError):
        search_idle_timeout({"AMARR_SEARCH_IDLE_TIMEOUT": "x"})
    with pytest.raises(ValueError):
        search_idle_timeout({"AMARR_SEARCH_IDLE_TIMEOUT": "-5"})


# --- setup_file_logging -------------------------------------------------------


def test_setup_file_logging_disabled_without_env():
    assert setup_file_logging({}) is None


def test_setup_file_logging_writes_to_file(tmp_path):
    log_file = tmp_path / "amarr.log"
    set_log_level("DEBUG")
    handler = setup_file_logging({"AMARR_LOG_FILE": str(log_file)})
    try:
        assert handler is not None
        logging.getLogger("amarr").debug("hola fichero de log")
        handler.flush()
        assert log_file.exists()
        assert "hola fichero de log" in log_file.read_text(encoding="utf-8")
        # El log no se propaga a stdout (no satura Docker).
        assert logging.getLogger("amarr").propagate is False
        assert logging.getLogger("ed2k").propagate is False
    finally:
        for name in ("amarr", "ed2k"):
            lg = logging.getLogger(name)
            lg.removeHandler(handler)
            lg.propagate = True
        handler.close()
        set_log_level("INFO")
