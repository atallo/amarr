"""Home page (``GET /``): documents the active endpoints with examples.

Generates a minimalist HTML page (Craigslist style: flat, sans-serif,
blue/purple links), responsive (mobile and desktop). It only lists the
**actually active** search engines (according to ``AMARR_SEARCH_BACKENDS``); the
inactive ones don't appear. Each endpoint includes a collapsible
request/response example, in the style of the .NET SOAP web service help pages.
"""
from __future__ import annotations

import html
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from .config import SEARCH_BACKENDS
from .ed2k import human_size
from .magnet import MagnetLink

# Readable name and description of each engine.
_BACKEND_INFO = {
    "amule": ("aMule", "Search through an external aMule (EC protocol)."),
    "ed2k": (
        "eD2k server",
        "Direct search on an eD2k server (implemented by amarr).",
    ),
    "kad": (
        "Kad network",
        "Serverless search on the Kad network (implemented by amarr).",
    ),
}

# Emulated qBittorrent API (consumed by Sonarr/Radarr as a download client).
# Each entry: (method, path, description, request/response example).
# It must mirror the real routes in ``torrent/api.py`` (a test verifies this).
_QBIT_ENDPOINTS = [
    (
        "GET", "/api/v2/app/webapiVersion", "Emulated WebAPI version (2.8.19).",
        "GET /api/v2/app/webapiVersion\n\n"
        "HTTP/1.1 200 OK\nContent-Type: text/plain\n\n2.8.19",
    ),
    (
        "POST", "/api/v2/auth/login", "Login (always accepted; no real authentication).",
        "POST /api/v2/auth/login\nContent-Type: application/x-www-form-urlencoded\n\n"
        "username=admin&password=secret\n\nHTTP/1.1 200 OK\n\nOk.",
    ),
    (
        "GET", "/api/v2/app/preferences", "qBittorrent preferences (includes save_path).",
        "GET /api/v2/app/preferences\n\n"
        "HTTP/1.1 200 OK\nContent-Type: application/json\n\n"
        '{"save_path": "/finished", "max_active_downloads": 20, ...}',
    ),
    (
        "POST", "/api/v2/torrents/add", "Adds a download from an amarr magnet.",
        "POST /api/v2/torrents/add\nContent-Type: application/x-www-form-urlencoded\n\n"
        "urls=magnet:?xt=urn:btih:...&category=radarr\n\nHTTP/1.1 200 OK\n\nOk.",
    ),
    (
        "POST", "/api/v2/torrents/createCategory", "Creates a category.",
        "POST /api/v2/torrents/createCategory\n\n"
        "category=radarr&savePath=/finished\n\nHTTP/1.1 200 OK\n\nOk.",
    ),
    (
        "GET", "/api/v2/torrents/categories", "Lists the categories.",
        "GET /api/v2/torrents/categories\n\n"
        "HTTP/1.1 200 OK\nContent-Type: application/json\n\n"
        '{"radarr": {"name": "radarr", "savePath": "/finished"}}',
    ),
    (
        "GET", "/api/v2/torrents/info", "Lists the downloads (state, progress, ETA…).",
        "GET /api/v2/torrents/info?category=radarr\n\n"
        "HTTP/1.1 200 OK\nContent-Type: application/json\n\n"
        '[{"hash": "0320c4...", "name": "ubuntu...iso", "progress": 0.5,\n'
        '  "state": "downloading", "eta": 1200, "save_path": "/finished"}]',
    ),
    (
        "POST", "/api/v2/torrents/delete", "Deletes downloads (and, optionally, their files).",
        "POST /api/v2/torrents/delete\n\n"
        "hashes=0320c4...&deleteFiles=true\n\nHTTP/1.1 200 OK\n\nOk.",
    ),
    (
        "GET", "/api/v2/torrents/files", "Files of a download.",
        "GET /api/v2/torrents/files?hash=0320c4...\n\n"
        "HTTP/1.1 200 OK\nContent-Type: application/json\n\n"
        '[{"name": "ubuntu-24.04-desktop-amd64.iso"}]',
    ),
    (
        "GET", "/api/v2/torrents/properties", "Properties of a download.",
        "GET /api/v2/torrents/properties?hash=0320c4...\n\n"
        "HTTP/1.1 200 OK\nContent-Type: application/json\n\n"
        '{"hash": "0320c4...", "save_path": "/finished", "seeding_time": 1}',
    ),
]

# Example of the status endpoint.
_STATUS_EXAMPLE = (
    "GET /status\n\n"
    "HTTP/1.1 200 OK\nContent-Type: application/json\n\n"
    '{"connectionStatus": {"ed2kConnected": true, "kadConnected": true},\n'
    ' "downloadSpeed": 0, "ed2kFiles": 0, "kadFiles": 0}'
)

