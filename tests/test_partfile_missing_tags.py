"""Regresión: aMule puede omitir tags EC en part-files/ficheros compartidos.

Un tag ausente (en producción, EC_TAG_PARTFILE_HASHED_PART_COUNT) hacía que
``from_subtags`` lanzase ``AttributeError: 'NoneType' object has no attribute
'get_value'`` y que ``GET /api/v2/torrents/info`` devolviera 500 en cuanto
había descargas activas. Con la lista de subtags vacía se ejercita la ruta
"tag ausente" de todos los campos a la vez.
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
    assert f.hashing_progress is False  # el tag que faltaba en producción
    assert f.a4af_auto is False
    assert f.source_count == 0
    assert f.file_cat == 0
    assert f.part_met_id is None
    assert f.size_done is None
    assert f.speed is None
