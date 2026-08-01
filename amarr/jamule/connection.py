"""TCP connection to the aMule core (``jamule/AmuleConnection.kt``).

Handles the socket, reconnection and authentication. It is **synchronous** and
protects each request/response exchange with a :class:`threading.Lock` (equivalent
to Kotlin's ``synchronized(socket)``), so that several threads of the FastAPI
threadpool can safely share a single client.
"""
from __future__ import annotations

import io
import logging
import socket
import threading
from typing import Callable, Optional

from .ec.packet import Packet, PacketParser, PacketWriter
from .ec.tag import TagEncoder, TagParser
from .exceptions import CommunicationException, ServerException
from .password import hash_password
from .request import auth_request, salt_request
from .response import (
    AuthFailedResponse,
    AuthOkResponse,
    AuthSaltResponse,
    ErrorResponse,
    Response,
    parse as parse_response,
)

_logger = logging.getLogger("amarr.jamule.connection")


class AmuleConnection:
    """Authenticated and reusable connection to aMule."""

    def __init__(
        self,
        socket_builder: Callable[[], socket.socket],
        password: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._socket_builder = socket_builder
        self._password = password
        self._logger = logger or _logger
        self._connected = False
        self._socket: Optional[socket.socket] = None
        # Persistent buffered reader bound to the socket. It is recreated on each
        # reconnection; reusing it avoids losing bytes that the buffer might
        # have read ahead between requests.
        self._reader: Optional[io.BufferedReader] = None
        self._lock = threading.RLock()

        self._tag_parser = TagParser()
        self._packet_parser = PacketParser(self._tag_parser)
        self._tag_encoder = TagEncoder()
        self._packet_writer = PacketWriter(self._tag_encoder)

    @classmethod
    def from_host(
        cls,
        host: str,
        port: int,
        timeout: float,
        password: str,
        logger: Optional[logging.Logger] = None,
    ) -> "AmuleConnection":
        """Creates a connection from host/port.

        ``timeout`` in seconds (0 = no timeout, like ``soTimeout`` in Java).
        """

        def builder() -> socket.socket:
            sock = socket.create_connection((host, port))
            sock.settimeout(timeout if timeout and timeout > 0 else None)
            return sock

        return cls(builder, password, logger)

    # --- lifecycle ----------------------------------------------------------

    def reconnect(self) -> None:
        with self._lock:
            self._logger.info("Reconnecting...")
            self._connected = False
            if self._socket is not None:
                try:
                    self._socket.close()
                except OSError:
                    pass
            self._socket = self._socket_builder()
            self._reader = self._socket.makefile("rb")
            self._authenticate()

    def send_request(self, packet: Packet) -> Response:
        """Sends a request, reconnecting/authenticating if needed."""
        if not self._connected:
            self.reconnect()
        try:
            return self._send_request_no_auth(packet)
        except OSError:
            # An I/O failure invalidates the connection; the next send
            # will reconnect. We re-raise so the upper layer decides.
            self._connected = False
            raise

    def _send_request_no_auth(self, packet: Packet) -> Response:
        with self._lock:
            assert self._socket is not None and self._reader is not None
            out = io.BytesIO()
            self._packet_writer.write(packet, out)
            self._socket.sendall(out.getvalue())

            response_packet = self._packet_parser.parse(self._reader)
            response = parse_response(response_packet)
            if isinstance(response, ErrorResponse):
                raise ServerException(response.server_message)
            return response

    def _authenticate(self) -> None:
        self._logger.info("Authenticating...")
        salt_response = self._send_request_no_auth(salt_request())
        if isinstance(salt_response, AuthFailedResponse):
            raise ServerException("Authentication failed", salt_response)
        if not isinstance(salt_response, AuthSaltResponse):
            raise CommunicationException("Unable to get auth salt")

        salted_password = hash_password(self._password, salt_response.salt)
        response = self._send_request_no_auth(auth_request(salted_password))
        if isinstance(response, AuthFailedResponse):
            raise ServerException("Authentication failed", response)
        if not isinstance(response, AuthOkResponse):
            raise CommunicationException("Unable to authenticate")

        self._logger.info("Authenticated with server version %s", response.version)
        self._connected = True
