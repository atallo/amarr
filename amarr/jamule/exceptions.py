"""Excepciones de la capa jamule (protocolo EC).

Port de ``jamule/exception/*.kt``. ``AmuleException`` es la raíz; el resto
hereda de ella, igual que en la librería original.
"""

from __future__ import annotations


class AmuleException(Exception):
    """Excepción base de todos los errores de jamule."""


class CommunicationException(AmuleException):
    """Respuesta inesperada o imposible de interpretar del servidor."""


class InvalidECException(AmuleException):
    """El paquete EC recibido o construido es inválido."""


class ServerException(AmuleException):
    """aMule devolvió un error explícito.

    :param message: mensaje de error.
    :param cause: respuesta o excepción que originó el error, si la hay.
    """

    def __init__(self, message: str, cause: object | None = None) -> None:
        super().__init__(message)
        self.cause = cause
