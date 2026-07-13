"""
Re-order records with reference auto-rewrite — the original editor's pick/sort "Save / Sync".

Move the *content* of a record to a new position (shifting the records in between), then rewrite
every reference so it still points to the same logical record. Confidently handled references:
  * moving a **Preset** updates the **Song** preset-slot references that point to it;
  * moving a **Song** updates the **Set-List** song-slot references.

(The original also rewrites MOMENTARY/JUMP-TO-PRESET command references, but those command function
codes aren't reverse-engineered in this build, so command-table references are left untouched.)
"""
from __future__ import annotations

from .model.song import SLOT_OFF as SONG_PRESET_OFF, NUM_SLOTS as SONG_NUM_PRESETS, SLOT_UNUSED
from .model.setlist import SONG_SLOT_OFF, NUM_SONG_SLOTS

# moved record type -> (referencing type, slot offset, slot count, byte width, unused-raw or None)
REFERENCERS: dict[int, tuple[int, int, int, int, int | None]] = {
    1: (2, SONG_PRESET_OFF, SONG_NUM_PRESETS, 2, SLOT_UNUSED),
    2: (5, SONG_SLOT_OFF, NUM_SONG_SLOTS, 1, None),
}


def move_record(dump, type_: int, src_num: int, dst_num: int, sync_refs: bool = True) -> dict:
    """Move record #src_num's content to position #dst_num (1-based), shifting the rest. If
    `sync_refs`, rewrite references so they follow the moved content. Returns the permutation
    {old_number: new_number}."""
    recs = dump.records(type_)
    n = len(recs)
    if not (1 <= src_num <= n and 1 <= dst_num <= n):
        raise ValueError("position out of range")
    if src_num == dst_num:
        return {k: k for k in range(1, n + 1)}

    snap = [list(r.values) for r in recs]
    order = list(range(n))                 # order[slot] = original content index now at that slot
    order.insert(dst_num - 1, order.pop(src_num - 1))
    for slot, content in enumerate(order):
        recs[slot].values[:] = snap[content]

    perm = {content + 1: slot + 1 for slot, content in enumerate(order)}
    if sync_refs and type_ in REFERENCERS:
        rewrite_references(dump, type_, perm)
    return perm


def rewrite_references(dump, moved_type: int, perm: dict) -> int:
    """Apply a {old_number: new_number} permutation to every reference to `moved_type`. Returns the
    number of reference slots changed."""
    if moved_type not in REFERENCERS:
        return 0
    ref_type, off, count, width, unused = REFERENCERS[moved_type]
    changed = 0
    for rec in dump.records(ref_type):
        for i in range(count):
            o = off + width * i
            raw = (rec.values[o] | (rec.values[o + 1] << 8)) if width == 2 else rec.values[o]
            if unused is not None and raw == unused:
                continue
            new_num = perm.get(raw + 1)
            if new_num is not None and new_num - 1 != raw:
                v = new_num - 1
                rec.values[o] = v & 0xFF
                if width == 2:
                    rec.values[o + 1] = (v >> 8) & 0xFF
                changed += 1
    return changed
