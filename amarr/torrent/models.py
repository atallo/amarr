"""Models of the qBittorrent API that amarr emulates (``amarr/torrent/model/*.kt``).

Sonarr/Radarr believe they are talking to qBittorrent v2.8.19, so these
models reproduce exactly the field names (snake_case) and the default
values that qBittorrent returns. Kotlin serialized with
``encodeDefaults=true``; pydantic emits all fields by default, so
the resulting JSON is equivalent.

``Category`` is a *frozen* dataclass (hashable) because it is stored in sets.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel


@dataclass(frozen=True)
class Category:
    """qBittorrent category (name + save path)."""

    name: str
    save_path: str = ""

    # qBittorrent exposes the field as ``savePath`` in JSON.
    def to_json(self) -> dict:
        return {"name": self.name, "savePath": self.save_path}


class TorrentFile(BaseModel):
    """A file inside a torrent."""

    name: str


class TorrentProperties(BaseModel):
    """Torrent properties (subset used by Radarr)."""

    hash: str
    save_path: str
    seeding_time: int


class TorrentState(str, Enum):
    """qBittorrent torrent states (see WebUI-API 4.1 wiki)."""

    error = "error"
    stalledDL = "stalledDL"
    missingFiles = "missingFiles"
    pausedDL = "pausedDL"
    queuedDL = "queuedDL"
    checkingDL = "checkingDL"
    checkingUP = "checkingUP"
    checkingResumeData = "checkingResumeData"
    pausedUP = "pausedUP"
    uploading = "uploading"
    stalledUP = "stalledUP"
    queuedUP = "queuedUP"
    forcedUP = "forcedUP"
    metaDL = "metaDL"
    forcedDL = "forcedDL"
    moving = "moving"
    downloading = "downloading"
    allocating = "allocating"
    unknown = "unknown"


# The long default magnet_uri that amarr uses as a placeholder.
_DEFAULT_MAGNET_URI = (
    "magnet:?xt=urn:btih:58d3afd393bb1748dc25e24fc680f032a475fa63"
    "&dn=Matrix%20HQ%20movie%201998"
    "&tr=udp%3a%2f%2ftracker.opentrackr.org%3a1337%2fannounce"
    "&tr=https%3a%2f%2ftracker2.ctix.cn%3a443%2fannounce"
    "&tr=https%3a%2f%2ftracker1.520.jp%3a443%2fannounce"
    "&tr=udp%3a%2f%2fopentracker.i2p.rocks%3a6969%2fannounce"
    "&tr=udp%3a%2f%2fopen.tracker.cl%3a1337%2fannounce"
    "&tr=udp%3a%2f%2fopen.demonii.com%3a1337%2fannounce"
    "&tr=udp%3a%2f%2ftracker.openbittorrent.com%3a6969%2fannounce"
    "&tr=http%3a%2f%2ftracker.openbittorrent.com%3a80%2fannounce"
    "&tr=udp%3a%2f%2fopen.stealth.si%3a80%2fannounce"
    "&tr=udp%3a%2f%2fexodus.desync.com%3a6969%2fannounce"
    "&tr=udp%3a%2f%2ftracker.torrent.eu.org%3a451%2fannounce"
    "&tr=udp%3a%2f%2ftracker1.bt.moack.co.kr%3a80%2fannounce"
    "&tr=udp%3a%2f%2ftracker-udp.gbitt.info%3a80%2fannounce"
    "&tr=udp%3a%2f%2fexplodie.org%3a6969%2fannounce"
    "&tr=https%3a%2f%2ftracker.gbitt.info%3a443%2fannounce"
    "&tr=http%3a%2f%2ftracker.gbitt.info%3a80%2fannounce"
    "&tr=http%3a%2f%2fbt.endpot.com%3a80%2fannounce"
    "&tr=udp%3a%2f%2ftracker.tiny-vps.com%3a6969%2fannounce"
    "&tr=udp%3a%2f%2ftracker.auctor.tv%3a6969%2fannounce"
    "&tr=udp%3a%2f%2ftk1.trackerservers.com%3a8080%2fannounce"
)


class TorrentInfo(BaseModel):
    """Torrent information as Radarr/Sonarr expects it.

    The first fields are the ones Radarr consumes; the rest reproduce the
    qBittorrent response with default values.
    """

    # Used by Radarr.
    hash: str
    name: str
    size: int
    progress: float
    eta: int
    state: TorrentState
    category: str | None
    save_path: str

    # Handled by amarr but not used by Radarr.
    dlspeed: int
    num_seeds: int
    priority: int
    total_size: int
    downloaded: int

    # Parsed by Radarr but not yet handled by amarr.
    content_path: str = ""
    ratio: float = 1.0
    ratio_limit: int = -2
    seeding_time: int = 1
    seeding_time_limit: int = -2

    magnet_uri: str = _DEFAULT_MAGNET_URI

    # Not handled by amarr (qBittorrent default values).
    upspeed: int = 0
    num_leechs: int = 0
    tags: str = ""
    super_seeding: bool = False
    added_on: int = 1696781958
    amount_left: int = 0
    auto_tmm: bool = False
    availability: int = 0
    completed: int = 0
    completion_on: int = 0
    dl_limit: int = 0
    download_path: str = ""
    downloaded_session: int = 0
    f_l_piece_prio: bool = False
    force_start: bool = False
    last_activity: int = 1696781958
    max_ratio: int = -1
    max_seeding_time: int = -1
    num_complete: int = -1
    num_incomplete: int = -1
    seen_complete: int = 0
    seq_dl: bool = False
    time_active: int = 309
    tracker: str = "http://tracker.openbittorrent.com:80/announce"
    trackers_count: int = 20
    up_limit: int = 0
    uploaded: int = 0
    uploaded_session: int = 0


class Preferences(BaseModel):
    """qBittorrent preferences. Only ``save_path`` is required."""

    add_trackers: str = ""
    add_trackers_enabled: bool = False
    alt_dl_limit: int = 0
    alt_up_limit: int = 3072000
    alternative_webui_enabled: bool = False
    alternative_webui_path: str = ""
    announce_ip: str = ""
    announce_to_all_tiers: bool = True
    announce_to_all_trackers: bool = False
    anonymous_mode: bool = False
    async_io_threads: int = 10
    auto_delete_mode: int = 0
    auto_tmm_enabled: bool = False
    autorun_enabled: bool = False
    autorun_on_torrent_added_enabled: bool = False
    autorun_on_torrent_added_program: str = ""
    autorun_program: str = ""
    banned_IPs: str = ""
    bittorrent_protocol: int = 0
    block_peers_on_privileged_ports: bool = False
    bypass_auth_subnet_whitelist: str = "0.0.0.0/0"
    bypass_auth_subnet_whitelist_enabled: bool = True
    bypass_local_auth: bool = True
    category_changed_tmm_enabled: bool = False
    checking_memory_use: int = 32
    connection_speed: int = 30
    current_interface_address: str = ""
    current_network_interface: str = ""
    dht: bool = True
    disk_cache: int = -1
    disk_cache_ttl: int = 60
    disk_io_read_mode: int = 1
    disk_io_type: int = 0
    disk_io_write_mode: int = 1
    disk_queue_size: int = 1048576
    dl_limit: int = 0
    dont_count_slow_torrents: bool = True
    dyndns_domain: str = "changeme.dyndns.org"
    dyndns_enabled: bool = False
    dyndns_password: str = ""
    dyndns_service: int = 0
    dyndns_username: str = ""
    embedded_tracker_port: int = 9000
    embedded_tracker_port_forwarding: bool = False
    enable_coalesce_read_write: bool = False
    enable_embedded_tracker: bool = False
    enable_multi_connections_from_same_ip: bool = False
    enable_piece_extent_affinity: bool = False
    enable_upload_suggestions: bool = False
    encryption: int = 0
    excluded_file_names: str = ""
    excluded_file_names_enabled: bool = False
    export_dir: str = ""
    export_dir_fin: str = ""
    file_pool_size: int = 5000
    hashing_threads: int = 1
    idn_support_enabled: bool = False
    incomplete_files_ext: bool = False
    ip_filter_enabled: bool = False
    ip_filter_path: str = ""
    ip_filter_trackers: bool = False
    limit_lan_peers: bool = True
    limit_tcp_overhead: bool = False
    limit_utp_rate: bool = True
    listen_port: int = 6881
    locale: str = "en"
    lsd: bool = True
    mail_notification_auth_enabled: bool = True
    mail_notification_email: str = ""
    mail_notification_enabled: bool = False
    mail_notification_password: str = ""
    mail_notification_sender: str = "qBittorrent_notification@example.com"
    mail_notification_smtp: str = "smtp.changeme.com"
    mail_notification_ssl_enabled: bool = False
    mail_notification_username: str = ""
    max_active_checking_torrents: int = 1
    max_active_downloads: int = 20
    max_active_torrents: int = 10
    max_active_uploads: int = 5
    max_concurrent_http_announces: int = 50
    max_connec: int = 500
    max_connec_per_torrent: int = 100
    max_ratio: int = 2
    max_ratio_act: int = 3
    max_ratio_enabled: bool = False
    max_seeding_time: int = 259200
    max_seeding_time_enabled: bool = False
    max_uploads: int = 20
    max_uploads_per_torrent: int = 4
    memory_working_set_limit: int = 512
    outgoing_ports_max: int = 0
    outgoing_ports_min: int = 0
    peer_tos: int = 4
    peer_turnover: int = 4
    peer_turnover_cutoff: int = 90
    peer_turnover_interval: int = 300
    performance_warning: bool = False
    pex: bool = True
    preallocate_all: bool = False
    proxy_auth_enabled: bool = False
    proxy_hostname_lookup: bool = True
    proxy_ip: str = "0.0.0.0"
    proxy_password: str = ""
    proxy_peer_connections: bool = False
    proxy_port: int = 8080
    proxy_torrents_only: bool = False
    proxy_type: int = 0
    proxy_username: str = ""
    queueing_enabled: bool = True
    random_port: bool = False
    reannounce_when_address_changed: bool = False
    recheck_completed_torrents: bool = False
    refresh_interval: int = 1500
    request_queue_size: int = 500
    resolve_peer_countries: bool = True
    resume_data_storage_type: str = "Legacy"
    rss_auto_downloading_enabled: bool = False
    rss_download_repack_proper_episodes: bool = True
    rss_max_articles_per_feed: int = 50
    rss_processing_enabled: bool = False
    rss_refresh_interval: int = 30
    rss_smart_episode_filters: str = "s(\\d+)e(\\d+)\n(\\d+)x(\\d+)\n(\\d{4}[.\\-]\\d{1,2}[.\\-]\\d{1,2})\n(\\d{1,2}[.\\-]\\d{1,2}[.\\-]\\d{4})"
    save_path: str
    save_path_changed_tmm_enabled: bool = False
    save_resume_data_interval: int = 60
    schedule_from_hour: int = 8
    schedule_from_min: int = 0
    schedule_to_hour: int = 20
    schedule_to_min: int = 0
    scheduler_days: int = 0
    scheduler_enabled: bool = True
    send_buffer_low_watermark: int = 10
    send_buffer_watermark: int = 500
    send_buffer_watermark_factor: int = 50
    slow_torrent_dl_rate_threshold: int = 1000
    slow_torrent_inactive_timer: int = 60
    slow_torrent_ul_rate_threshold: int = 80
    socket_backlog_size: int = 30
    ssrf_mitigation: bool = True
    start_paused_enabled: bool = False
    stop_tracker_timeout: int = 5
    temp_path: str = "/downloads/incomplete"
    temp_path_enabled: bool = False
    torrent_changed_tmm_enabled: bool = True
    torrent_content_layout: str = "Original"
    torrent_stop_condition: str = "None"
    up_limit: int = 10240000
    upload_choking_algorithm: int = 1
    upload_slots_behavior: int = 0
    upnp: bool = False
    upnp_lease_duration: int = 0
    use_category_paths_in_manual_mode: bool = False
    use_https: bool = False
    utp_tcp_mixed_mode: int = 0
    validate_https_tracker_certificate: bool = True
    web_ui_address: str = "*"
    web_ui_ban_duration: int = 3600
    web_ui_clickjacking_protection_enabled: bool = True
    web_ui_csrf_protection_enabled: bool = True
    web_ui_custom_http_headers: str = ""
    web_ui_domain_list: str = "*"
    web_ui_host_header_validation_enabled: bool = True
    web_ui_https_cert_path: str = ""
    web_ui_https_key_path: str = ""
    web_ui_max_auth_fail_count: int = 5
    web_ui_port: int = 8055
    web_ui_reverse_proxies_list: str = ""
    web_ui_reverse_proxy_enabled: bool = False
    web_ui_secure_cookie_enabled: bool = True
    web_ui_session_timeout: int = 3600
    web_ui_upnp: bool = True
    web_ui_use_custom_http_headers_enabled: bool = False
    web_ui_username: str = "oslinux"
