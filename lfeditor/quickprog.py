"""
Quick Repeated Command Programmer — the original editor's Utilities tool.

Write ONE programming command into a chosen command-table **row** across a **range** of records,
optionally auto-incrementing a Program-Change number as it goes (e.g. PC 0,1,2,… for a bank of
presets). Targets any of the four command areas the editor edits: preset commands, song commands,
IA-Slot ON commands, IA-Slot BYPASS commands. Pure logic — the dialog just builds the 4 command
bytes and calls `apply_command`.
"""
from __future__ import annotations

from .model.preset import (
    CMDS_OFF as PRESET_CMDS_OFF, NUM_CMDS as PRESET_NUM_CMDS, FUNC_MIDI,
)
from .model.song import CMDS_OFF as SONG_CMDS_OFF, NUM_CMDS as SONG_NUM_CMDS
from .model.iaswitch import ON_CMDS_OFF, BYPASS_CMDS_OFF, NUM_CMDS as IA_NUM_CMDS

# area key -> (record type, base offset, row count, label)
AREAS: dict[str, tuple[int, int, int, str]] = {
    "preset_cmd": (1, PRESET_CMDS_OFF, PRESET_NUM_CMDS, "Preset commands"),
    "song_cmd":   (2, SONG_CMDS_OFF, SONG_NUM_CMDS, "Song commands"),
    "ia_on":      (3, ON_CMDS_OFF, IA_NUM_CMDS, "IA-Slot ON commands"),
    "ia_bypass":  (3, BYPASS_CMDS_OFF, IA_NUM_CMDS, "IA-Slot BYPASS commands"),
}

PC_MSGTYPE = 0xC  # Program Change


def midi_command(msgtype: int, channel: int, data1: int, data2: int) -> list[int]:
    """Build a 4-byte MIDI command [func, status, b2, b3]. For Program Change (0xC) `data1` is the
    program number (0..16383, split high/low); otherwise data1/data2 are the two MIDI data bytes."""
    status = ((msgtype & 0xF) << 4) | ((channel - 1) & 0xF)
    if msgtype == PC_MSGTYPE:
        prog = data1 & 0x3FFF
        return [FUNC_MIDI, status, (prog >> 8) & 0xFF, prog & 0xFF]
    return [FUNC_MIDI, status, data1 & 0xFF, data2 & 0xFF]


def ia_command(func: int, slot: int) -> list[int]:
    """Build a 4-byte IA-trigger command (func 10..14); b1 holds the IA-slot number."""
    return [func & 0xFF, slot & 0xFF, 0, 0]


def empty_command() -> list[int]:
    return [0, 0, 0, 0]


def apply_command(dump, area: str, row: int, lo: int, hi: int, command,
                  pc_increment: bool = False) -> int:
    """Write `command` (4 bytes) into 1-based `row` of `area`'s table for every record whose number
    is in [lo, hi]. With `pc_increment` and a Program-Change command, the program number advances by
    one per record. Returns the number of records written."""
    type_, base, nrows, _label = AREAS[area]
    if not (1 <= row <= nrows):
        raise ValueError(f"row {row} out of range (1..{nrows}) for {area}")
    func, b1, b2, b3 = (list(command) + [0, 0, 0, 0])[:4]
    off = base + (row - 1) * 4
    is_pc = func == FUNC_MIDI and (b1 >> 4) == PC_MSGTYPE
    base_prog = (b2 << 8) | b3
    written = 0
    for rec in dump.records(type_):
        if not (lo <= rec.number <= hi):
            continue
        c2, c3 = b2, b3
        if pc_increment and is_pc:
            prog = (base_prog + written) & 0x3FFF
            c2, c3 = (prog >> 8) & 0xFF, prog & 0xFF
        o = off
        rec.values[o] = func & 0xFF
        rec.values[o + 1] = b1 & 0xFF
        rec.values[o + 2] = c2 & 0xFF
        rec.values[o + 3] = c3 & 0xFF
        written += 1
    return written
