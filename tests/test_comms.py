"""Offline tests for the device-comms layer (no hardware needed).

The protocol these exercise is hardware-confirmed against a real Liquid Foot+ (2026-06-15);
see docs/LF_USB_DIRECT.md. A FakeTransport stands in for the serial link.
"""
import pathlib

import pytest

from conftest import requires_rjm

from lfeditor.codec import Dump
from lfeditor.codec.frame import split_frames, Frame
from lfeditor.comms import (
    handshake_frame, read_command, connect, pull_records, pull_dump, send_record,
    select_preset, FOOT_READ_CMDS, MODEL_FOOT,
)
from lfeditor.comms import protocol
from lfeditor.comms.transport import split_sysex

ROOT = pathlib.Path(__file__).resolve().parent.parent


class FakeTransport:
    """Captures sent bytes; replays queued raw byte-blobs on read_raw/read_frames."""
    def __init__(self, replies=()):
        self.sent = []
        self._replies = list(replies)  # each item: bytes returned by one read

    def send(self, data):
        self.sent.append(bytes(data))

    def read_raw(self, idle_timeout=1.0, overall_timeout=10.0):
        if not self._replies:
            return []
        item = self._replies.pop(0)
        return [item] if item else []

    def read_frames(self, idle_timeout=1.0, overall_timeout=10.0):
        return split_sysex(b"".join(self.read_raw()))

    def close(self):
        pass


def test_handshake_frame_layout():
    f = handshake_frame(MODEL_FOOT)
    assert f[0] == 0xF0 and f[-1] == 0xF7
    assert list(f[:7]) == [0xF0, 0x00, 0x00, 0x7C, 0x0F, 0x0F, 0xC9]


def test_read_command_layout():
    f = read_command(0x05, MODEL_FOOT)
    assert list(f) == [0xF0, 0x00, 0x00, 0x7C, 0x0F, 0x0F, 0x05, 0xF7]


def test_connect_handshake_then_session_ctrl():
    # handshake reply on first read, then the CA session reply (empty) on the second
    t = FakeTransport(replies=[b"\xf0\x05\x00\x7c\x06\x20\xf7", b""])
    reply = connect(t, MODEL_FOOT, retries=3)
    assert reply.startswith(b"\xf0\x05\x00\x7c")
    # editor-faithful: handshake (C9) THEN the CA session-begin control
    assert t.sent[0] == handshake_frame(MODEL_FOOT)
    assert t.sent[1] == protocol.session_frame(MODEL_FOOT)
    assert list(t.sent[1]) == [0xF0, 0x00, 0x00, 0x7C, 0x0F, 0x0F, 0xCA, 0xF7]


def test_send_record_waits_for_ack():
    t = FakeTransport(replies=[b"\xf0\x09\xf7"])   # device ACK
    assert send_record(t, b"\xf0\x01\xf7", allow_write=True) is True
    t2 = FakeTransport(replies=[b""])              # no ACK
    assert send_record(t2, b"\xf0\x01\xf7", allow_write=True) is False


def test_exit_frame_and_disconnect():
    assert list(protocol.exit_frame(MODEL_FOOT)) == [0xF0, 0x00, 0x00, 0x7C, 0x0F, 0x0F, 0xCC, 0xF7]

    class T:
        def __init__(self): self.sent = []; self.closed = False
        def send(self, d): self.sent.append(bytes(d))
        def read_raw(self, **k): return []
        def close(self): self.closed = True
    t = T()
    protocol.disconnect(t, MODEL_FOOT)
    assert t.sent == [protocol.exit_frame(MODEL_FOOT)]  # CC sent before close
    assert t.closed is True


def test_send_record_blocked_by_default():
    t = FakeTransport(replies=[b"\xf0\x09\xf7"])  # device ACK for the allowed write
    with pytest.raises(PermissionError):
        send_record(t, b"\xf0\x00\xf7")
    assert t.sent == []  # nothing transmitted
    assert send_record(t, b"\xf0\x00\xf7", allow_write=True) is True
    assert t.sent == [b"\xf0\x00\xf7"]


def test_send_record_verify_readback():
    # write needs BOTH the ACK and a truthy read-back to count as confirmed
    t = FakeTransport(replies=[b"\xf0\x09\xf7"])
    assert send_record(t, b"\xf0\x01\xf7", allow_write=True, verify_read=lambda: True) is True
    t2 = FakeTransport(replies=[b"\xf0\x09\xf7"])  # ACK came, but read-back disagrees
    assert send_record(t2, b"\xf0\x01\xf7", allow_write=True, verify_read=lambda: False) is False


def test_select_preset_bank_and_program():
    t = FakeTransport()
    select_preset(t, 200)  # n=199 -> bank 1, prog 71
    assert t.sent[0] == bytes([0xB0, 0x00, 1])   # CC0 bank
    assert t.sent[1] == bytes([0xC0, 71])         # PC


def test_split_sysex():
    buf = b"\x00\xf0\x01\x02\xf7\xaa\xf0\x03\xf7"
    assert split_sysex(buf) == [b"\xf0\x01\x02\xf7", b"\xf0\x03\xf7"]


def _device_block(rtype, rlen, recs):
    """Build a fake device read-stream: concatenated decoded records + 1 status byte."""
    out = bytearray()
    for r in recs:
        out += bytes(r.values)
    out.append(0x00)  # trailing status byte the device appends
    return bytes(out)


@requires_rjm
def test_pull_records_segments_stream():
    """A get-command stream slices back into the right number of decoded records."""
    d = Dump.from_file(ROOT / "reference" / "sysex_dumps" / "RJM.syx")
    preset_recs = d.records(1)
    t = FakeTransport(replies=[_device_block(1, 170, preset_recs)])
    got = pull_records(t, MODEL_FOOT, cmds=[0x05])
    assert set(got) == {1}
    assert len(got[1]) == len(preset_recs)
    assert got[1][0] == preset_recs[0].values  # byte-exact decoded values


@requires_rjm
def test_pull_dump_synthesizes_writeable_frames():
    """pull_dump wraps decoded records into frames that re-encode to the .syx write format."""
    d = Dump.from_file(ROOT / "reference" / "sysex_dumps" / "RJM.syx")
    preset_recs = d.records(1)
    # connect() reads the handshake reply then the CA reply (empty), then the 0x05 stream:
    t = FakeTransport(replies=[b"\xf0\x05\x00\x7c\x06\x20\xf7", b"",
                               _device_block(1, 170, preset_recs)])
    dump = protocol.pull_dump(t, MODEL_FOOT, cmds=[0x05])
    assert len(dump.frames) == len(preset_recs)
    f0 = dump.frames[0]
    # the synthesised frame must re-encode byte-identically to the device's real frame
    real0 = split_frames((ROOT / "reference" / "sysex_dumps" / "RJM.syx").read_bytes())
    real0 = next(fr for fr in real0 if fr[5] == 1)
    assert f0.to_bytes() == real0
    assert dump.presets[0].name  # decodes as a real preset


@requires_rjm
def test_foot_read_cmd_map_consistent_with_codec():
    """Every read-command's record length matches the codec's decoded value-count."""
    d = Dump.from_file(ROOT / "reference" / "sysex_dumps" / "RJM.syx")
    for cmd, (rtype, rlen) in FOOT_READ_CMDS.items():
        recs = d.records(rtype)
        assert recs, f"no type-{rtype} records"
        assert len(recs[0].values) == rlen, f"cmd {cmd:#x}: {len(recs[0].values)} != {rlen}"
