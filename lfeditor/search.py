"""
Find / Q-LIST search — the original editor's FIND / EDIT / EXPORT window, as a pure engine.

Two kinds of query, combinable:
  * **Record filter** — restrict to record types + a 1-based number range, and an optional
    wildcard text match on name/nick ("Quick Search", `*`/`?` supported, case-insensitive).
  * **Command filter** — find records whose programming commands contain a MIDI message matching
    a channel / message-type / CC#-or-PC# (the original's "MIDI CHAN only" + "CHAN+ (CC#/PC#)").

Command tables scanned (same offsets the editor tabs use): Preset (16), Song (8), IA-Slot ON (20)
and BYPASS (20). One result row is produced per matching command (or per record for a name match).
Results are display-only; the dump is never modified.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from .model.preset import (
    CMDS_OFF as PRESET_CMDS_OFF, NUM_CMDS as PRESET_NUM_CMDS,
    FUNC_MIDI, MIDI_MSG_TYPES, decode_command,
)
from .model.song import CMDS_OFF as SONG_CMDS_OFF, NUM_CMDS as SONG_NUM_CMDS
from .model.iaswitch import ON_CMDS_OFF, BYPASS_CMDS_OFF, NUM_CMDS as IA_NUM_CMDS

TYPE_NAMES = {1: "Preset", 2: "Song", 3: "IA-Slot", 5: "Set-List", 6: "Sysex", 7: "Page", 8: "IA-Map"}
SEARCHABLE_TYPES = [1, 2, 3, 5, 6, 7, 8]

# record type -> list of (where-label, start offset, entry count); each entry is 4 bytes
CMD_SOURCES: dict[int, list[tuple[str, int, int]]] = {
    1: [("cmd", PRESET_CMDS_OFF, PRESET_NUM_CMDS)],
    2: [("cmd", SONG_CMDS_OFF, SONG_NUM_CMDS)],
    3: [("ON", ON_CMDS_OFF, IA_NUM_CMDS), ("BYPASS", BYPASS_CMDS_OFF, IA_NUM_CMDS)],
}

# message-type nibbles offered as command-search choices
MSG_TYPE_CHOICES = MIDI_MSG_TYPES  # {0x8: "Note Off", ... 0xE: "Pitch Bend"}


@dataclass
class Match:
    type_: int
    type_name: str
    number: int
    name: str
    where: str     # "name" | "cmd 3" | "ON cmd 5" | "BYPASS cmd 2"
    detail: str    # decoded command summary, or the matched name


def _text_matches(text: str, *fields: str) -> bool:
    pat = text.strip().lower()
    if not pat:
        return True
    use_glob = any(c in pat for c in "*?[")
    for f in fields:
        f = (f or "").lower()
        if use_glob:
            if fnmatch.fnmatch(f, pat):
                return True
        elif pat in f:
            return True
    return False


def _cmd_matches(b1: int, b2: int, b3: int, channel, msgtype, number) -> bool:
    """True if this MIDI command entry satisfies every *given* command criterion."""
    mtype, chan = b1 >> 4, (b1 & 0x0F) + 1
    if channel is not None and chan != channel:
        return False
    if msgtype is not None and mtype != msgtype:
        return False
    if number is not None:
        prog = (b2 << 8) + b3
        if mtype == 0xC:               # Program Change -> program number
            if prog != number:
                return False
        elif mtype == 0xB:             # Control Change -> CC#
            if b2 != number:
                return False
        else:                          # any other type: match either data byte / program
            if number not in (b2, b3, prog):
                return False
    return True


def _has_cmd_query(channel, msgtype, number) -> bool:
    return channel is not None or msgtype is not None or number is not None


def search(dump, *, text: str = "", types=None, num_min: int = 1, num_max: int = 99999,
           channel=None, msgtype=None, number=None, first_only: bool = False) -> list[Match]:
    """Return all matches. A record must pass the text filter AND (if any command criterion is set)
    contain a matching command. With no command criteria, name-matching records are returned."""
    types = set(SEARCHABLE_TYPES if types is None else types)
    cmd_query = _has_cmd_query(channel, msgtype, number)
    out: list[Match] = []

    for type_ in sorted(types):
        tname = TYPE_NAMES.get(type_, f"type{type_}")
        for rec in dump.records(type_):
            n = rec.number
            if not (num_min <= n <= num_max):
                continue
            name = (getattr(rec, "name", "") or "").strip()
            nick = (getattr(rec, "nick", "") or "").strip()
            if not _text_matches(text, name, nick):
                continue

            if not cmd_query:
                out.append(Match(type_, tname, n, name, "name", name or "(no name)"))
                continue

            # command query: emit a row per matching command (this record type must have commands)
            hits = 0
            for label, start, count in CMD_SOURCES.get(type_, []):
                for i in range(count):
                    o = start + i * 4
                    func, b1, b2, b3 = rec.values[o:o + 4]
                    if func != FUNC_MIDI:
                        continue
                    if _cmd_matches(b1, b2, b3, channel, msgtype, number):
                        where = f"{label} {i + 1}" if label != "cmd" else f"cmd {i + 1}"
                        out.append(Match(type_, tname, n, name, where,
                                         decode_command(func, b1, b2, b3)))
                        hits += 1
                        if first_only:
                            break
                if first_only and hits:
                    break
    return out


def results_csv(matches: list[Match]) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(["Type", "#", "Name", "Where", "Data"])
    for m in matches:
        w.writerow([m.type_name, m.number, m.name, m.where, m.detail])
    return buf.getvalue()
