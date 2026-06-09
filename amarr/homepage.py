"""Página de inicio (``GET /``): documenta los endpoints activos con ejemplos.

Genera una página HTML minimalista (estilo Craigslist: plana, sans-serif,
enlaces azul/morado), responsive (móvil y PC). Solo lista los motores de
búsqueda **realmente activos** (según ``AMARR_SEARCH_BACKENDS``); los no
activados no aparecen. Cada endpoint incluye un ejemplo de petición/respuesta
plegable, al estilo de las páginas de ayuda de los servicios web SOAP de .NET.
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

# Nombre legible y descripción de cada motor.
_BACKEND_INFO = {
    "amule": ("aMule", "Búsqueda a través de un aMule externo (protocolo EC)."),
    "ed2k": (
        "Servidor eD2k",
        "Búsqueda directa en un servidor eD2k (implementada por amarr).",
    ),
    "kad": (
        "Red Kad",
        "Búsqueda serverless en la red Kad (implementada por amarr).",
    ),
}

# API qBittorrent emulada (la consume Sonarr/Radarr como cliente de descarga).
# Cada entrada: (método, ruta, descripción, ejemplo petición/respuesta).
# Debe reflejar las rutas reales de ``torrent/api.py`` (hay un test que lo verifica).
_QBIT_ENDPOINTS = [
    (
        "GET", "/api/v2/app/webapiVersion", "Versión de la WebAPI emulada (2.8.19).",
        "GET /api/v2/app/webapiVersion\n\n"
        "HTTP/1.1 200 OK\nContent-Type: text/plain\n\n2.8.19",
    ),
    (
        "POST", "/api/v2/auth/login", "Login (siempre aceptado; sin autenticación real).",
        "POST /api/v2/auth/login\nContent-Type: application/x-www-form-urlencoded\n\n"
        "username=admin&password=secret\n\nHTTP/1.1 200 OK\n\nOk.",
    ),
    (
        "GET", "/api/v2/app/preferences", "Preferencias de qBittorrent (incluye save_path).",
        "GET /api/v2/app/preferences\n\n"
        "HTTP/1.1 200 OK\nContent-Type: application/json\n\n"
        '{"save_path": "/finished", "max_active_downloads": 20, ...}',
    ),
    (
        "POST", "/api/v2/torrents/add", "Añade una descarga desde un magnet de amarr.",
        "POST /api/v2/torrents/add\nContent-Type: application/x-www-form-urlencoded\n\n"
        "urls=magnet:?xt=urn:btih:...&category=radarr\n\nHTTP/1.1 200 OK\n\nOk.",
    ),
    (
        "POST", "/api/v2/torrents/createCategory", "Crea una categoría.",
        "POST /api/v2/torrents/createCategory\n\n"
        "category=radarr&savePath=/finished\n\nHTTP/1.1 200 OK\n\nOk.",
    ),
    (
        "GET", "/api/v2/torrents/categories", "Lista las categorías.",
        "GET /api/v2/torrents/categories\n\n"
        "HTTP/1.1 200 OK\nContent-Type: application/json\n\n"
        '{"radarr": {"name": "radarr", "savePath": "/finished"}}',
    ),
    (
        "GET", "/api/v2/torrents/info", "Lista las descargas (estado, progreso, ETA…).",
        "GET /api/v2/torrents/info?category=radarr\n\n"
        "HTTP/1.1 200 OK\nContent-Type: application/json\n\n"
        '[{"hash": "0320c4...", "name": "ubuntu...iso", "progress": 0.5,\n'
        '  "state": "downloading", "eta": 1200, "save_path": "/finished"}]',
    ),
    (
        "POST", "/api/v2/torrents/delete", "Borra descargas (y, opcionalmente, sus ficheros).",
        "POST /api/v2/torrents/delete\n\n"
        "hashes=0320c4...&deleteFiles=true\n\nHTTP/1.1 200 OK\n\nOk.",
    ),
    (
        "GET", "/api/v2/torrents/files", "Ficheros de una descarga.",
        "GET /api/v2/torrents/files?hash=0320c4...\n\n"
        "HTTP/1.1 200 OK\nContent-Type: application/json\n\n"
        '[{"name": "ubuntu-24.04-desktop-amd64.iso"}]',
    ),
    (
        "GET", "/api/v2/torrents/properties", "Propiedades de una descarga.",
        "GET /api/v2/torrents/properties?hash=0320c4...\n\n"
        "HTTP/1.1 200 OK\nContent-Type: application/json\n\n"
        '{"hash": "0320c4...", "save_path": "/finished", "seeding_time": 1}',
    ),
]

# Ejemplo del endpoint de estado.
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


def _example(raw: str, label: str = "ejemplo de petición/respuesta") -> str:
    return (
        f"<details><summary>{html.escape(label)}</summary>"
        f"<pre>{html.escape(raw)}</pre></details>"
    )


def _torznab_example(base: str, name: str) -> str:
    host = base.split("//", 1)[-1] or "tu-servidor:8080"
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
        f'<li><a href="{api_attr}?t=caps">caps</a> &mdash; capacidades del indexador</li>'
        f'<li><a href="{api_attr}?t=search&amp;q=ubuntu">search</a> &mdash; buscar &laquo;ubuntu&raquo;</li>'
        f'<li><a href="{api_attr}?t=tvsearch&amp;q=the+expanse&amp;season=1&amp;episode=1">'
        "tvsearch</a> &mdash; serie, temporada 1 episodio 1</li>"
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
    """Genera el HTML de la página de inicio para los motores ``backends``."""
    active = [b for b in SEARCH_BACKENDS if b in backends]

    blocks = [_endpoint_block(base, name, *_BACKEND_INFO[name]) for name in active]
    if active:
        blocks.append(
            _endpoint_block(
                base,
                "all",
                "Todos (all)",
                "Combina los resultados de todos los motores activos.",
            )
        )
    endpoints_html = "\n".join(blocks) or (
        '<p class="muted">No hay motores de búsqueda activos.</p>'
    )

    # Nota del endpoint heredado /api (solo tiene sentido si hay motores).
    legacy_note = ""
    if active:
        legacy_note = (
            f'<p class="muted">También responde en <code>{html.escape(base + "/api")}</code> '
            "(heredado): equivale a <code>amule</code> si está activo; si no, a "
            "<code>all</code>.</p>"
        )

    home_attr = html.escape(f"{base}/", quote=True)
    status_attr = html.escape(f"{base}/status", quote=True)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>amarr</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">
  <h1>amarr</h1>
  <p class="sub">Conector aMule para Sonarr/Radarr &mdash; indexador Torznab y cliente qBittorrent.</p>

  <h2>Indexadores de búsqueda (Torznab)</h2>
  <p class="muted">Endpoints activos según tu configuración. En Sonarr/Radarr, añade uno
  como indexador Torznab usando su URL.</p>
  {endpoints_html}
  {legacy_note}

  <h2>API qBittorrent (cliente de descarga)</h2>
  <p class="muted">amarr emula qBittorrent 2.8.19. Sonarr/Radarr usan estas rutas
  automáticamente al añadirlo como cliente de descarga; no hace falta llamarlas a mano.
  La descarga siempre la realiza aMule.</p>
  {_qbit_section()}

  <h2>Otros endpoints</h2>
  <ul class="api">
    <li class="endpoint"><span class="m">GET</span> <a href="{home_attr}">/</a> &mdash;
        esta página (HTML).</li>
    <li class="endpoint"><span class="m">GET</span> <a href="{status_attr}">/status</a> &mdash;
        estado de la conexión con aMule (JSON).{_example(_STATUS_EXAMPLE)}</li>
    <li class="endpoint"><span class="m">GET</span> <code>/openapi.json</code> &mdash;
        esquema OpenAPI (autogenerado por FastAPI).</li>
  </ul>

  <p class="foot muted">amarr &middot; busca por aMule, eD2k o Kad &middot; descarga por aMule</p>
</div>
</body>
</html>"""


