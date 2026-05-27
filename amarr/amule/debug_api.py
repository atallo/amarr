"""API de depuración (``amarr/amule/DebugApi.kt``).

Expone ``GET /status`` con un volcado plano de las estadísticas de aMule, útil
para diagnóstico. ``StatusResponse`` aplana ``StatsResponse`` y anida el estado
de conexión en ``connectionStatus``.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..jamule.client import AmuleClient
from ..jamule.response import StatsResponse

_log = logging.getLogger("amarr.amule.debug")


class ConnectionStatus(BaseModel):
    clientId: Optional[int] = None
    ed2kConnected: Optional[bool] = None
    ed2kConnecting: Optional[bool] = None
    ed2kId: Optional[int] = None
    kadConnected: Optional[bool] = None
    kadFirewalled: Optional[bool] = None
    kadId: Optional[int] = None
    kadRunning: Optional[bool] = None
    serverDescription: Optional[str] = None
    serverFailed: Optional[int] = None
    serverFiles: Optional[int] = None
    serverIpv4: Optional[str] = None
    serverPing: Optional[int] = None
    serverPrio: Optional[int] = None
    serverStatic: Optional[bool] = None
    serverUsers: Optional[int] = None
    serverUsersMax: Optional[int] = None
    serverVersion: Optional[str] = None


class StatusResponse(BaseModel):
    bannedCount: int = 0
    buddyIp: Optional[str] = None
    buddyPort: Optional[int] = None
    buddyStatus: Optional[str] = None
    connectionStatus: Optional[ConnectionStatus] = ConnectionStatus()
    downloadOverhead: int = 0
    downloadSpeed: int = 0
    downloadSpeedLimit: int = 0
    ed2kFiles: int = 0
    ed2kUsers: int = 0
    kadFiles: int = 0
    kadFirewalledUdp: Optional[bool] = None
    kadIndexedKeywords: Optional[int] = None
    kadIndexedLoad: Optional[int] = None
    kadIndexedNotes: Optional[int] = None
    kadIndexedSources: Optional[int] = None
    kadIpAddress: Optional[str] = None
    kadIsRunningInLanMode: Optional[bool] = None
    kadNodes: int = 0
    kadUsers: int = 0
    loggerMessage: List[str] = []
    sharedFileCount: int = 0
    totalReceivedBytes: int = 0
    totalSentBytes: int = 0
    totalSourceCount: int = 0
    uploadOverhead: int = 0
    uploadQueueLength: int = 0
    uploadSpeed: int = 0
    uploadSpeedLimit: int = 0

    @staticmethod
    def from_stats_response(stats: StatsResponse) -> "StatusResponse":
        cs = stats.connection_state
        return StatusResponse(
            bannedCount=stats.banned_count,
            buddyIp=stats.buddy_ip,
            buddyPort=stats.buddy_port,
            buddyStatus=stats.buddy_status.name if stats.buddy_status else None,
            connectionStatus=ConnectionStatus(
                clientId=cs.client_id if cs else None,
                ed2kConnected=cs.ed2k_connected if cs else None,
                ed2kConnecting=cs.ed2k_connecting if cs else None,
                ed2kId=cs.ed2k_id if cs else None,
                kadConnected=cs.kad_connected if cs else None,
                kadFirewalled=cs.kad_firewalled if cs else None,
                kadId=cs.kad_id if cs else None,
                kadRunning=cs.kad_running if cs else None,
                serverDescription=cs.server_description if cs else None,
                serverFailed=cs.server_failed if cs else None,
                serverFiles=cs.server_files if cs else None,
                serverIpv4=cs.server_ipv4.address if cs and cs.server_ipv4 else None,
                serverPing=cs.server_ping if cs else None,
                serverPrio=cs.server_prio if cs else None,
                serverStatic=cs.server_static if cs else None,
                serverUsers=cs.server_users if cs else None,
                serverUsersMax=cs.server_users_max if cs else None,
                serverVersion=cs.server_version if cs else None,
            ),
            downloadOverhead=stats.download_overhead,
            downloadSpeed=stats.download_speed,
            downloadSpeedLimit=stats.download_speed_limit,
            ed2kFiles=stats.ed2k_files,
            ed2kUsers=stats.ed2k_users,
            kadFiles=stats.kad_files,
            kadFirewalledUdp=stats.kad_firewalled_udp,
            kadIndexedKeywords=stats.kad_indexed_keywords,
            kadIndexedLoad=stats.kad_indexed_load,
            kadIndexedNotes=stats.kad_indexed_notes,
            kadIndexedSources=stats.kad_indexed_sources,
            kadIpAddress=stats.kad_ip_address,
            kadIsRunningInLanMode=stats.kad_is_running_in_lan_mode,
            kadNodes=stats.kad_nodes,
            kadUsers=stats.kad_users,
            loggerMessage=stats.logger_message,
            sharedFileCount=stats.shared_file_count,
            totalReceivedBytes=stats.total_received_bytes,
            totalSentBytes=stats.total_sent_bytes,
            totalSourceCount=stats.total_source_count,
            uploadOverhead=stats.upload_overhead,
            uploadQueueLength=stats.upload_queue_length,
            uploadSpeed=stats.upload_speed,
            uploadSpeedLimit=stats.upload_speed_limit,
        )


def build_debug_router(amule_client: AmuleClient) -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    def status() -> JSONResponse:
        stats = amule_client.get_stats()
        return JSONResponse(StatusResponse.from_stats_response(stats).model_dump())

    return router
