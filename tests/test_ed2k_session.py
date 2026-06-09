"""Tests de Ed2kServerSession: conexión persistente, reconexión e idle."""
import socket
import struct

from amarr.ed2k.server import OP_IDCHANGE, OP_SEARCHRESULT
from amarr.ed2k_session import Ed2kServerSession

# Payload de OP_SEARCHRESULT con 0 resultados (count = 0).
_NO_RESULTS = struct.pack("<I", 0)


class FakeConn:
    """Conexión eD2k de mentira: encola IDCHANGE al loguear y SEARCHRESULT al buscar."""

    def __init__(self):
        self.logins = 0
        self.searches = []
        self.closed = False
        self._queue = []

    def login(self, nick="x", client_port=0):
        self.logins += 1
        self._queue.append((OP_IDCHANGE, b"\x00\x00\x00\x01"))

    def search(self, query):
        self.searches.append(query)
        self._queue.append((OP_SEARCHRESULT, _NO_RESULTS))

    def recv_packet(self):
        if self._queue:
            return self._queue.pop(0)
        raise socket.timeout()

    def close(self):
        self.closed = True


def _session(factory, idle_seconds=600):
    return Ed2kServerSession(idle_seconds=idle_seconds, conn_factory=factory, timeout=1.0)


def test_reuses_connection_single_login():
    conns = []

    def factory():
        c = FakeConn()
        conns.append(c)
        return c

    s = _session(factory)
    s.search("a")
    s.search("b")
    s.search("c")
    assert len(conns) == 1  # una sola conexión
    assert conns[0].logins == 1  # un solo login para 3 búsquedas
    assert conns[0].searches == ["a", "b", "c"]
    s.close()


def test_reconnects_after_connection_error():
    conns = []

    class Conn(FakeConn):
        def search(self, query):
            if len(conns) == 1:  # la primera conexión está "muerta"
                raise ConnectionError("dead")
            super().search(query)

    def factory():
        c = Conn()
        conns.append(c)
        return c

    s = _session(factory)
    s.search("a")  # 1ª conn falla -> reconecta -> 2ª OK
    assert len(conns) == 2
    assert conns[0].closed
    s.close()


def test_idle_close_then_reconnect():
    conns = []

    def factory():
        c = FakeConn()
        conns.append(c)
        return c

    s = _session(factory)
    s.search("a")
    assert len(conns) == 1
    s._idle_close()  # simula el disparo del timer de inactividad
    assert conns[0].closed
    s.search("b")  # debe reconectar
    assert len(conns) == 2
    s.close()


def test_idle_zero_closes_after_each_search():
    conns = []

    def factory():
        c = FakeConn()
        conns.append(c)
        return c

    s = _session(factory, idle_seconds=0)
    s.search("a")
    s.search("b")
    assert len(conns) == 2  # sin persistencia: una conexión por búsqueda
    assert conns[0].closed and conns[1].closed
    s.close()
