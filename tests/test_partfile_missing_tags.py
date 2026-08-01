"""Regression: aMule may omit EC tags in part-files/shared files.

A missing tag (in production, EC_TAG_PARTFILE_HASHED_PART_COUNT) made
``from_subtags`` raise ``AttributeError: 'NoneType' object has no attribute
'get_value'`` and ``GET /api/v2/torrents/info`` return 500 as soon as
there were active downloads. With an empty subtag list the "missing tag"
path of all fields is exercised at once.
"""
from amarr.jamule.model import FileStatus, PartFileTag, SharedFileTag


def test_shared_file_from_empty_subtags_uses_defaults():
    f = SharedFileTag.from_subtags([])
    assert f.file_hash_hex_string is None
    assert f.file_name is None
    assert f.size_full is None
    assert f.up_prio == 0
    assert f.get_requests == 0
    assert f.get_all_xferred == 0
    assert f.get_complete_sources == 0
    assert f.get_rating is None


def test_part_file_from_empty_subtags_uses_defaults():
    f = PartFileTag.from_subtags([])
    assert f.file_status is FileStatus.UNKNOWN
    assert f.stopped is False
    assert f.hashing_progress is False  # the tag that was missing in production
    assert f.a4af_auto is False
    assert f.source_count == 0
    assert f.file_cat == 0
    assert f.part_met_id is None
    assert f.size_done is None
    assert f.speed is None
