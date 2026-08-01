"""EC protocol tests: packets, UTF-8 encoding and password hashing.

Ported from ``PacketParserTest``, ``EncodingTest``, ``PasswordHasherTest`` and the
``SamplePackets`` vectors of jaMule.
"""
import io

import pytest

from amarr.jamule.ec.codes import ECOpCode, ECTagName
from amarr.jamule.ec.encoding import read_utf8_number, ushort_to_bytes_utf
from amarr.jamule.ec.packet import PacketParser, PacketWriter
from amarr.jamule.ec.tag import TagEncoder, TagParser, UShortTag
from amarr.jamule.exceptions import InvalidECException
from amarr.jamule.password import hash_password
from amarr.jamule import request as req

# Vectors from ``SamplePackets.kt`` (hex -> description).
_AUTH_REQ = (
    "00000022000000240205c8800609614d756c65636d6400c8820606322e33"
    "2e330004030202041801001a0100"
)
_AUTH_SALT = "000000220000000d4f0116050855099a4aea510c43"
_AUTH_PASSWD = "00000022000000155001020910ca9026415e1a7df7ec0f7ec69678c150"
_AUTH_OK = "000000220000001d0401e0a8960616322e332e31204164756e616e7a4120323031322e3100"
_STATUS_REQ = "00000022000000060a0108020100"
_AUTH_FAIL = (
    "000000220000002c0301000627417574"
    "68656e7469636174696f6e206661696c"
    "65643a2077726f6e672070617373776f"
    "72642e00"
)
_SEARCH = "00000020000000192600010e03020000000d00010e040600000005746573740001"

_STATUS_RESPONSE = (
    "000000220000008c0c10d08003021664d082020100d484020100d4860302"
    "1664d488020100d48a020100d084020100d086020100d090020100"
    "d08c020100d092040400017cbbd09402010ad096040402e2740f"
    "d09803020438d0b60201000b023f03e0a881081f01e0a88206124"
    "16b74656f6e20536572766572204e6f3200b07de76247b50c0404"
    "1d4e48541404041d4e485419"
)
_MALFORMED_COMPRESSED = "000000230000000100"

_ALL_SAMPLES = [_AUTH_REQ, _AUTH_SALT, _AUTH_PASSWD, _AUTH_OK, _STATUS_REQ, _AUTH_FAIL, _SEARCH]


def _parser() -> PacketParser:
    return PacketParser(TagParser())


@pytest.mark.parametrize("hexstr", _ALL_SAMPLES)
def test_parses_sample_packets(hexstr):
    pkt = _parser().parse(io.BytesIO(bytes.fromhex(hexstr)))
    assert pkt is not None


def test_parses_status_response():
    pkt = _parser().parse(io.BytesIO(bytes.fromhex(_STATUS_RESPONSE)))
    assert pkt.op_code == ECOpCode.EC_OP_STATS
    assert len(pkt.tags) == 16
    # Tag equality excludes the value (parity with Kotlin); the real value
    # of the first tag is 0x1664 = 5732.
    assert pkt.tags[0] == UShortTag(ECTagName.EC_TAG_STATS_UL_SPEED, value=1664)
    assert pkt.tags[0].get_value() == 0x1664


def test_rejects_malformed_compressed_payload():
    with pytest.raises(InvalidECException):
        _parser().parse(io.BytesIO(bytes.fromhex(_MALFORMED_COMPRESSED)))


def test_decodes_utf8_value():
    assert read_utf8_number(bytes([0x01]), 0) == 1


def test_decodes_and_reencodes_same_value():
    encoded = ushort_to_bytes_utf(1, True)
    assert read_utf8_number(encoded, 0) == 1


def test_write_auth_passwd_byte_exact():
    enc = TagEncoder()
    pw = PacketWriter(enc)
    buf = io.BytesIO()
    pw.write(req.auth_request(bytes.fromhex("ca9026415e1a7df7ec0f7ec69678c150")), buf)
    assert buf.getvalue().hex() == _AUTH_PASSWD


def test_password_hash_vector():
    got = hash_password("amule", 0x55099A4AEA510C43)
    assert got == bytes.fromhex("ca9026415e1a7df7ec0f7ec69678c150")
