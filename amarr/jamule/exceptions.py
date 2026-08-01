"""Exceptions of the jamule layer (EC protocol).

Port of ``jamule/exception/*.kt``. ``AmuleException`` is the root; the rest
inherit from it, just like in the original library.
"""

from __future__ import annotations


class AmuleException(Exception):
    """Base exception for all jamule errors."""


class CommunicationException(AmuleException):
    """Unexpected or uninterpretable response from the server."""


class InvalidECException(AmuleException):
    """The received or built EC packet is invalid."""


class ServerException(AmuleException):
    """aMule returned an explicit error.

    :param message: error message.
    :param cause: response or exception that caused the error, if any.
    """

    def __init__(self, message: str, cause: object | None = None) -> None:
        super().__init__(message)
        self.cause = cause
