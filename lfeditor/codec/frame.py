"""
Low-level FAMC Liquid Foot+ sysex frame codec.

A device backup (.syx) is a concatenation of frames, each one MIDI System Exclusive:

    F0 00 00 <ID> 00 <TYPE> <SUB> <NUM…> <LEN…> <nibble data> F7

Payload values are nibble-encoded (one byte -> high nibble, low nibble). v6.31 has no
trailing checksum (the 2013 firmware did). See docs/LF_PROTOCOL.md.

This module is pure and IO-free: bytes <-> Frame. It is the foundation the model and the
device-comms layer both sit on, and it round-trips every known dump byte-for-byte.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SYSEX_START = 0xF0
SYSEX_END = 0xF7

# Record type (byte 5) -> human name. See docs/LF_PROTOCOL.md.
TYPE_NAMES = {
    1: "Preset", 2: "Song", 3: "IASwitch", 4: "Config", 5: "Setlist", 6: "SysexMsg",
    7: "Page", 8: "IAMap", 9: "PresetExt9", 10: "PresetExt10", 11: "SongExt11",
}

# Per-type header layout for the v6.31 wire format, empirically fit against the device
# dumps and validated by byte-exact round-trip.
#   type -> (data_offset, length_field_hi_byte, record_number_is_4_nibbles)
# Types whose record count can exceed 255 carry a 4-nibble record number (bytes 7..10)
# with data at byte 13; the rest a 2-nibble number (bytes 7..8) with data at byte 11.
# The 2-nibble value-count sits in the two bytes immediately before the data.
TYPE_LAYOUT = {
    1:  (13, 11, True),
    2:  (11, 9, False),
    3:  (11, 9, False),
    4:  (11, 9, False),
    5:  (11, 9, False),
    6:  (11, 9, False),
    7:  (11, 9, False),
    8:  (11, 9, False),
    9:  (13, 11, True),
    10: (13, 11, True),
    11: (11, 9, False),
}


def nibbles_to_values(region: bytes) -> list[int]:
    """Decode a nibble-encoded byte region into logical byte values."""
    return [(region[k] << 4) | (region[k + 1] & 0xF) for k in range(0, len(region) - 1, 2)]


def values_to_nibbles(values: list[int]) -> bytearray:
    """Encode logical byte values into a nibble-encoded byte region."""
    out = bytearray()
    for v in values:
        out.append((v >> 4) & 0xF)
        out.append(v & 0xF)
    return out


@dataclass
class Frame:
    """One decoded FAMC sysex record.

    `values` is the decoded payload (one int per logical byte). `raw` keeps the exact
    original bytes so a frame we don't fully understand still re-encodes byte-identically.
    Edits go through `values`; `to_bytes()` rebuilds the header from `raw` and re-nibbles
    `values`, so unmapped fields are preserved automatically.
    """

    type: int
    sub: int
    rec_num: int
    dev_id: int
    values: list[int]
    raw: bytes = field(repr=False, default=b"")

    @property
    def name(self) -> str:
        return TYPE_NAMES.get(self.type, f"type{self.type}")

    @classmethod
    def parse(cls, frame: bytes) -> "Frame":
        if len(frame) < 13 or frame[0] != SYSEX_START or frame[-1] != SYSEX_END:
            raise ValueError("not a sysex frame")
        t = frame[5]
        if t not in TYPE_LAYOUT:
            raise ValueError(f"unknown record type {t}")
        data_off, len_hi, recnum4 = TYPE_LAYOUT[t]
        nv = (frame[len_hi] << 4) + (frame[len_hi + 1] & 0xF)
        expected = data_off + 2 * nv + 1
        if expected != len(frame):
            raise ValueError(
                f"type {t}: length field {nv} implies {expected} bytes, got {len(frame)}"
            )
        if recnum4:
            rec_num = (frame[7] << 12) + (frame[8] << 8) + (frame[9] << 4) + (frame[10] & 0xF)
        else:
            rec_num = (frame[7] << 4) + (frame[8] & 0xF)
        values = nibbles_to_values(frame[data_off: data_off + 2 * nv])
        return cls(type=t, sub=frame[6], rec_num=rec_num, dev_id=frame[3],
                   values=values, raw=bytes(frame))

    def to_bytes(self) -> bytes:
        """Re-encode this frame. Header comes from `raw`; payload from `values`."""
        data_off, _len_hi, _ = TYPE_LAYOUT[self.type]
        header = bytearray(self.raw[:data_off])
        body = values_to_nibbles(self.values)
        return bytes(header + body + bytes([SYSEX_END]))


def split_frames(data: bytes) -> list[bytes]:
    """Split a byte stream into raw F0..F7 frames (inclusive)."""
    frames: list[bytes] = []
    i, n = 0, len(data)
    while i < n:
        if data[i] != SYSEX_START:
            i += 1
            continue
        j = data.find(SYSEX_END, i + 1)
        if j == -1:
            break
        frames.append(data[i: j + 1])
        i = j + 1
    return frames
