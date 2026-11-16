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
from copy import copy

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
        n = _bounded_int(cell, 0, 384, "preset number")
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
        rec.values[SONG_SLOT_OFF + i] = _bounded_int(cell, 1, 254, "song number") - 1


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


def _bounded_int(cell: str, lo: int, hi: int, label: str) -> int:
    value = int(cell)
    if not lo <= value <= hi:
        raise ValueError(f"{label} out of range: {cell!r} ({lo}..{hi})")
    return value


def _parse_byte(cell: str, hexmode: bool) -> int:
    s = cell.strip().lower().replace("&h", "").replace("0x", "").replace("x", "")
    if s == "":
        return 0
    return int(s, 16) if hexmode else int(s)


def _sysex_apply(rec, row):
    rec.name = row[1].rstrip()
    rec.nick = row[2].rstrip()
    hexmode = row[3].strip().upper() != "D"
    rec.values[SYSEX_POST_OFF] = _bounded_int(row[4], 0, 255, "post link")
    rec.values[SYSEX_PRE_OFF] = _bounded_int(row[5], 0, 255, "pre link")
    for i, cell in enumerate(row[6:6 + SYSEX_NDATA]):
        value = _parse_byte(cell, hexmode)
        if not 0 <= value <= 255:
            raise ValueError(f"data byte out of range: {cell!r} (0..255)")
        rec.values[SYSEX_DATA_OFF + i] = value


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
            expected = len(spec["header"]())
            if len(row) != expected:
                raise ValueError(f"expected {expected} columns, got {len(row)}")
            # Parse a detached copy: a bad cell late in the row must not change the name or
            # earlier cells while reporting that the row was rejected.
            candidate_frame = copy(rec.frame)
            candidate_frame.values = list(rec.values)
            candidate = type(rec)(candidate_frame)
            spec["apply"](candidate, row)
            rec.values[:] = candidate.values
            applied += 1
        except (ValueError, IndexError) as exc:
            warnings.append(f"line {lineno} ({spec['label']} #{num}): {exc}")
    return applied, warnings


def import_csv(dump, kind: str, path: str) -> tuple[int, list[str]]:
    with open(path, "r", encoding="utf-8-sig") as fh:
        return import_text(dump, kind, fh.read())


# Backwards-compatible entry points; report formatting has its own module so import/export
# validation and read-only reporting can evolve independently.
from .reports import report_text, write_report  # noqa: E402,F401
