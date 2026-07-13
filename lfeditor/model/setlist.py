"""
Set-List record (type 5). v6 record = 90 values; full name [0:16], nick [16:24], body from 24.
Offsets pinned via diff_dumps.py.
"""
from __future__ import annotations

from .base import Record

# Set-List "Song Definitions": 60 ordered slots, each a 1-byte song reference (stored = song-1,
# 0-based; default 0 = song #1). Pinned by diff-RE: slot 1 set to Song #200 wrote value[24]=199.
SONG_SLOT_OFF = 24
NUM_SONG_SLOTS = 60

# Number of songs defined in this set-list (0..60). Only the first `value[84]` song slots are
# meaningful — the device ignores slots at or beyond this index, so empty set-lists keep
# value[84]=0 even when stale slot bytes remain. Confirmed across the whole reference corpus
# (9984 set-lists): value[84] never exceeds 60, and real hand-built lists (e.g. the v4.x PRO+
# 3-song lists, the Axe-Fx III 8-song templates) carry the exact count here.
SONG_COUNT_OFF = 84
END_CYCLE_OFF = 85  # what happens at the end of the set-list
# value[86:90] are reserved — always 0 across every set-list in the corpus.

END_CYCLES = {0: "Stop", 1: "Top → 1st song", 2: "Bottom ↔ Top"}


class Setlist(Record):
    has_name = True

    @property
    def song_count(self) -> int:
        return self.values[SONG_COUNT_OFF]

    @property
    def end_cycle(self) -> int:
        return self.values[END_CYCLE_OFF]
