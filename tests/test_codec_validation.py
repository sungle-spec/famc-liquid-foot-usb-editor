"""Malformed-input and lossless-envelope regressions, using bundled records."""
from copy import deepcopy
from pathlib import Path

import pytest

from lfeditor.codec import Dump, Frame

FACTORY = Path(__file__).resolve().parents[1] / 'lfeditor/resources/factory/Factory_Defaults12.syx'


@pytest.fixture
def raw():
    return Dump.from_file(FACTORY).frames[0].to_bytes()


def test_dump_keeps_interframe_and_trailing_bytes_after_edit(raw):
    second = Dump.from_file(FACTORY).frames[1].to_bytes()
    data = b'prefix' + raw + b'gap\xf8' + second + b'tail\xf8'
    dump = Dump.from_bytes(data)
    assert dump.to_bytes() == data
    assert deepcopy(dump).to_bytes() == data
    dump.frames[0].values[0] = 65
    assert dump.to_bytes() == (b'prefix' + dump.frames[0].to_bytes() + b'gap\xf8' + second + b'tail\xf8')
    assert not dump.frames[0].to_bytes().endswith(b'gap\xf8')  # device writes remain frame-only


@pytest.mark.parametrize('tail', [b'\xf0', b'\xf0\x00\x00'])
def test_dump_rejects_truncated_last_frame(raw, tail):
    with pytest.raises(ValueError, match='unterminated'):
        Dump.from_bytes(raw + tail)


@pytest.mark.parametrize('data', [b'', b'not a sysex document', b'\xf0\x00'])
def test_dump_rejects_files_without_any_records(data):
    with pytest.raises(ValueError):
        Dump.from_bytes(data)


@pytest.mark.parametrize('offset,value', [(1, 0x01), (4, 0x06), (7, 0x10), (13, 0x11)])
def test_frame_rejects_bad_header_and_nibble_bytes(raw, offset, value):
    bad = bytearray(raw)
    bad[offset] = value
    with pytest.raises(ValueError):
        Frame.parse(bytes(bad))