_CSS = """
* { box-sizing: border-box; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.45;
       color: #222; background: #fff; margin: 0; padding: 14px; }
.container { max-width: 820px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0; }
h2 { font-size: 15px; font-weight: bold; margin: 22px 0 6px; padding-bottom: 3px;
     border-bottom: 1px solid #ccc; }
a { color: #0000cc; text-decoration: underline; }
a:visited { color: #551a8b; }
.sub { color: #444; margin: 4px 0 0; }
.muted { color: #666; font-size: 13px; }
.endpoint { margin: 10px 0 14px; }
ul { margin: 5px 0; padding-left: 20px; }
code { font-family: Menlo, Consolas, monospace; font-size: 12.5px; background: #f4f4f4;
       padding: 1px 4px; border-radius: 2px; word-break: break-all; }
pre { font-family: Menlo, Consolas, monospace; font-size: 12px; background: #f4f4f4;
      border: 1px solid #ddd; padding: 10px; overflow-x: auto; line-height: 1.35; margin: 5px 0 0; }
ul.api { list-style: none; padding-left: 0; }
.m { display: inline-block; min-width: 40px; font-family: Menlo, Consolas, monospace;
     font-size: 11px; font-weight: bold; color: #666; }
details { margin: 4px 0 0; }
summary { cursor: pointer; color: #0000cc; font-size: 12px; }
summary:hover { text-decoration: underline; }
.foot { margin-top: 26px; border-top: 1px solid #ccc; padding-top: 8px; }
@media (max-width: 600px) { body { font-size: 15px; } pre, code { font-size: 12px; } }
""".strip()


def _example(raw: str, label: str = "request/response example") -> str:
    return (
        f"<details><summary>{html.escape(label)}</summary>"
        f"<pre>{html.escape(raw)}</pre></details>"
    )


def _torznab_example(base: str, name: str) -> str:
    host = base.split("//", 1)[-1] or "your-server:8080"
    raw = (
        f"GET /indexer/{name}/api?t=search&q=ubuntu HTTP/1.1\n"
        f"Host: {host}\n\n"
        "HTTP/1.1 200 OK\n"
        "Content-Type: application/xml\n\n"
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss xmlns:torznab="http://torznab.com/schemas/2015/feed" version="2.0">\n'
        "  <channel>\n"
        "    <title>Amarr</title>\n"
        '    <torznab:response offset="0" total="1"/>\n'
        "    <item>\n"
        "      <title>ubuntu-24.04-desktop-amd64.iso</title>\n"
        '      <enclosure url="magnet:?xt=urn:btih:..." length="6203170816"\n'
        '                 type="application/x-bittorrent"/>\n'
        '      <torznab:attr name="seeders" value="42"/>\n'
        '      <torznab:attr name="peers" value="50"/>\n'
        '      <torznab:attr name="size" value="6203170816"/>\n'
        "    </item>\n"
        "  </channel>\n"
        "</rss>"
    )
    return _example(raw)


def _endpoint_block(base: str, name: str, title: str, desc: str) -> str:
    api = f"{base}/indexer/{name}/api"
    api_attr = html.escape(api, quote=True)
    return (
        '<div class="endpoint">'
        f"<b>{html.escape(title)}</b> &mdash; {html.escape(desc)}<br>"
        f"<code>{html.escape(api)}</code>"
        "<ul>"
        f'<li><a href="{api_attr}?t=caps">caps</a> &mdash; indexer capabilities</li>'
        f'<li><a href="{api_attr}?t=search&amp;q=ubuntu">search</a> &mdash; search &laquo;ubuntu&raquo;</li>'
        f'<li><a href="{api_attr}?t=tvsearch&amp;q=the+expanse&amp;season=1&amp;episode=1">'
        "tvsearch</a> &mdash; TV show, season 1 episode 1</li>"
        "</ul>"
        f"{_torznab_example(base, name)}"
        "</div>"
    )


def _qbit_section() -> str:
    blocks = "\n".join(
        '<li class="endpoint">'
        f'<span class="m">{m}</span> <code>{html.escape(p)}</code> &mdash; {html.escape(d)}'
        f"{_example(ex)}"
        "</li>"
        for m, p, d, ex in _QBIT_ENDPOINTS
    )
    return f'<ul class="api">{blocks}</ul>'


