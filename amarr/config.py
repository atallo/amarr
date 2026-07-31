"""Lectura de variables de entorno y configuración (de ``App.kt``).

Centraliza el acceso a variables de entorno y la validación del puerto, igual
que las funciones ``amarrPort``/``requiredEnv``/``optionalEnv`` de Kotlin.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import List, Mapping, Optional


def required_env(name: str, env: Optional[Mapping[str, str]] = None) -> str:
    """Devuelve la variable o lanza si no está definida."""
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
    """Puerto del servidor (AMARR_PORT, por defecto 8080).

    Debe ser un entero válido entre 1 y 65535, igual que en el original.
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
    """Configura el nivel de log de amarr y de la librería de búsqueda ed2k.

    Acepta DEBUG/INFO/WARN/ERROR. Además del logger ``amarr``, ajusta el logger
    ``ed2k`` (y sus hijos ``ed2k.server``/``ed2k.kad``), que **no** cuelga de
    ``amarr``; así, en DEBUG, se ven también las trazas internas de los motores
    eD2k/Kad (conexión, login, bootstrap, paquetes), útiles para depurar búsquedas.
    """
    if log_level not in _LEVELS:
        raise ValueError(f"Unknown log level: {log_level}")
    level = _LEVELS[log_level]
    logging.getLogger("amarr").setLevel(level)
    logging.getLogger("ed2k").setLevel(level)


class _RotatingWatchedFileHandler(RotatingFileHandler):
    """``RotatingFileHandler`` que además **reabre** el fichero si desaparece o
    cambia de inodo (lo borras a mano, lo rota un logrotate externo, etc.).

    Un ``RotatingFileHandler`` normal mantiene el descriptor abierto: si borras el
    fichero, en Linux sigue escribiendo a un inodo ya sin nombre y no vuelve a
    aparecer nada en disco hasta reiniciar. Aquí se comprueba antes de cada
    escritura y se reabre si hace falta, conservando la rotación por tamaño.
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
        except Exception:  # el logging nunca debe tumbar la petición
            pass
        super().emit(record)


def setup_file_logging(env: Optional[Mapping[str, str]] = None):
    """Envía el log de ``amarr``/``ed2k`` a un fichero en disco (con rotación) si
    ``AMARR_LOG_FILE`` está definido, en lugar de a stdout — así el modo DEBUG no
    satura el log de Docker.

    Variables: ``AMARR_LOG_FILE`` (ruta; vacío = desactivado, log a stdout como
    siempre), ``AMARR_LOG_MAX_BYTES`` (def. 5 MiB) y ``AMARR_LOG_BACKUPS`` (def. 3).
    Devuelve el handler creado, o ``None`` si está desactivado.
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
        # El log va solo al fichero; no se propaga al root (stdout/Docker).
        logger.propagate = False
    return handler


# --- motores de búsqueda ------------------------------------------------------

#: Motores de búsqueda válidos en orden canónico.
SEARCH_BACKENDS = ("amule", "ed2k", "kad")
#: Sinónimos aceptados -> nombre canónico.
_BACKEND_ALIASES = {"emule": "amule"}


def cache_ttl(env: Optional[Mapping[str, str]] = None) -> int:
    """TTL de la caché de búsquedas en segundos (``AMARR_CACHE_TTL``, def. 3600).

    ``0`` desactiva la caché. Debe ser un entero >= 0.
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
    """Segundos que una sesión de búsqueda se mantiene viva sin actividad
    (``AMARR_SEARCH_IDLE_TIMEOUT``, def. 600).

    Aplica a la conexión persistente eD2k y al pool de contactos de Kad. ``0``
    desactiva la persistencia (conectar/descartar en cada búsqueda). Entero >= 0.
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
    """Motores de búsqueda activos (``AMARR_SEARCH_BACKENDS``, lista por comas).

    Acepta ``amule`` (a través de un aMule externo), ``ed2k`` (servidor eD2k) y
    ``kad`` (red Kad); ``emule`` es alias de ``amule``. Por defecto ``amule``
    (mismo comportamiento que antes). Devuelve la lista canónica sin duplicados y
    en orden de aparición. Lanza si algún valor es inválido o la lista es vacía.
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
