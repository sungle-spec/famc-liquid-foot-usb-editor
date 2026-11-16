"""Read-only CSV reports shared by the desktop and web editors.

Report generation resolves names and commands without mutating the open document.
Round-trippable CSV import/export remains in :mod:`lfeditor.csvio`.
"""
from __future__ import annotations

import csv
import io

from .text import decode_ascii
from .model.song import SLOT_OFF as SONG_PRESET_OFF, NUM_SLOTS as SONG_NUM_PRESETS, SLOT_UNUSED
from .model.setlist import SONG_SLOT_OFF, NUM_SONG_SLOTS


def _fixed(values, off, length):
    return decode_ascii(values, off, length)


# --- reports (read-only, human readable) ----------------------------------------------------
def _names(dump, type_):
    return {r.frame.rec_num: (getattr(r, "name", "") or "").strip()
            for r in dump.records(type_)}


def report_text(dump, kind: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    if kind == "presets":
        from .model.preset import IA_SLOT_MAP_OFF, DEFAULT_PAGE_OFF, CMDS_OFF
        w.writerow(["Num", "Name", "Nickname", "IA-Map", "Default Page", "Commands", "ON slots"])
        for r in dump.records(1):
            ncmds = sum(1 for i in range(16) if r.values[CMDS_OFF + i * 4] != 0)
            on = [str(s + 1) for s in range(60) if r.ia_on(s)]
            w.writerow([r.number, r.name, r.nick, r.values[IA_SLOT_MAP_OFF],
                        r.values[DEFAULT_PAGE_OFF], ncmds, " ".join(on)])
    elif kind == "songs":
        pres = _names(dump, 1)
        w.writerow(["Num", "Name", "Nickname", "Presets", "Assigned (number: name)"])
        for r in dump.records(2):
            items = []
            for i in range(SONG_NUM_PRESETS):
                off = SONG_PRESET_OFF + 2 * i
                raw = r.values[off] | (r.values[off + 1] << 8)
                if raw != SLOT_UNUSED:
                    nm = pres.get(raw, "?")
                    items.append(f"{raw + 1}: {nm}")
            w.writerow([r.number, r.name, r.nick, len(items), " | ".join(items)])
    elif kind == "setlists":
        from .model.setlist import SONG_COUNT_OFF
        songs = _names(dump, 2)
        w.writerow(["Num", "Name", "Nickname", "Song count", "Songs (number: name)"])
        for r in dump.records(5):
            count = r.values[SONG_COUNT_OFF]
            items = []
            for i in range(min(count, NUM_SONG_SLOTS)):
                s = r.values[SONG_SLOT_OFF + i]
                nm = songs.get(s, "?")
                items.append(f"{s + 1}: {nm}")
            w.writerow([r.number, r.name, r.nick, count, " | ".join(items)])
    elif kind == "iaslots":
        _iaslot_report(dump, w)
    elif kind == "iamaps":
        _iamap_report(dump, w)
    else:
        raise ValueError(f"no report for {kind!r}")
    return buf.getvalue()


def _commands_text(values, start: int, count: int) -> tuple[int, str]:
    """(number of non-empty commands, "1. text | 2. text …") for a 4-byte-per-entry command table.
    Numbering is the table row, so it matches the row you see in the editor."""
    from .model.preset import decode_command
    items = []
    for i in range(count):
        f, b1, b2, b3 = values[start + i * 4:start + i * 4 + 4]
        if f:
            items.append(f"{i + 1}. {decode_command(f, b1, b2, b3)}")
    return len(items), " | ".join(items)


def _iaslot_report(dump, w) -> None:
    """One row per IA-Slot: settings plus the decoded ON and BYPASS command lists, for documenting
    a rig in a spreadsheet."""
    from .model import iaswitch as ia
    from .model.config import COLOR_NAMES
    from .model.sync_effects import sync_effect_name
    def _color(n):
        return str(COLOR_NAMES.get(n, n)).strip()

    w.writerow(["Num", "Name", "Nickname", "Enabled", "Switch type", "Group", "Global IA",
                "Sync device", "Sync effect", "On colour", "Off colour", "Bypass colour",
                "Blocked colour", "Steps", "ON cmd count", "ON commands",
                "BYPASS cmd count", "BYPASS commands"])
    for r in dump.records(3):
        v = r.values
        dev, eff = v[ia.SYNC_DEVICE_OFF], v[ia.SYNC_EFFECT_OFF]
        if dev == 0:
            sync_eff = ""
        else:
            sync_eff = sync_effect_name(dev, eff) or f"#{eff}"
        steps = [_fixed(v, ia.STEP_NAMES_OFF + i * ia.STEP_NAME_LEN, ia.STEP_NAME_LEN).strip()
                 for i in range(ia.NUM_STEPS)]
        n_on, on_txt = _commands_text(v, ia.ON_CMDS_OFF, ia.NUM_CMDS)
        n_by, by_txt = _commands_text(v, ia.BYPASS_CMDS_OFF, ia.NUM_CMDS)
        w.writerow([
            r.number, r.name, r.nick,
            "Yes" if v[ia.ENABLE_OFF] & ia.ENABLE_BIT else "No",
            ia.SWITCH_TYPES.get(v[ia.SWITCH_TYPE_OFF], v[ia.SWITCH_TYPE_OFF]),
            ia.GROUP_IDS.get(v[ia.GROUP_ID_OFF], v[ia.GROUP_ID_OFF]),
            "Yes" if v[ia.GLOBAL_IA_OFF] & ia.GLOBAL_IA_BIT else "No",
            ia.SYNC_DEVICES.get(dev, dev), sync_eff,
            _color(v[ia.ON_COLOR_OFF]),
            _color(v[ia.OFF_COLOR_OFF]),
            _color(v[ia.BYPASS_COLOR_OFF]),
            _color(v[ia.BLOCKED_COLOR_OFF]),
            " | ".join(x for x in steps if x),
            n_on, on_txt, n_by, by_txt,
        ])


def _iamap_report(dump, w) -> None:
    """One row per IA-Map: which IA-Slot each of the 60 buttons triggers, as "slot#: name"."""
    from .model.iamap import MAP_OFF, NUM_BUTTONS
    slots = _names(dump, 3)
    w.writerow(["Num", "Name", "Nickname", "Remapped buttons"]
               + [f"Btn {b + 1}" for b in range(NUM_BUTTONS)])
    for r in dump.records(8):
        cells, remapped = [], 0
        for b in range(NUM_BUTTONS):
            s = r.values[MAP_OFF + b]
            if s != b:
                remapped += 1
            nm = slots.get(s, "?")
            cells.append(f"{s + 1}: {nm}")
        w.writerow([r.number, r.name, r.nick, remapped] + cells)


def write_report(dump, kind: str, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write(report_text(dump, kind))