def render_home(base: str, backends: List[str]) -> str:
    """Generates the HTML of the home page for the ``backends`` engines."""
    active = [b for b in SEARCH_BACKENDS if b in backends]

    blocks = [_endpoint_block(base, name, *_BACKEND_INFO[name]) for name in active]
    if active:
        blocks.append(
            _endpoint_block(
                base,
                "all",
                "All (all)",
                "Combines the results of all active engines.",
            )
        )
    endpoints_html = "\n".join(blocks) or (
        '<p class="muted">No active search engines.</p>'
    )

    # Note about the legacy /api endpoint (only makes sense if there are engines).
    legacy_note = ""
    if active:
        legacy_note = (
            f'<p class="muted">Also responds at <code>{html.escape(base + "/api")}</code> '
            "(legacy): equivalent to <code>amule</code> if active; otherwise "
            "<code>all</code>.</p>"
        )

    home_attr = html.escape(f"{base}/", quote=True)
    status_attr = html.escape(f"{base}/status", quote=True)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>amarr</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">
  <h1>amarr</h1>
  <p class="sub">aMule connector for Sonarr/Radarr &mdash; Torznab indexer and qBittorrent client.</p>

  <h2>Search indexers (Torznab)</h2>
  <p class="muted">Active endpoints according to your configuration. In Sonarr/Radarr, add one
  as a Torznab indexer using its URL.</p>
  {endpoints_html}
  {legacy_note}

  <h2>qBittorrent API (download client)</h2>
  <p class="muted">amarr emulates qBittorrent 2.8.19. Sonarr/Radarr use these routes
  automatically when you add it as a download client; you don't need to call them by hand.
  The download is always performed by aMule.</p>
  {_qbit_section()}

  <h2>Other endpoints</h2>
  <ul class="api">
    <li class="endpoint"><span class="m">GET</span> <a href="{home_attr}">/</a> &mdash;
        this page (HTML).</li>
    <li class="endpoint"><span class="m">GET</span> <a href="{status_attr}">/status</a> &mdash;
        aMule connection status (JSON).{_example(_STATUS_EXAMPLE)}</li>
    <li class="endpoint"><span class="m">GET</span> <code>/openapi.json</code> &mdash;
        OpenAPI schema (auto-generated by FastAPI).</li>
  </ul>

  <p class="foot muted">amarr &middot; search via aMule, eD2k or Kad &middot; download via aMule</p>
</div>
</body>
</html>"""


def render_details(
    hash_hex: str, name: str, size: int, seeders: int, peers: int
) -> str:
    """Details page for a result: basic data + ed2k link + magnet."""
    name = name or "(no name)"
    try:
        raw_hash = bytes.fromhex(hash_hex)
    except ValueError:
        raw_hash = b""
    ed2k = f"ed2k://|file|{name}|{size}|{hash_hex}|/"
    # Standard eD2k magnet (urn:ed2k) — the "real" one, valid in eD2k clients.
    ed2k_magnet = (
        f"magnet:?xt=urn:ed2k:{hash_hex.upper()}&dn={quote(name)}&xl={size}"
        if raw_hash
        else ""
    )
    # Synthetic magnet (urn:btih) that amarr hands to Sonarr/Radarr.
    magnet = str(MagnetLink.for_amarr(raw_hash, name, size)) if raw_hash else ""
    size_h = human_size(size) if size else "?"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(name)} · amarr</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">
  <h1>{html.escape(name)}</h1>
  <p class="sub">{html.escape(size_h)} &middot; {seeders} seeders &middot; {peers} sources</p>

  <h2>Info</h2>
  <ul>
    <li>Size: {html.escape(size_h)} ({size} bytes)</li>
    <li>eD2k hash: <code>{html.escape(hash_hex)}</code></li>
    <li>Complete sources (seeders): {seeders}</li>
    <li>Total sources (peers): {peers}</li>
  </ul>

  <h2>eD2k link</h2>
  <p><a href="{html.escape(ed2k, quote=True)}">open in eMule/aMule</a></p>
  <pre>{html.escape(ed2k)}</pre>

  <h2>eD2k Magnet</h2>
  <p><a href="{html.escape(ed2k_magnet, quote=True)}">open eD2k magnet</a></p>
  <pre>{html.escape(ed2k_magnet)}</pre>

  <h2>Fake Magnet Amarr</h2>
  <p class="muted">Synthetic magnet (<code>urn:btih</code>) that amarr hands to
  Sonarr/Radarr so they manage the download; the actual download is done by aMule.</p>
  <p><a href="{html.escape(magnet, quote=True)}">open magnet</a></p>
  <pre>{html.escape(magnet)}</pre>

  <p class="foot muted"><a href="/">&larr; amarr</a></p>
</div>
</body>
</html>"""


def build_home_router(backends: List[str]) -> APIRouter:
    """Router with the home page (``GET /``) and the details page (``GET /details``)."""
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        base = str(request.base_url).rstrip("/")
        return HTMLResponse(render_home(base, backends))

    @router.get("/details", response_class=HTMLResponse)
    def details(
        hash: str = Query(...),
        name: str = Query(""),
        size: int = Query(0),
        seeders: int = Query(0),
        peers: int = Query(0),
    ) -> HTMLResponse:
        return HTMLResponse(render_details(hash, name, size, seeders, peers))

    return router
