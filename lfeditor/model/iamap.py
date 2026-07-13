"""
IA-Map record (type 8). v6 record = 100 values; full name [0:16], nick [16:24].
value[24:84] = 60-cell button→IA-slot map (each cell = 0-based IA-slot index; the
"IA-Map Default" record is the identity map 0..59). Verified against the rig.
"""
from __future__ import annotations

from .base import Record

MAP_OFF = 24       # start of the 60-cell button -> IA-slot map
NUM_BUTTONS = 60


class IAMap(Record):
    has_name = True

    def slot_for_button(self, button: int) -> int:
        """0-based IA-slot index assigned to `button` (0-based)."""
        return self.values[MAP_OFF + button]
