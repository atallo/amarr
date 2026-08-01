"""Reading of environment variables and configuration (from ``App.kt``).

Centralizes access to environment variables and port validation, just like
the ``amarrPort``/``requiredEnv``/``optionalEnv`` functions in Kotlin.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import List, Mapping, Optional


def required_env(name: str, env: Optional[Mapping[str, str]] = None) -> str:
    """Returns the variable or raises if it is not set."""
    env = env if env is not None else os.environ
    value = env.get(name)
    if value is None:
        raise ValueError(f"{name} is not set")
    return value


def optional_env(
    name: str, default: str, env: Optional[Mapping[str, str]] = None
) -> str:
    env = env if env is not None else os.environ
    return env.get(name, default)


def amarr_port(env: Optional[Mapping[str, str]] = None) -> int:
    """Server port (AMARR_PORT, default 8080).

    Must be a valid integer between 1 and 65535, just like in the original.
    """
    env = env if env is not None else os.environ
    raw = env.get("AMARR_PORT", "8080")
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError("AMARR_PORT must be a valid port number") from exc
    if not 1 <= port <= 65535:
        raise ValueError("AMARR_PORT must be between 1 and 65535")
    return port


_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
}


def set_log_level(log_level: str) -> None:
    """Configures the log level of amarr and of the ed2k search library.

    Accepts DEBUG/INFO/WARN/ERROR. Besides the ``amarr`` logger, it adjusts the
    ``ed2k`` logger (and its children ``ed2k.server``/``ed2k.kad``), which does
    **not** hang off ``amarr``; this way, in DEBUG, the internal traces of the
    eD2k/Kad engines (connection, login, bootstrap, packets) are also visible,
    useful for debugging searches.
    """
    if log_level not in _LEVELS:
        raise ValueError(f"Unknown log level: {log_level}")
    level = _LEVELS[log_level]
    logging.getLogger("amarr").setLevel(level)
    logging.getLogger("ed2k").setLevel(level)


class _RotatingWatchedFileHandler(RotatingFileHandler):
    """``RotatingFileHandler`` that also **reopens** the file if it disappears or
    changes inode (you delete it by hand, an external logrotate rotates it, etc.).

    A normal ``RotatingFileHandler`` keeps the descriptor open: if you delete the
    file, on Linux it keeps writing to an already unnamed inode and nothing shows
    up on disk again until restart. Here it is checked before each
    write and reopened if needed, preserving size-based rotation.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._dev = 0
        self._ino = 0
        self._stat_stream()

    def _stat_stream(self) -> None:
        if self.stream is not None:
            try:
                st = os.fstat(self.stream.fileno())
                self._dev, self._ino = st.st_dev, st.st_ino
            except OSError:
                self._dev = self._ino = 0

    def _reopen_if_needed(self) -> None:
        try:
            st = os.stat(self.baseFilename)
        except OSError:
            st = None
        changed = st is None
        if st is not None and self._ino:
            changed = st.st_ino != self._ino or st.st_dev != self._dev
        if changed:
            if self.stream is not None:
                try:
                    self.stream.flush()
                    self.stream.close()
                except OSError:
                    pass
                self.stream = None
            self.stream = self._open()
            self._stat_stream()

    def emit(self, record) -> None:
        try:
            self._reopen_if_needed()
        except Exception:  # logging must never take down the request
            pass
        super().emit(record)


def setup_file_logging(env: Optional[Mapping[str, str]] = None):
    """Sends the ``amarr``/``ed2k`` log to a file on disk (with rotation) if
    ``AMARR_LOG_FILE`` is set, instead of to stdout — so that DEBUG mode does not
    flood the Docker log.

    Variables: ``AMARR_LOG_FILE`` (path; empty = disabled, log to stdout as
    always), ``AMARR_LOG_MAX_BYTES`` (default 5 MiB) and ``AMARR_LOG_BACKUPS`` (default 3).
    Returns the created handler, or ``None`` if disabled.
    """
    env = env if env is not None else os.environ
    log_file = env.get("AMARR_LOG_FILE", "")
    if not log_file:
        return None
    max_bytes = int(env.get("AMARR_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
    backups = int(env.get("AMARR_LOG_BACKUPS", "3"))
    directory = os.path.dirname(os.path.abspath(log_file))
    if directory:
        os.makedirs(directory, exist_ok=True)
    handler = _RotatingWatchedFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    for name in ("amarr", "ed2k"):
        logger = logging.getLogger(name)
        logger.addHandler(handler)
        # The log goes only to the file; it is not propagated to root (stdout/Docker).
        logger.propagate = False
    return handler


# --- search engines -----------------------------------------------------------

#: Valid search engines in canonical order.
SEARCH_BACKENDS = ("amule", "ed2k", "kad")
#: Accepted synonyms -> canonical name.
_BACKEND_ALIASES = {"emule": "amule"}


def cache_ttl(env: Optional[Mapping[str, str]] = None) -> int:
    """Search cache TTL in seconds (``AMARR_CACHE_TTL``, default 3600).

    ``0`` disables the cache. Must be an integer >= 0.
    """
    env = env if env is not None else os.environ
    raw = env.get("AMARR_CACHE_TTL", "3600")
    try:
        ttl = int(raw)
    except ValueError as exc:
        raise ValueError("AMARR_CACHE_TTL must be an integer (seconds)") from exc
    if ttl < 0:
        raise ValueError("AMARR_CACHE_TTL must be >= 0")
    return ttl


def search_idle_timeout(env: Optional[Mapping[str, str]] = None) -> int:
    """Seconds a search session is kept alive without activity
    (``AMARR_SEARCH_IDLE_TIMEOUT``, default 600).

    Applies to the persistent eD2k connection and the Kad contact pool. ``0``
    disables persistence (connect/discard on each search). Integer >= 0.
    """
    env = env if env is not None else os.environ
    raw = env.get("AMARR_SEARCH_IDLE_TIMEOUT", "600")
    try:
        secs = int(raw)
    except ValueError as exc:
        raise ValueError(
            "AMARR_SEARCH_IDLE_TIMEOUT must be an integer (seconds)"
        ) from exc
    if secs < 0:
        raise ValueError("AMARR_SEARCH_IDLE_TIMEOUT must be >= 0")
    return secs


def search_backends(env: Optional[Mapping[str, str]] = None) -> List[str]:
    """Active search engines (``AMARR_SEARCH_BACKENDS``, comma-separated list).

    Accepts ``amule`` (through an external aMule), ``ed2k`` (eD2k server) and
    ``kad`` (Kad network); ``emule`` is an alias of ``amule``. Defaults to ``amule``
    (same behavior as before). Returns the canonical list without duplicates and
    in order of appearance. Raises if any value is invalid or the list is empty.
    """
    env = env if env is not None else os.environ
    raw = env.get("AMARR_SEARCH_BACKENDS", "amule")
    result: List[str] = []
    for token in raw.split(","):
        name = token.strip().lower()
        if not name:
            continue
        name = _BACKEND_ALIASES.get(name, name)
        if name not in SEARCH_BACKENDS:
            raise ValueError(
                f"Unknown search backend: {token.strip()!r} "
                f"(valid: {', '.join(SEARCH_BACKENDS)})"
            )
        if name not in result:
            result.append(name)
    if not result:
        raise ValueError("AMARR_SEARCH_BACKENDS must list at least one backend")
    return result
