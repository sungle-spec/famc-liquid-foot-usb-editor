"""
CSV import / export + reports — matches the original LF+ Editor's File ▸ Import/Export menus.

Column formats were captured byte-for-byte from LF+ Editor v6.31 (File ▸ Export, factory data):

  Presets   : Num, Name(16), Nickname(8), Slot#1..Slot#60     IA-state glyph O/-/B/X
  Songs     : Num, Name(16), Nickname(8), Preset#1..Preset#24 0 = none, else 1..384
  Set-Lists : Num, Name(16), Nickname(8), Song#1..Song#60      1..254
  Sysex     : Num, Name(16), Nickname(8), "D=Dec H=Hex", Post Link, Pre Link, Data 1..Data 16

All fields are quoted, Name is space-padded to 16 and Nickname to 8, the line terminator is `\n`.
Export reproduces that exactly; Import is tolerant (accepts unquoted, stripped, decimal-or-hex).

Reports (Reports menu) are read-only, human-readable CSV summaries that resolve cross-references
to names — distinct from the round-trippable Export above.
"""
from __future__ import annotations

import csv
import io

from .model.preset import IA_ONSTATE_OFF
from .model.song import SLOT_OFF as SONG_PRESET_OFF, NUM_SLOTS as SONG_NUM_PRESETS, SLOT_UNUSED
from .model.setlist import SONG_SLOT_OFF, NUM_SONG_SLOTS

# --- low-level fixed-width name/nick fields (preserve trailing spaces on export) ---
NAME_LEN, NICK_OFF, NICK_LEN = 16, 16, 8


def _fixed(values, off, length) -> str:
    return "".join(chr(c) if 32 <= c < 127 else " " for c in values[off:off + length])


def _ia_glyph(rec, slot0: int) -> str:
    # our model stores on/off; the original also writes B (bypass) / X (block) which we don't model
    return "O" if rec.ia_on(slot0) else "-"


def _set_ia_glyph(rec, slot0: int, glyph: str) -> None:
    rec.set_ia_on(slot0, glyph.strip().upper() == "O")


# --- per-kind header / row / apply ----------------------------------------------------------
def _preset_header():
    return ["Num", "Name", "Nickname"] + [f"Slot#{i}" for i in range(1, 61)]


def _preset_row(rec):
    return ([str(rec.number), _fixed(rec.values, 0, NAME_LEN), _fixed(rec.values, NICK_OFF, NICK_LEN)]
            + [_ia_glyph(rec, i) for i in range(60)])


def _preset_apply(rec, row):
    rec.name = row[1].rstrip()
    rec.nick = row[2].rstrip()
    for i, g in enumerate(row[3:63]):
        _set_ia_glyph(rec, i, g)


def _song_header():
    return ["Num", "Name", "Nickname"] + [f"Preset#{i}" for i in range(1, SONG_NUM_PRESETS + 1)]


def _song_row(rec):
    out = [str(rec.number), _fixed(rec.values, 0, NAME_LEN), _fixed(rec.values, NICK_OFF, NICK_LEN)]
    for i in range(SONG_NUM_PRESETS):
        off = SONG_PRESET_OFF + 2 * i
        raw = rec.values[off] | (rec.values[off + 1] << 8)
        out.append("0" if raw == SLOT_UNUSED else str(raw + 1))
    return out


def _song_apply(rec, row):
    rec.name = row[1].rstrip()
    rec.nick = row[2].rstrip()
    for i, cell in enumerate(row[3:3 + SONG_NUM_PRESETS]):
        n = int(cell)
        raw = SLOT_UNUSED if n == 0 else n - 1
        off = SONG_PRESET_OFF + 2 * i
        rec.values[off] = raw & 0xFF
        rec.values[off + 1] = (raw >> 8) & 0xFF


def _setlist_header():
    return ["Num", "Name", "Nickname"] + [f"Song#{i}" for i in range(1, NUM_SONG_SLOTS + 1)]


def _setlist_row(rec):
    out = [str(rec.number), _fixed(rec.values, 0, NAME_LEN), _fixed(rec.values, NICK_OFF, NICK_LEN)]
    for i in range(NUM_SONG_SLOTS):
        out.append(str(rec.values[SONG_SLOT_OFF + i] + 1))
    return out


def _setlist_apply(rec, row):
    rec.name = row[1].rstrip()
    rec.nick = row[2].rstrip()
    for i, cell in enumerate(row[3:3 + NUM_SONG_SLOTS]):
        rec.values[SONG_SLOT_OFF + i] = (int(cell) - 1) & 0xFF


SYSEX_DATA_OFF, SYSEX_NDATA = 24, 16
SYSEX_PRE_OFF, SYSEX_POST_OFF = 40, 41


