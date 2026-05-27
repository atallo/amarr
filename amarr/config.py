"""Lectura de variables de entorno y configuración (de ``App.kt``).

Centraliza el acceso a variables de entorno y la validación del puerto, igual
que las funciones ``amarrPort``/``requiredEnv``/``optionalEnv`` de Kotlin.
"""
from __future__ import annotations

import logging
import os
from typing import Mapping, Optional


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
    """Configura el nivel del logger raíz de amarr.

    Acepta DEBUG/INFO/WARN/ERROR (igual que el mapeo logback del original).
    """
    if log_level not in _LEVELS:
        raise ValueError(f"Unknown log level: {log_level}")
    logging.getLogger("amarr").setLevel(_LEVELS[log_level])
