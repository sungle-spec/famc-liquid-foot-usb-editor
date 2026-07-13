"""
Song record (type 2). v6 record = 125 values; full name [0:16], nick [16:24], body from 24.
Offsets pinned via diff_dumps.py.
"""
from __future__ import annotations

from .base import Record

# Song "Command Programming": 8 entries × 4 bytes [func, b1, b2, b3] at value[24:56], the SAME
# encoding as the Preset command table (model/preset.py::decode_command). Pinned from the corpus:
# used songs carry rows like (1,192,0,4) = "PC ch1 → prog 4" and (8,n,0,0) = special functions.
# value[56:64] is reserved (never set across 20k corpus songs).
CMDS_OFF = 24
NUM_CMDS = 8

TRIGGER_TYPE_OFF = 64  # how the song triggers
TRIGGER_TYPES = {0: "Immediately", 1: "Arm only"}

# Song "Preset Definitions": 24 ordered slots, each a 2-byte little-endian preset reference.
# Stored value = preset_number - 1 (0-based); 0xFFFF = unused. Pinned by diff-RE: slot 1 set to
# Preset #300 wrote value[65]=43,[66]=1 → 43 + 1*256 = 299 → preset 300. (24*2 bytes = the 0xFF run.)
SLOT_OFF = 65
NUM_SLOTS = 24
SLOT_UNUSED = 0xFFFF

# MTC (MIDI Time Code) start position + enable — the Parameters panel's
# "Enable MTC Mode" rocker + Hour/Min/Sec/Frame steppers. Pinned by a clean single-record live
# diff (2026-06-15): setting Hour=1/Min=2/Sec=3/Frame=4 + enable changed exactly value[114..118].
MTC_HOUR_OFF = 114
MTC_MIN_OFF = 115
MTC_SEC_OFF = 116
MTC_FRAME_OFF = 117
MTC_ENABLE_OFF = 118
MTC_ENABLE_BIT = 0x01


class Song(Record):
    has_name = True

    @property
    def trigger_type(self) -> int:
        return self.values[TRIGGER_TYPE_OFF]