def render_details(
    hash_hex: str, name: str, size: int, seeders: int, peers: int
) -> str:
    """Página de detalles de un resultado: datos básicos + enlace ed2k + magnet."""
    name = name or "(sin nombre)"
    try:
        raw_hash = bytes.fromhex(hash_hex)
    except ValueError:
        raw_hash = b""
    ed2k = f"ed2k://|file|{name}|{size}|{hash_hex}|/"
    # Magnet eD2k estándar (urn:ed2k) — el "real", válido en clientes eD2k.
    ed2k_magnet = (
        f"magnet:?xt=urn:ed2k:{hash_hex.upper()}&dn={quote(name)}&xl={size}"
        if raw_hash
        else ""
    )
    # Magnet sintético (urn:btih) que amarr entrega a Sonarr/Radarr.
    magnet = str(MagnetLink.for_amarr(raw_hash, name, size)) if raw_hash else ""
    size_h = human_size(size) if size else "?"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(name)} · amarr</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">
  <h1>{html.escape(name)}</h1>
  <p class="sub">{html.escape(size_h)} &middot; {seeders} seeders &middot; {peers} fuentes</p>

  <h2>Datos</h2>
  <ul>
    <li>Tamaño: {html.escape(size_h)} ({size} bytes)</li>
    <li>Hash eD2k: <code>{html.escape(hash_hex)}</code></li>
    <li>Fuentes completas (seeders): {seeders}</li>
    <li>Fuentes totales (peers): {peers}</li>
  </ul>

  <h2>Enlace eD2k</h2>
  <p><a href="{html.escape(ed2k, quote=True)}">abrir en eMule/aMule</a></p>
  <pre>{html.escape(ed2k)}</pre>

  <h2>Magnet eD2k</h2>
  <p><a href="{html.escape(ed2k_magnet, quote=True)}">abrir magnet eD2k</a></p>
  <pre>{html.escape(ed2k_magnet)}</pre>

  <h2>Fake Magnet Amarr</h2>
  <p class="muted">Magnet sintético (<code>urn:btih</code>) que amarr entrega a
  Sonarr/Radarr para que gestionen la descarga; la descarga real la hace aMule.</p>
  <p><a href="{html.escape(magnet, quote=True)}">abrir magnet</a></p>
  <pre>{html.escape(magnet)}</pre>

  <p class="foot muted"><a href="/">&larr; amarr</a></p>
</div>
</body>
</html>"""


def build_home_router(backends: List[str]) -> APIRouter:
    """Router con la página de inicio (``GET /``) y la de detalles (``GET /details``)."""
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
