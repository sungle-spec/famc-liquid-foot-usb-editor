"""
Whole-record copy / paste / clear — mirrors the original LF+ Editor toolbar buttons.

Observed behaviour in LF+ Editor v6.31 (factory defaults, Presets tab):
  - **copy**  snapshots the *entire* current record into an internal buffer (NOT the system
              clipboard — verified the OS clipboard stays empty).
  - **paste** overwrites the current record's content with the buffer; the record's slot
              *number* is unchanged, but its name, commands, IA-states, flags — everything —
              become the copied record's. Only a record of the same type can be pasted.
  - **clear** resets the current record to its default: name "Preset #NNN", nick "Pre #NNN",
              all commands Empty, all IA-states Off, IA-Map = 1, Default Page = Use-Currently
              (i.e. a zeroed payload + a generated default name). The original confirms first.

A "whole record" includes the linked **extension records** (a preset's IA-Slot Defined Labels /
MAP labels, a song's preset labels), so copy/paste/clear carry those too — matching the original's
"copy whole preset".
"""
from __future__ import annotations

from dataclasses import dataclass

# main record type -> linked extension record types (1:1 by rec_num)
EXT_FOR: dict[int, list[int]] = {1: [9, 10], 2: [11]}

# singular labels used to generate a default name on clear
TYPE_SINGULAR: dict[int, str] = {
    1: "Preset", 2: "Song", 3: "IA-Slot", 5: "Set-List",
    6: "Sysex Msg", 7: "Page", 8: "IA-Map",
}


@dataclass
class RecordClip:
    """An internal whole-record snapshot: the main payload + each linked ext payload."""
    type_: int
    values: list[int]
    ext: dict[int, list[int]]   # ext_type -> values


def _linked_ext(dump, type_: int, rec_num: int) -> dict[int, list]:
    """The extension records (as wrapped Records) linked to a main record by rec_num."""
    out: dict[int, list] = {}
    for ext_type in EXT_FOR.get(type_, []):
        for r in dump.records(ext_type):
            if r.frame.rec_num == rec_num:
                out.setdefault(ext_type, []).append(r)
    return out


def snapshot(dump, rec, type_: int) -> RecordClip:
    """Copy: capture the record's full payload plus every linked extension payload."""
    ext_vals: dict[int, list[int]] = {}
    for ext_type, recs in _linked_ext(dump, type_, rec.frame.rec_num).items():
        # there is one ext record per type per rec_num, but store a list to be safe
        ext_vals[ext_type] = list(recs[0].values)
    return RecordClip(type_=type_, values=list(rec.values), ext=ext_vals)


def can_paste(clip: RecordClip | None, rec, type_: int) -> bool:
    return (clip is not None and clip.type_ == type_ and rec is not None
            and len(clip.values) == len(rec.values))


def apply_paste(dump, rec, type_: int, clip: RecordClip) -> bool:
    """Paste: overwrite the current record (and its linked ext records) from the buffer.

    The record's slot/number is preserved; only its content changes. Returns False (no-op)
    if the buffer isn't a same-type, same-length record.
    """
    if not can_paste(clip, rec, type_):
        return False
    rec.values[:] = clip.values
    for ext_type, vals in clip.ext.items():
        for r in _linked_ext(dump, type_, rec.frame.rec_num).get(ext_type, []):
            if len(r.values) == len(vals):
                r.values[:] = vals
    return True


def reset_record(dump, rec, type_: int) -> None:
    """Clear: reset the record (and linked ext records) to a blank default.

    Zeroes the payload, then writes the generated default name/nick. Preset-specific touch-ups
    (IA-Map = 1) match what the original editor produces on clear.
    """
    from ..model.base import NAME_LEN, NICK_OFF, NICK_LEN

    n = rec.number
    vals = rec.values
    for i in range(len(vals)):
        vals[i] = 0

    label = TYPE_SINGULAR.get(type_, "Record")
    rec.name = f"{label} #{n:03d}"

    if type_ == 1:  # Preset — matches the observed clear: "Pre #NNN" + IA-Map 1
        rec.nick = f"Pre #{n:03d}"
        from ..model.preset import IA_SLOT_MAP_OFF
        if len(vals) > IA_SLOT_MAP_OFF:
            vals[IA_SLOT_MAP_OFF] = 1

    # blank the linked extension records (labels) too
    for _ext_type, recs in _linked_ext(dump, type_, rec.frame.rec_num).items():
        for r in recs:
            ev = r.values
            for i in range(len(ev)):
                ev[i] = 0
