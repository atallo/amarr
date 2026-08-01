"""Tests for the AmuleIndexer (ported from ``AmuleIndexerTest.kt``)."""
from amarr.magnet import MagnetLink
from amarr.torznab.indexer.amule import AmuleIndexer

from .helpers import FakeAmuleClient, make_search_file

_HASH16 = bytes(range(16))


def _indexer(client=None):
    return AmuleIndexer(client or FakeAmuleClient())


def test_capabilities_single_category():
    caps = _indexer().capabilities()
    xml = caps.to_xml()
    assert "<categories>" in xml
    assert '<category id="1" name="All"/>' in xml


def test_empty_query_returns_single_placeholder():
    client = FakeAmuleClient()
    indexer = _indexer(client)
    feed = indexer.search("", 0, 1000, [])
    assert feed.channel.response.total == 1
    assert feed.channel.response.offset == 0
    assert len(feed.channel.item) == 1
    item = feed.channel.item[0]
    assert item.title == "No query provided"
    assert item.enclosure.url == "http://mock.url"
    assert item.enclosure.length == 0
    assert len(item.attributes) == 2
    assert item.attributes[0].name == "category" and item.attributes[0].value == "1"
    assert item.attributes[1].name == "size" and item.attributes[1].value == "0"
    # The client must not be queried.
    assert not hasattr(client, "last_query")


def test_query_calls_client_and_maps_result():
    client = FakeAmuleClient()
    sf = make_search_file("test.mkv", _HASH16, size_full=1000)
    client.search_files = [sf]
    indexer = _indexer(client)
    feed = indexer.search("test", 0, 1000, [])
    assert client.last_query == "test"
    assert feed.channel.response.total == 1
    item = feed.channel.item[0]
    assert item.title == "test.mkv"
    assert item.enclosure.url == str(
        MagnetLink.for_amarr(sf.hash, "test.mkv", sf.size_full)
    )
    assert item.enclosure.length == 1000
    pairs = {(a.name, a.value) for a in item.attributes}
    assert ("category", "1") in pairs
    assert ("size", "1000") in pairs
    assert ("seeders", "1") in pairs
    assert ("peers", "2") in pairs


def test_filters_non_video_results():
    client = FakeAmuleClient()
    client.search_files = [
        make_search_file("matrix.mkv", _HASH16),
        make_search_file("matrix.nfo", _HASH16),
        make_search_file("matrix.zip", _HASH16),
        make_search_file("matrix.mp3", _HASH16),
    ]
    feed = _indexer(client).search("matrix", 0, 1000, [])
    assert feed.channel.response.total == 1
    assert [i.title for i in feed.channel.item] == ["matrix.mkv"]


def test_normalizes_query_accents_and_punctuation():
    client = FakeAmuleClient()
    _indexer(client).search("C'est un complot", 0, 1000, [])
    assert client.last_query == "C est un complot"
