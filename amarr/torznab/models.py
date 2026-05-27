"""Modelos Torznab (Caps y Feed) y su serialización XML (``torznab/model/*.kt``).

La API Torznab usa XML en lugar de JSON. Como la salida es sencilla y debe
controlar el prefijo de espacio de nombres ``torznab:``, se construye el XML a
mano con escapado correcto (en Kotlin lo hacía la librería ``xmlutil``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
from xml.sax.saxutils import escape, quoteattr

TORZNAB_NAMESPACE = "http://torznab.com/schemas/2015/feed"
TORZNAB_PREFIX = "torznab"

_XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>'


def _attrs(**pairs: object) -> str:
    """Construye una cadena de atributos XML con escapado."""
    return "".join(f" {k}={quoteattr(str(v))}" for k, v in pairs.items())


# --- Caps ---------------------------------------------------------------------


@dataclass
class Caps:
    """Capacidades del indexador Torznab."""

    server_version: str = "1.0"
    server_title: str = "Amarr"
    limits_max: int = 10000
    limits_default: int = 10000

    def to_xml(self) -> str:
        return (
            f"{_XML_DECL}\n"
            "<caps>"
            f"<server{_attrs(version=self.server_version, title=self.server_title)}/>"
            f"<limits{_attrs(max=self.limits_max, default=self.limits_default)}/>"
            "<searching>"
            f'<search{_attrs(available="yes", supportedParams="q", searchEngine="raw")}/>'
            f'<tv-search{_attrs(available="yes", supportedParams="q,season,ep", searchEngine="raw")}/>'
            f'<movie-search{_attrs(available="no", supportedParams="q", searchEngine="raw")}/>'
            f'<audio-search{_attrs(available="no", supportedParams="q", searchEngine="raw")}/>'
            f'<book-search{_attrs(available="no", supportedParams="q", searchEngine="raw")}/>'
            "</searching>"
            "<categories>"
            f'<category{_attrs(id=1, name="All")}/>'
            "</categories>"
            "</caps>"
        )


# --- Feed ---------------------------------------------------------------------


@dataclass
class Enclosure:
    url: str
    length: int
    type: str = "application/x-bittorrent"


@dataclass
class TorznabAttribute:
    name: str
    value: str


@dataclass
class Item:
    title: str
    enclosure: Enclosure
    attributes: List[TorznabAttribute] = field(default_factory=list)
    pub_date: str = "Sat, 14 Mar 2015 12:42:19 -0400"

    def to_xml(self) -> str:
        attrs_xml = "".join(
            f"<{TORZNAB_PREFIX}:attr{_attrs(name=a.name, value=a.value)}/>"
            for a in self.attributes
        )
        return (
            "<item>"
            f"<title>{escape(self.title)}</title>"
            f"<pubDate>{escape(self.pub_date)}</pubDate>"
            f"<enclosure{_attrs(url=self.enclosure.url, length=self.enclosure.length, type=self.enclosure.type)}/>"
            f"{attrs_xml}"
            "</item>"
        )


@dataclass
class Response:
    offset: int
    total: int


@dataclass
class Channel:
    response: Response
    item: List[Item] = field(default_factory=list)
    title: str = "Amarr"
    description: str = "Amarr 1.0"


@dataclass
class Feed:
    channel: Channel
    version: str = "2.0"

    def to_xml(self) -> str:
        items_xml = "".join(i.to_xml() for i in self.channel.item)
        return (
            f"{_XML_DECL}\n"
            f'<rss xmlns:{TORZNAB_PREFIX}="{TORZNAB_NAMESPACE}"{_attrs(version=self.version)}>'
            "<channel>"
            f"<title>{escape(self.channel.title)}</title>"
            f"<description>{escape(self.channel.description)}</description>"
            f"<{TORZNAB_PREFIX}:response{_attrs(offset=self.channel.response.offset, total=self.channel.response.total)}/>"
            f"{items_xml}"
            "</channel>"
            "</rss>"
        )
