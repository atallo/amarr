"""Lectura de variables de entorno y configuración (de ``App.kt``).

Centraliza el acceso a variables de entorno y la validación del puerto, igual
que las funciones ``amarrPort``/``requiredEnv``/``optionalEnv`` de Kotlin.
"""
from __future__ import annotations

import logging
import os
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


# --- motores de búsqueda ------------------------------------------------------

#: Motores de búsqueda válidos en orden canónico.
SEARCH_BACKENDS = ("amule", "ed2k", "kad")
#: Sinónimos aceptados -> nombre canónico.
_BACKEND_ALIASES = {"emule": "amule"}


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
