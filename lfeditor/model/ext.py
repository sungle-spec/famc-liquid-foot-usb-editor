"""
Extension records — the v6 "Ext" records that hold each parent's overflow text fields. They
carry NO name header; the whole record is an array of fixed-width 8-char ASCII labels. Each
extension is linked to its parent by record number (preset[N] ↔ Ext9[N] ↔ Ext10[N];
song[N] ↔ SongExt11[N]); a full rig has one of each per parent.

Reverse-engineered from the 124-file corpus (2026-06-15):
  - **PresetExt9 (type 9, 80B) = 10 × 8-char "IA-Slot Defined Labels"** — CONFIRMED by real
    content (e.g. "Basic", "Delay", "Driven", "Solo", "Swirly", …). These are the labels an
    IA-Slot's "Preset label" (1–10) selects.
  - **SongExt11 (type 11, 96B) = 12 × 8-char Song "LCD Button Labels"** (slots 1–12) — structure
    matches the editor's 12 label fields; space-filled (unused) throughout the corpus.
  - **PresetExt10 (type 10, 160B) = 20 × 8-char label store** — space-filled throughout the
    corpus; exact purpose unconfirmed (likely per-button MAP labels). Modelled as labels.
All three are space-initialised when empty; editing a label rewrites its 8-byte slot losslessly.
"""
from __future__ import annotations

from .base import Record
from ..text import decode_ascii, encode_ascii

LABEL_WIDTH = 8


class LabelRecord(Record):
    """An extension record that is purely a flat array of `count` 8-char ASCII labels."""
    has_name = False
    count = 0

    def label(self, i: int) -> str:
        return decode_ascii(self.frame.values, i * LABEL_WIDTH, LABEL_WIDTH)

    def set_label(self, i: int, text: str) -> None:
        off = i * LABEL_WIDTH
        self.frame.values[off:off + LABEL_WIDTH] = encode_ascii(text, LABEL_WIDTH)

    def labels(self) -> list[str]:
        return [self.label(i) for i in range(self.count)]


class PresetExt9(LabelRecord):
    """10 IA-Slot Defined Labels (8 chars each)."""
    count = 10


class PresetExt10(LabelRecord):
    """20-slot 8-char label store (purpose unconfirmed; round-trips losslessly)."""
    count = 20


class SongExt11(LabelRecord):
    """12 Song LCD Button Labels (8 chars each), for song preset slots 1–12."""
    count = 12
