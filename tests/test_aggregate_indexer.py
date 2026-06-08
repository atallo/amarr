"""Tests del AggregateIndexer (endpoint ``all``): fusión, dedup y paginación."""
from amarr.ed2k import SearchResult
from amarr.torznab.indexer.aggregate import AggregateIndexer
from amarr.torznab.indexer.ed2k_server import Ed2kServerIndexer


def _sr(name, h, size=1000):
    return SearchResult(
        file_hash=h, name=name, raw_name=name, size=size,
        sources=1, complete_sources=1,
    )


def _engine(results):
    return lambda _q: results


def test_merges_and_dedups_by_url():
    h1, h2, h3 = bytes([1]) * 16, bytes([2]) * 16, bytes([3]) * 16
    a = Ed2kServerIndexer(search_fn=_engine([_sr("a.mkv", h1), _sr("b.mkv", h2)]))
    b = Ed2kServerIndexer(search_fn=_engine([_sr("b.mkv", h2), _sr("c.mkv", h3)]))
    feed = AggregateIndexer([a, b]).search("x", 0, 100, [])
    assert sorted(i.title for i in feed.channel.item) == ["a.mkv", "b.mkv", "c.mkv"]
    assert feed.channel.response.total == 3  # b.mkv deduplicado


def test_offset_and_slicing():
    items = [_sr(f"f{i}.mkv", bytes([i]) * 16) for i in range(5)]
    feed = AggregateIndexer([Ed2kServerIndexer(search_fn=_engine(items))]).search(
        "x", 3, 10, []
    )
    assert feed.channel.response.offset == 3
    assert feed.channel.response.total == 5
    assert len(feed.channel.item) == 2  # items[3:5]


def test_empty_query_returns_placeholder():
    feed = AggregateIndexer([Ed2kServerIndexer(search_fn=_engine([]))]).search(
        "", 0, 100, []
    )
    assert feed.channel.item[0].title == "No query provided"


def test_one_engine_failure_is_ignored():
    def boom(_q):
        raise ConnectionError()

    good = Ed2kServerIndexer(search_fn=_engine([_sr("a.mkv", bytes([1]) * 16)]))
    bad = Ed2kServerIndexer(search_fn=boom)
    feed = AggregateIndexer([bad, good]).search("x", 0, 100, [])
    assert [i.title for i in feed.channel.item] == ["a.mkv"]
