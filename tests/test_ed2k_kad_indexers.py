"""Tests for the ed2k (server) and kad indexers with an injected search engine.

A ``search_fn`` is injected that returns ``SearchResult`` from the ``ed2k``
library, so the network is never touched.
"""
import logging

from amarr.ed2k import SearchResult
from amarr.magnet import MagnetLink
from amarr.torznab.indexer.ed2k_server import Ed2kServerIndexer
from amarr.torznab.indexer.kad import KadIndexer

_HASH = bytes(range(16))


def _sr(name, size=1000, sources=5, complete=2, h=_HASH):
    return SearchResult(
        file_hash=h, name=name, raw_name=name, size=size,
        sources=sources, complete_sources=complete,
    )


def test_ed2k_maps_results_and_builds_feed():
    sr = _sr("ubuntu.mkv", size=2000, sources=7, complete=3)
    feed = Ed2kServerIndexer(search_fn=lambda q: [sr]).search("ubuntu", 0, 100, [])
    assert feed.channel.response.total == 1
    item = feed.channel.item[0]
    assert item.title == "ubuntu.mkv"
    assert item.enclosure.url == str(MagnetLink.for_amarr(_HASH, "ubuntu.mkv", 2000))
    pairs = {(a.name, a.value) for a in item.attributes}
    assert ("seeders", "3") in pairs  # complete_sources
    assert ("peers", "7") in pairs    # sources
    assert ("size", "2000") in pairs


def test_ed2k_filters_non_video():
    ix = Ed2kServerIndexer(
        search_fn=lambda q: [_sr("a.mkv"), _sr("b.nfo"), _sr("c.zip")]
    )
    feed = ix.search("x", 0, 100, [])
    assert [i.title for i in feed.channel.item] == ["a.mkv"]


def test_ed2k_none_sources_become_zero():
    sr = _sr("a.mkv", sources=None, complete=None)
    feed = Ed2kServerIndexer(search_fn=lambda q: [sr]).search("x", 0, 100, [])
    pairs = {(a.name, a.value) for a in feed.channel.item[0].attributes}
    assert ("seeders", "0") in pairs
    assert ("peers", "0") in pairs


def test_ed2k_network_error_returns_empty_feed():
    def boom(_q):
        raise ConnectionError("server down")

    feed = Ed2kServerIndexer(search_fn=boom).search("x", 0, 100, [])
    assert feed.channel.response.total == 0
    assert feed.channel.item == []


def test_kad_uses_injected_engine():
    feed = KadIndexer(nodes_path="ignored", search_fn=lambda q: [_sr("movie.mp4")]).search(
        "movie", 0, 100, []
    )
    assert feed.channel.item[0].title == "movie.mp4"


def test_kad_value_error_returns_empty_feed():
    def boom(_q):
        raise ValueError("bad nodes.dat")

    feed = KadIndexer(nodes_path="x", search_fn=boom).search("x", 0, 100, [])
    assert feed.channel.response.total == 0
    assert feed.channel.item == []


def test_search_logs_raw_and_relevant_counts_in_debug(caplog):
    ix = Ed2kServerIndexer(search_fn=lambda q: [_sr("a.mkv"), _sr("b.nfo")])
    with caplog.at_level(logging.DEBUG, logger="amarr.torznab.ed2k"):
        ix.search("x", 0, 100, [])
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "raw" in messages  # DEBUG-mode diagnostic trace
