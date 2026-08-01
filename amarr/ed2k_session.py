"""Persistent TCP session with an eD2k server.

Keeps a single connection (login **only once**) and reuses it between
searches, instead of connecting/logging in/closing for each query — that
repeated login is what eD2k servers penalize as abuse. After
``idle_seconds`` without searches the connection is closed; the next search
reconnects. It also reconnects if the server drops the idle connection.

Reuses the library primitives (``Ed2kConnection``,
``parse_search_result``, ``filter_by_query``, ``SearchResult``). Searches are
serialized with a lock: an eD2k connection does not allow concurrent queries.
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
    """Persistent, reusable eD2k connection, with idle close."""

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

    # --- public API ---------------------------------------------------------

    def search(self, query: str) -> List[SearchResult]:
        with self._lock:
            self._cancel_timer()
            try:
                pairs = self._search_once(query)
            except (OSError, ConnectionError):
                # The server may have dropped the idle connection: reconnect once.
                self._log.info("[*] eD2k connection down; reconnecting...")
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

    # --- internals ----------------------------------------------------------

    def _search_once(self, query: str) -> list:
        self._ensure_connected()
        assert self._conn is not None
        self._conn.search(query)
        return self._await_results(self._conn)

    def _ensure_connected(self) -> None:
        if self._conn is not None:
            return
        self._log.info(
            "[*] Connecting to %s:%d (persistent session)...", self._host, self._port
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
                self._log.info("[*] Login OK (persistent session).")
                return
            if op == OP_REJECT:
                raise ConnectionError("The server rejected the connection")
            # OP_SERVERMESSAGE / OP_SERVERSTATUS and others: ignored.
        self._log.info("[!] IDCHANGE did not arrive; searching anyway.")

    def _await_results(self, conn: Ed2kConnection) -> list:
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            try:
                op, payload = conn.recv_packet()
            except socket.timeout:
                break
            if op == OP_SEARCHRESULT:
                return parse_search_result(payload)
            # OP_SERVERMESSAGE and others: ignored.
        self._log.info("[!] No results arrived (timeout).")
        return []

    def _after_search(self) -> None:
        # idle > 0: keep alive and schedule an idle close.
        # idle <= 0: close now (one connect/login per search, no persistence).
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
                    "[*] Closing idle eD2k connection (%ds without searches).",
                    self._idle,
                )
            self._close_conn()

    def _close_conn(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
