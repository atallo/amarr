"""Sesión Kad que reutiliza el pool de contactos vivos entre búsquedas.

Kad es serverless (UDP): no hay conexión ni login que mantener, pero el bootstrap
desde ``nodes.dat`` (~30 s) se repite en cada búsqueda. Esta sesión **acumula**
los contactos vivos descubiertos y los usa como semillas de las siguientes
búsquedas, reduciendo el bootstrap. Tras ``idle_seconds`` sin búsquedas el pool
se descarta (la próxima parte de ``nodes.dat``).

Cada búsqueda usa su propio ``KadClient`` (socket UDP propio, barato), así que
puede haber búsquedas concurrentes; solo el acceso al pool va bajo cerrojo.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional, Tuple

from .ed2k import SearchResult
from .ed2k.kad import KadClient, kad_id_int, keyword_target, parse_nodes_dat

_log = logging.getLogger("ed2k.kad")

# Límites para que el pool y el bootstrap no crezcan sin control.
_MAX_POOL = 2000
_MAX_SEEDS = 400

# Motor inyectable para tests: (query, seeds, with_sources) -> (contacts, pairs).
SearchEngine = Callable[[str, list, bool], Tuple[dict, list]]


class KadSession:
    """Búsquedas Kad reutilizando un pool de contactos vivos acumulado."""

    def __init__(
        self,
        nodes_path: str,
        ip_order: str = "be",
        with_sources: bool = False,
        idle_seconds: int = 600,
        timeout: float = 3.0,
        verbose: bool = False,
        search_engine: Optional[SearchEngine] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._seeds, _, _ = parse_nodes_dat(nodes_path, ip_order)
        if not self._seeds:
            raise ValueError("nodes.dat sin contactos semilla: %s" % nodes_path)
        self._ip_order = ip_order
        self._with_sources = with_sources
        self._idle = idle_seconds
        self._timeout = timeout
        self._verbose = verbose
        self._search_engine = search_engine
        self._log = logger or _log
        self._lock = threading.RLock()
        self._pool: dict = {}  # id_int -> contacto
        self._timer: Optional[threading.Timer] = None

    # --- API pública --------------------------------------------------------

    def search(self, query: str, with_sources: Optional[bool] = None) -> List[SearchResult]:
        do_sources = self._with_sources if with_sources is None else with_sources
        with self._lock:
            self._cancel_timer()
            seeds = self._seeds_for(query)
            pool_size = len(self._pool)
        self._log.debug(
            "Kad: %d semillas (pool reutilizado: %d contactos)", len(seeds), pool_size
        )
        # La búsqueda UDP va fuera del cerrojo para permitir concurrencia.
        contacts, pairs = self._run_search(query, seeds, do_sources)
        with self._lock:
            self._merge_pool(contacts)
            self._after_search()
        return [SearchResult.from_tags(h, t) for h, t in pairs]

    def close(self) -> None:
        with self._lock:
            self._cancel_timer()
            self._pool = {}

    # --- internos -----------------------------------------------------------

    def _seeds_for(self, query: str) -> list:
        words = query.lower().split()
        target = kad_id_int(keyword_target(words[0])) if words else 0
        combined = {c["id_int"]: c for c in self._seeds}
        combined.update(self._pool)
        ordered = sorted(combined.values(), key=lambda c: c["id_int"] ^ target)
        return ordered[:_MAX_SEEDS]

    def _run_search(self, query: str, seeds: list, with_sources: bool) -> Tuple[dict, list]:
        if self._search_engine is not None:
            return self._search_engine(query, seeds, with_sources)
        cli = KadClient(
            ip_order=self._ip_order, verbose=self._verbose, timeout=self._timeout
        )
        try:
            pairs = cli.keyword_search(query, seeds=seeds, do_sources=with_sources)
            return dict(cli.contacts), pairs
        finally:
            cli.close()

    def _merge_pool(self, contacts: dict) -> None:
        if not contacts:
            return
        self._pool.update(contacts)
        if len(self._pool) > _MAX_POOL:
            # dict conserva el orden de inserción; conservamos los últimos.
            self._pool = dict(list(self._pool.items())[-_MAX_POOL:])

    def _after_search(self) -> None:
        if self._idle and self._idle > 0:
            self._schedule_timer()
        else:
            self._pool = {}  # idle <= 0: no reutilizar el pool entre búsquedas

    def _schedule_timer(self) -> None:
        self._timer = threading.Timer(self._idle, self._idle_clear)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _idle_clear(self) -> None:
        with self._lock:
            if self._pool:
                self._log.info(
                    "[*] Descartando pool Kad (%ds sin búsquedas).", self._idle
                )
            self._pool = {}
            self._timer = None