def _sysex_header():
    return (["Num", "Name", "Nickname", "D=Dec H=Hex", "Post Link", "Pre Link"]
            + [f"Data {i}" for i in range(1, SYSEX_NDATA + 1)])


def _sysex_row(rec):
    out = [str(rec.number), _fixed(rec.values, 0, NAME_LEN), _fixed(rec.values, NICK_OFF, NICK_LEN),
           "H", str(rec.values[SYSEX_POST_OFF]), str(rec.values[SYSEX_PRE_OFF])]
    out += [f"{rec.values[SYSEX_DATA_OFF + i]:02X}" for i in range(SYSEX_NDATA)]
    return out


def _parse_byte(cell: str, hexmode: bool) -> int:
    s = cell.strip().lower().replace("&h", "").replace("0x", "").replace("x", "")
    if s == "":
        return 0
    return int(s, 16) if hexmode else int(s)


def _sysex_apply(rec, row):
    rec.name = row[1].rstrip()
    rec.nick = row[2].rstrip()
    hexmode = row[3].strip().upper() != "D"
    rec.values[SYSEX_POST_OFF] = int(row[4]) & 0xFF
    rec.values[SYSEX_PRE_OFF] = int(row[5]) & 0xFF
    for i, cell in enumerate(row[6:6 + SYSEX_NDATA]):
        rec.values[SYSEX_DATA_OFF + i] = _parse_byte(cell, hexmode) & 0xFF


KINDS = {
    "presets":  dict(type=1, label="Presets",   header=_preset_header,  row=_preset_row,  apply=_preset_apply),
    "songs":    dict(type=2, label="Songs",     header=_song_header,    row=_song_row,    apply=_song_apply),
    "setlists": dict(type=5, label="Set-Lists", header=_setlist_header, row=_setlist_row, apply=_setlist_apply),
    "sysex":    dict(type=6, label="Sysex",     header=_sysex_header,   row=_sysex_row,   apply=_sysex_apply),
}


# --- public API -----------------------------------------------------------------------------
def export_text(dump, kind: str) -> str:
    spec = KINDS[kind]
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(spec["header"]())
    for rec in dump.records(spec["type"]):
        w.writerow(spec["row"](rec))
    return buf.getvalue()


def export_csv(dump, kind: str, path: str) -> int:
    text = export_text(dump, kind)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write(text)
    return len(dump.records(KINDS[kind]["type"]))


def import_text(dump, kind: str, text: str) -> tuple[int, list[str]]:
    """Apply a CSV (matching the export format) onto the open dump. Returns (rows_applied, warnings).

    Records are matched by the 'Num' column to the record of that 1-based number. Rows whose Num is
    out of range are skipped with a warning; the header row is detected and ignored.
    """
    spec = KINDS[kind]
    by_num = {rec.number: rec for rec in dump.records(spec["type"])}
    applied, warnings = 0, []
    reader = csv.reader(io.StringIO(text))
    for lineno, row in enumerate(reader, 1):
        if not row or not row[0].strip():
            continue
        if row[0].strip().lower() == "num":      # header
            continue
        try:
            num = int(row[0])
        except ValueError:
            warnings.append(f"line {lineno}: bad record number {row[0]!r}")
            continue
        rec = by_num.get(num)
        if rec is None:
            warnings.append(f"line {lineno}: no {spec['label']} #{num} in the open file")
            continue
        try:
            spec["apply"](rec, row)
            applied += 1
        except (ValueError, IndexError) as exc:
            warnings.append(f"line {lineno} ({spec['label']} #{num}): {exc}")
    return applied, warnings


def import_csv(dump, kind: str, path: str) -> tuple[int, list[str]]:
    with open(path, "r", encoding="utf-8-sig") as fh:
        return import_text(dump, kind, fh.read())


# --- reports (read-only, human readable) ----------------------------------------------------
def _names(dump, type_):
    return [(getattr(r, "name", "") or "").strip() for r in dump.records(type_)]


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
                    nm = pres[raw] if raw < len(pres) else "?"
                    items.append(f"{raw + 1}: {nm}")
            w.writerow([r.number, r.name, r.nick, len(items), " | ".join(items)])
    elif kind == "setlists":
        from .model.setlist import SONG_COUNT_OFF
        songs = _names(dump, 2)
        w.writerow(["Num", "Name", "Nickname", "Song count", "Songs (number: name)"])
        for r in dump.records(5):
            count = r.values[SONG_COUNT_OFF]
            items = []
            for i in range(count if count else 0):
                s = r.values[SONG_SLOT_OFF + i]
                nm = songs[s] if s < len(songs) else "?"
                items.append(f"{s + 1}: {nm}")
            w.writerow([r.number, r.name, r.nick, count, " | ".join(items)])
    else:
        raise ValueError(f"no report for {kind!r}")
    return buf.getvalue()


def write_report(dump, kind: str, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write(report_text(dump, kind))
