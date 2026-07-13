"""Live expression-pedal stream parser — validated against bytes captured from a real LF+ 12+."""
import pytest

from lfeditor.comms.protocol import (
    parse_live_positions, live_view_start_frame, live_view_stop_frame, NUM_PEDALS,
    write_records_live, LIVE_WRITE_PRELUDE, WRITE_ACK,
)


def test_start_stop_frames():
    assert live_view_start_frame() == bytes.fromhex("f000007c0f0fd2f7")
    assert live_view_stop_frame() == bytes.fromhex("f000007c0f0fccf7")   # CC, same as leave-editor


def test_parse_real_capture():
    # exactly as captured: FE-delimited 8-byte frames, 4×16-bit big-endian positions
    cap = bytes.fromhex("fe0063003e01990199" "fe0064003d01990199" "fe")
    frames, leftover = parse_live_positions(cap)
    assert frames == [[0x63, 0x3E, 0x199, 0x199], [0x64, 0x3D, 0x199, 0x199]]
    assert all(len(f) == NUM_PEDALS for f in frames)
    # 99/100 = pedal-1 live position; 409 = uncalibrated pedals 3/4
    assert frames[0] == [99, 62, 409, 409]


def test_streaming_keeps_partial_tail():
    # a chunk that ends mid-frame: the tail must be retained for the next read
    chunk1 = bytes.fromhex("fe0063003e01990199" "fe0064")     # second frame incomplete
    frames, leftover = parse_live_positions(chunk1)
    assert frames == [[99, 62, 409, 409]]
    # feeding the rest completes the second frame
    frames2, _ = parse_live_positions(leftover + bytes.fromhex("003d01990199fe"))
    assert frames2 == [[100, 61, 409, 409]]


def test_parse_double_delimited_stream():
    # the real continuous stream double-delimits frames (… DATA FE FE DATA FE) — empty parts skip
    cap = bytes.fromhex("03ff019901990199" "fefe" "03ff019901990199" "fe")
    frames, _ = parse_live_positions(cap)
    assert frames == [[1023, 409, 409, 409]]   # pedal 1 volume-clamped at 0x3FF, others 409


def test_no_complete_frame_is_buffered():
    frames, leftover = parse_live_positions(bytes.fromhex("fe006300"))
    assert frames == []
    assert leftover == bytes.fromhex("fe006300")


class _FakeLiveTransport:
    """Echoes the real device: a config write during live view ACKs (F0 09 F7) after the LAST
    record, mixed into the continuing FE stream."""
    def __init__(self, ack=True):
        self.sent = []
        self._ack = ack
        self.flushed = 0

    def send(self, data):
        self.sent.append(bytes(data))

    def flush_input(self):
        self.flushed += 1

    def read_raw(self, idle_timeout=1.0, overall_timeout=10.0):
        stream = bytes.fromhex("03ff019901990199fe")
        return [stream + (WRITE_ACK if self._ack else b"") + stream]


def test_write_records_live_sends_prelude_then_frames_then_reads_ack():
    t = _FakeLiveTransport(ack=True)
    rec0 = bytes.fromhex("f000007c0004010000" "0f0a" + "00" * 4 + "f7")
    rec1 = bytes.fromhex("f000007c0004010001" "0f0a" + "00" * 4 + "f7")
    ok = write_records_live(t, [rec0, rec1], allow_write=True)
    assert ok is True
    # mirrors the original editor: a single 0xFF prelude, then each record back-to-back
    assert t.sent[0] == LIVE_WRITE_PRELUDE
    assert t.sent[1] == rec0 and t.sent[2] == rec1
    assert t.flushed == 1                       # cleared stale stream bytes before reading the ACK


def test_write_records_live_reports_missing_ack():
    t = _FakeLiveTransport(ack=False)
    assert write_records_live(t, [b"\xf0\x00\x00\x7c\x00\x04\x01\x00\x00\x0f\x0a\x00\x00\x00\x00\xf7"],
                              allow_write=True) is False


def test_write_records_live_refuses_without_allow_write():
    with pytest.raises(PermissionError):
        write_records_live(_FakeLiveTransport(), [b"\xf0\xf7"])
