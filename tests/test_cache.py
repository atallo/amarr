"""Tests for the search cache (SearchCache) and its use from the indexers."""
import amarr.cache as cache_mod
from amarr.cache import SearchCache
from amarr.ed2k import SearchResult
from amarr.jamule.response import SearchFile, SearchFileDownloadStatus
from amarr.torznab.indexer.ed2k_server import Ed2kServerIndexer


def _sf(name="a.mkv", h=bytes(range(16)), size=1000, c=2, p=5):
    return SearchFile(
        file_name=name, hash=h, size_full=size,
        download_status=SearchFileDownloadStatus.NEW,
        complete_source_count=c, source_count=p,
    )


def _sr(name="a.mkv", h=bytes(range(16)), size=1000):
    return SearchResult(
        file_hash=h, name=name, raw_name=name, size=size,
        sources=5, complete_sources=2,
    )


# --- SearchCache --------------------------------------------------------------


def test_put_get_roundtrip_preserves_fields(tmp_path):
    cache = SearchCache(str(tmp_path), ttl_seconds=3600)
    cache.put("kad", "ubuntu", [_sf("ubuntu.mkv", size=4242, c=7, p=9)])
    got = cache.get("kad", "ubuntu")
    assert got is not None and len(got) == 1
    r = got[0]
    assert r.file_name == "ubuntu.mkv"
    assert r.hash == bytes(range(16))
    assert r.size_full == 4242
    assert r.complete_source_count == 7
    assert r.source_count == 9


def test_miss_returns_none(tmp_path):
    assert SearchCache(str(tmp_path), 3600).get("kad", "nope") is None


def test_namespaced_by_backend(tmp_path):
    cache = SearchCache(str(tmp_path), 3600)
    cache.put("kad", "q", [_sf("k.mkv")])
    assert cache.get("ed2k", "q") is None  # different engine, same query -> miss
    assert cache.get("kad", "q") is not None


def test_creates_cache_db_file(tmp_path):
    SearchCache(str(tmp_path), 3600)
    assert (tmp_path / "cache.db").exists()


def test_ttl_zero_disables_cache(tmp_path):
    cache = SearchCache(str(tmp_path), ttl_seconds=0)
    cache.put("kad", "q", [_sf()])
    assert cache.get("kad", "q") is None


def test_expired_entry_is_a_miss(tmp_path, monkeypatch):
    cache = SearchCache(str(tmp_path), ttl_seconds=10)
    clock = [1000.0]
    monkeypatch.setattr(cache_mod.time, "time", lambda: clock[0])
    cache.put("kad", "q", [_sf()])
    assert cache.get("kad", "q") is not None  # within the TTL
    clock[0] += 11  # exceeds the 10 s TTL
    assert cache.get("kad", "q") is None


# --- use from the indexer -----------------------------------------------------


def test_indexer_reuses_cache_on_repeated_search(tmp_path):
    calls = []

    def engine(query):
        calls.append(query)
        return [_sr("a.mkv")]

    cache = SearchCache(str(tmp_path), ttl_seconds=3600)
    ix = Ed2kServerIndexer(search_fn=engine, cache=cache)
    ix.search("ubuntu", 0, 100, [])
    ix.search("ubuntu", 0, 100, [])  # 2nd time: must be served from the cache
    assert calls == ["ubuntu"]  # the engine was invoked only once


def test_indexer_does_not_cache_errors(tmp_path):
    calls = []

    def boom(query):
        calls.append(query)
        raise ConnectionError("server down")

    cache = SearchCache(str(tmp_path), ttl_seconds=3600)
    ix = Ed2kServerIndexer(search_fn=boom, cache=cache)
    ix.search("x", 0, 100, [])
    ix.search("x", 0, 100, [])  # the error is not cached -> it is retried
    assert len(calls) == 2
