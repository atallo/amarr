"""Constructores de peticiones EC (``jamule/request/*.kt``).

Cada función/clase produce un :class:`Packet` listo para enviar. En Kotlin son
``data class``/``class`` que implementan la interfaz ``Request`` con un método
``packet()``; aquí se modelan como funciones-fábrica (más idiomático en Python)
salvo cuando conviene conservar parámetros, en cuyo caso son funciones con
argumentos. Todos los detalles de wire-format viven en :mod:`amarr.jamule.ec`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .ec.codes import (
    ECDetailLevel,
    ECOpCode,
    ECSearchType,
    ECTagName,
    EcPrefs,
    ProtocolVersion,
)
from .ec.packet import Flags, Packet
from .ec.tag import (
    CustomTag,
    Hash16Tag,
    StringTag,
    Tag,
    UByteTag,
    UIntTag,
    ULongTag,
    UShortTag,
)
from .model import AmuleCategory, DownloadCommand

# Identificación del cliente, igual que ``AmuleClient.CLIENT_NAME`` y
# ``Build.VERSION`` en jaMule (soporta aMule 2.3.1-2.3.3).
CLIENT_NAME = "jAmule"
CLIENT_VERSION = "for amule 2.3.3"


def salt_request() -> Packet:
    """EC_OP_AUTH_REQ: solicita el *salt* para autenticar."""
    return Packet(
        ECOpCode.EC_OP_AUTH_REQ,
        [
            StringTag(ECTagName.EC_TAG_CLIENT_NAME, value=CLIENT_NAME),
            StringTag(ECTagName.EC_TAG_CLIENT_VERSION, value=CLIENT_VERSION),
            UShortTag(
                ECTagName.EC_TAG_PROTOCOL_VERSION,
                value=ProtocolVersion.EC_CURRENT_PROTOCOL_VERSION.value,
            ),
            CustomTag(ECTagName.EC_TAG_CAN_ZLIB, value=b""),
            CustomTag(ECTagName.EC_TAG_CAN_UTF8_NUMBERS, value=b""),
        ],
        Flags(),
    )


def auth_request(hashed_password: bytes) -> Packet:
    """EC_OP_AUTH_PASSWD: envía el hash de la contraseña con el salt."""
    return Packet(
        ECOpCode.EC_OP_AUTH_PASSWD,
        [Hash16Tag(ECTagName.EC_TAG_PASSWD_HASH, value=hashed_password)],
        Flags(),
    )


def stats_request() -> Packet:
    """EC_OP_STAT_REQ: estadísticas completas del núcleo."""
    return Packet(
        ECOpCode.EC_OP_STAT_REQ,
        [UByteTag(ECTagName.EC_TAG_DETAIL_LEVEL, value=ECDetailLevel.EC_DETAIL_FULL.value)],
        Flags(),
    )


def download_queue_request() -> Packet:
    """EC_OP_GET_DLOAD_QUEUE: cola de descargas con detalle completo."""
    return Packet(
        ECOpCode.EC_OP_GET_DLOAD_QUEUE,
        [UByteTag(ECTagName.EC_TAG_DETAIL_LEVEL, value=ECDetailLevel.EC_DETAIL_FULL.value)],
    )


def shared_files_request() -> Packet:
    """EC_OP_GET_SHARED_FILES: ficheros compartidos con detalle completo."""
    return Packet(
        ECOpCode.EC_OP_GET_SHARED_FILES,
        [UByteTag(ECTagName.EC_TAG_DETAIL_LEVEL, value=ECDetailLevel.EC_DETAIL_FULL.value)],
    )


def add_link_request(link: str) -> Packet:
    """EC_OP_ADD_LINK: añade una descarga a partir de un enlace ed2k."""
    return Packet(
        ECOpCode.EC_OP_ADD_LINK,
        [StringTag(ECTagName.EC_TAG_PARTFILE_ED2K_LINK, value=link)],
    )


def search_status_request() -> Packet:
    """EC_OP_SEARCH_PROGRESS: progreso (0..100%) de la búsqueda en curso."""
    return Packet(ECOpCode.EC_OP_SEARCH_PROGRESS, [])


def search_results_request() -> Packet:
    """EC_OP_SEARCH_RESULTS: resultados de la búsqueda en curso."""
    return Packet(ECOpCode.EC_OP_SEARCH_RESULTS, [])


def search_stop_request() -> Packet:
    """EC_OP_SEARCH_STOP: detiene la búsqueda en curso."""
    return Packet(ECOpCode.EC_OP_SEARCH_STOP, [])


def get_preferences_request(prefs: EcPrefs) -> Packet:
    """EC_OP_GET_PREFERENCES: lee un bloque de preferencias del núcleo."""
    return Packet(
        ECOpCode.EC_OP_GET_PREFERENCES,
        [
            UByteTag(ECTagName.EC_TAG_DETAIL_LEVEL, value=ECDetailLevel.EC_DETAIL_FULL.value),
            UIntTag(ECTagName.EC_TAG_SELECT_PREFS, value=prefs.value),
        ],
    )


def download_command_request(file_hash: bytes, status: DownloadCommand) -> Packet:
    """Comando sobre una descarga (pausar, reanudar, borrar...).

    El *opcode* del paquete es el asociado al comando (``status.value``).
    """
    return Packet(
        status.value,
        [Hash16Tag(ECTagName.EC_TAG_PARTFILE, value=file_hash)],
    )


def download_search_result_request(file_hash: bytes) -> Packet:
    """EC_OP_DOWNLOAD_SEARCH_RESULT: descarga un resultado de búsqueda."""
    return Packet(
        ECOpCode.EC_OP_DOWNLOAD_SEARCH_RESULT,
        [Hash16Tag(ECTagName.EC_TAG_PARTFILE, value=file_hash)],
    )


def set_file_category_request(file_hash: bytes, category: int) -> Packet:
    """EC_OP_PARTFILE_SET_CAT: asigna una categoría a una descarga."""
    return Packet(
        ECOpCode.EC_OP_PARTFILE_SET_CAT,
        [
            Hash16Tag(
                ECTagName.EC_TAG_PARTFILE,
                value=file_hash,
                subtags=[ULongTag(ECTagName.EC_TAG_PARTFILE_CAT, value=category)],
            )
        ],
    )


def create_category_request(category: AmuleCategory) -> Packet:
    """EC_OP_CREATE_CATEGORY: crea una categoría en aMule."""
    return Packet(
        ECOpCode.EC_OP_CREATE_CATEGORY,
        [
            UIntTag(
                ECTagName.EC_TAG_CATEGORY,
                value=category.id,
                subtags=[
                    StringTag(ECTagName.EC_TAG_CATEGORY_TITLE, value=category.name),
                    StringTag(ECTagName.EC_TAG_CATEGORY_PATH, value=category.path),
                    StringTag(ECTagName.EC_TAG_CATEGORY_COMMENT, value=category.comment),
                    UByteTag(ECTagName.EC_TAG_CATEGORY_COLOR, value=category.color & 0xFF),
                    UIntTag(ECTagName.EC_TAG_CATEGORY_PRIO, value=category.priority),
                ],
            )
        ],
    )


class SearchType(Enum):
    """Ámbito de la búsqueda."""

    GLOBAL = ECSearchType.EC_SEARCH_GLOBAL
    KAD = ECSearchType.EC_SEARCH_KAD
    LOCAL = ECSearchType.EC_SEARCH_LOCAL
    WEB = ECSearchType.EC_SEARCH_WEB


@dataclass
class SearchFilters:
    """Filtros opcionales de una búsqueda."""

    filetype: Optional[str] = None
    extension: Optional[str] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    availability: Optional[int] = None


def search_request(
    query: str,
    type: SearchType,
    filters: Optional[SearchFilters] = None,
) -> Packet:
    """EC_OP_SEARCH_START: inicia una búsqueda asíncrona.

    El nombre buscado va como subtag del tag de tipo de búsqueda; los filtros
    (si existen) van como tags hermanos a nivel raíz.
    """
    filters = filters or SearchFilters()
    tags: List[Tag] = [
        UByteTag(
            ECTagName.EC_TAG_SEARCH_TYPE,
            value=type.value.value,
            subtags=[StringTag(ECTagName.EC_TAG_SEARCH_NAME, value=query)],
        )
    ]
    if filters.filetype is not None:
        tags.append(StringTag(ECTagName.EC_TAG_SEARCH_FILE_TYPE, value=filters.filetype))
    if filters.extension is not None:
        tags.append(StringTag(ECTagName.EC_TAG_SEARCH_EXTENSION, value=filters.extension))
    if filters.min_size is not None:
        tags.append(ULongTag(ECTagName.EC_TAG_SEARCH_MIN_SIZE, value=filters.min_size))
    if filters.max_size is not None:
        tags.append(ULongTag(ECTagName.EC_TAG_SEARCH_MAX_SIZE, value=filters.max_size))
    if filters.availability is not None:
        tags.append(
            ULongTag(ECTagName.EC_TAG_SEARCH_AVAILABILITY, value=filters.availability)
        )
    return Packet(ECOpCode.EC_OP_SEARCH_START, tags)
