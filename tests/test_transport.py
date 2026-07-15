"""Offline tests for SerialTransport.read_one_frame (no hardware needed).

Constructs SerialTransport via __new__ (bypassing __init__'s real serial.Serial() open) and
substitutes a fake `.ser` exposing just `in_waiting`/`read()`, mirroring pyserial's interface.
"""
from lfeditor.comms.transport import SerialTransport


class FakeSerial:
    """Replays a fixed byte string in fixed-size chunks, mimicking pyserial's `in_waiting`/`read`."""

    def __init__(self, data: bytes, chunk_size: int = 4):
        self._data = data
        self._pos = 0
        self._chunk_size = chunk_size

    @property
    def in_waiting(self) -> int:
        return min(self._chunk_size, len(self._data) - self._pos)

    def read(self, n: int) -> bytes:
        end = min(self._pos + n, len(self._data))
        chunk = self._data[self._pos:end]
        self._pos = end
        return chunk


def _transport(data: bytes, chunk_size: int = 4) -> SerialTransport:
    t = SerialTransport.__new__(SerialTransport)
    t.ser = FakeSerial(data, chunk_size)
    return t


def test_read_one_frame_returns_as_soon_as_the_terminator_arrives():
    """The whole point: stop at the FIRST complete frame, not after an idle gap — a second frame
    arriving immediately after (no gap, as on a busy/fast link) must NOT be merged in."""
    frame1 = bytes([0xF0, 0x00, 0x00, 0x7C, 0x01, 0x02, 0xF7])
    frame2 = bytes([0xF0, 0x00, 0x00, 0x7C, 0x03, 0x04, 0xF7])
    t = _transport(frame1 + frame2)
    got = t.read_one_frame(overall_timeout=3.0)
    assert got == frame1


def test_read_one_frame_ignores_leading_garbage():
    junk = bytes([0x00, 0xFF, 0x01])
    frame = bytes([0xF0, 0x00, 0x00, 0x7C, 0x09, 0xF7])
    t = _transport(junk + frame)
    got = t.read_one_frame(overall_timeout=3.0)
    assert got == frame


def test_read_one_frame_times_out_on_no_reply():
    t = _transport(b"")
    got = t.read_one_frame(overall_timeout=0.05)
    assert got == b""
