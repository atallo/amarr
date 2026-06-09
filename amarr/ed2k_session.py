"""Sesión TCP persistente con un servidor eD2k.

Mantiene una única conexión (login **una sola vez**) y la reutiliza entre
búsquedas, en lugar de conectar/loguear/cerrar por cada consulta — ese login
repetido es lo que los servidores eD2k penalizan como abuso. Tras
``idle_seconds`` sin búsquedas la conexión se cierra; la siguiente búsqueda
reconecta. También reconecta si el servidor corta la conexión inactiva.

Reutiliza las primitivas de la librería (``Ed2kConnection``,
``parse_search_result``, ``filter_by_query``, ``SearchResult``). Las búsquedas se
serializan con un cerrojo: una conexión eD2k no admite consultas concurrentes.
"""
from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Callable, List, Optional

from .ed2k import DEFAULT_SERVER, SearchResult, filter_by_query
from .ed2k.server import (
    OP_IDCHANGE,
    OP_REJECT,
    OP_SEARCHRESULT,
    Ed2kConnection,
    parse_search_result,
    pick_random_port,
)

_log = logging.getLogger("ed2k.server")

ConnFactory = Callable[[], Ed2kConnection]


class Ed2kServerSession:
    """Conexión eD2k persistente y reutilizable, con cierre por inactividad."""

    def __init__(
        self,
        server: str = DEFAULT_SERVER,
        timeout: float = 15.0,
        idle_seconds: int = 600,
        nick: str = "hydra",
        conn_factory: Optional[ConnFactory] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        host, _, port = server.partition(":")
        self._host = host
        self._port = int(port or "4661")
        self._timeout = timeout
        self._idle = idle_seconds
        self._nick = nick
        self._conn_factory = conn_factory or self._default_factory
        self._log = logger or _log
        self._lock = threading.RLock()
        self._conn: Optional[Ed2kConnection] = None
        self._timer: Optional[threading.Timer] = None

    def _default_factory(self) -> Ed2kConnection:
        return Ed2kConnection(self._host, self._port, timeout=self._timeout)

    # --- API pública --------------------------------------------------------

    def search(self, query: str) -> List[SearchResult]:
        with self._lock:
            self._cancel_timer()
            try:
                pairs = self._search_once(query)
            except (OSError, ConnectionError):
                # El servidor pudo cortar la conexión inactiva: reconectar 1 vez.
                self._log.info("[*] Conexión eD2k caída; reconectando...")
                self._close_conn()
                try:
                    pairs = self._search_once(query)
                except (OSError, ConnectionError):
                    self._close_conn()
                    raise
            self._after_search()
            pairs = filter_by_query(pairs, query)
            return [SearchResult.from_tags(h, t) for h, t in pairs]

    def close(self) -> None:
        with self._lock:
            self._cancel_timer()
            self._close_conn()

    # --- internos -----------------------------------------------------------

    def _search_once(self, query: str) -> list:
        self._ensure_connected()
        assert self._conn is not None
        self._conn.search(query)
        return self._await_results(self._conn)

    def _ensure_connected(self) -> None:
        if self._conn is not None:
            return
        self._log.info(
            "[*] Conectando a %s:%d (sesión persistente)...", self._host, self._port
        )
        conn = self._conn_factory()
        conn.login(nick=self._nick, client_port=pick_random_port())
        self._await_login(conn)
        self._conn = conn

    def _await_login(self, conn: Ed2kConnection) -> None:
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            try:
                op, _payload = conn.recv_packet()
            except socket.timeout:
                break
            if op == OP_IDCHANGE:
                self._log.info("[*] Login OK (sesión persistente).")
                return
            if op == OP_REJECT:
                raise ConnectionError("El servidor rechazó la conexión")
            # OP_SERVERMESSAGE / OP_SERVERSTATUS y demás: se ignoran.
        self._log.info("[!] No llegó IDCHANGE; intento buscar de todos modos.")

    def _await_results(self, conn: Ed2kConnection) -> list:
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            try:
                op, payload = conn.recv_packet()
            except socket.timeout:
                break
            if op == OP_SEARCHRESULT:
                return parse_search_result(payload)
            # OP_SERVERMESSAGE y demás: se ignoran.
        self._log.info("[!] No llegaron resultados (timeout).")
        return []

    def _after_search(self) -> None:
        # idle > 0: mantener viva y programar cierre por inactividad.
        # idle <= 0: cerrar ya (un connect/login por búsqueda, sin persistencia).
        if self._idle and self._idle > 0:
            self._schedule_timer()
        else:
            self._close_conn()

    def _schedule_timer(self) -> None:
        self._timer = threading.Timer(self._idle, self._idle_close)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _idle_close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._log.info(
                    "[*] Cerrando conexión eD2k inactiva (%ds sin búsquedas).",
                    self._idle,
                )
            self._close_conn()

    def _close_conn(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
