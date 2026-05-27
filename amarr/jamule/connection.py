"""Conexión TCP con el núcleo de aMule (``jamule/AmuleConnection.kt``).

Maneja el socket, la reconexión y la autenticación. Es **síncrono** y protege
cada intercambio petición/respuesta con un :class:`threading.Lock` (equivale al
``synchronized(socket)`` de Kotlin), de modo que varios hilos del threadpool de
FastAPI pueden compartir un mismo cliente con seguridad.
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
    """Conexión autenticada y reutilizable con aMule."""

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
        # Lector buffer persistente ligado al socket. Se recrea en cada
        # reconexión; reutilizarlo evita perder bytes que el buffer pudiera
        # haber leído por adelantado entre peticiones.
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
        """Crea una conexión a partir de host/puerto.

        ``timeout`` en segundos (0 = sin timeout, como ``soTimeout`` en Java).
        """

        def builder() -> socket.socket:
            sock = socket.create_connection((host, port))
            sock.settimeout(timeout if timeout and timeout > 0 else None)
            return sock

        return cls(builder, password, logger)

    # --- ciclo de vida ------------------------------------------------------

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
        """Envía una petición, reconectando/autenticando si hace falta."""
        if not self._connected:
            self.reconnect()
        try:
            return self._send_request_no_auth(packet)
        except OSError:
            # Un fallo de E/S invalida la conexión; el siguiente envío
            # reconectará. Re-elevamos para que la capa superior decida.
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
