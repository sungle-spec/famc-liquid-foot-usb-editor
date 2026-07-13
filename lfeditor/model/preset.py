"""
Preset record (type 1).

v6.31 layout (each "value" = one decoded byte):
    0..15    full name (16 ASCII chars)        — verified
    16..23   nick name  (8 ASCII chars)         — verified (v6 addition)
    24..169  preset body                        — v6 reorganised vs the 2013 JAR; precise
                                                  offsets (tempo, initial IA states, on-preset
                                                  MIDI messages, IA-overrides) are mapped per
                                                  field by diffing live-editor exports.

The 2013 `Preset.java` is the semantic guide (tempo 31–250, 64 buttons as green/red
bitfields, 16 MIDI messages, expression pedals) but its byte offsets no longer line up
because v6 inserted the nick name and extra blocks. Until each offset is pinned by a diff,
the editor surfaces the verified name/nick and the raw value table; unmapped bytes round-trip
untouched (lossless), so edits are always safe.
"""
from __future__ import annotations

from .base import Record

NUM_IA_SLOTS = 60
BODY_OFF = 24  # start of the type-specific body, after full name + nick

# Verified v6 offsets (pinned via scripts/diff_dumps.py against the live editor):
IA_ONSTATE_OFF = 24   # 8-byte bitfield: initial IA-slot ON states (slot N -> bit)
DEFAULT_PAGE_OFF = 40  # 0 = use currently-active page, else page number
IA_SLOT_MAP_OFF = 158  # 0-based IA-map index used by this preset's page
STEP_NAMES_OFF = 44    # 4 step names x 8 ASCII chars
STEP_NAME_LEN = 8
NUM_STEPS = 4
CMDS_OFF = 76          # Command Programming: 16 entries x 4 bytes [func, b1, b2, b3]
NUM_CMDS = 16

# Command "Function" code (byte 0 of each 4-byte entry). Pinned against the 384-preset reference rig (v6) and validated
# across the 31.5k-preset corpus: func 0 (empty) is 94% of all entries, func 1 (MIDI message)
# is essentially all the rest of the *real* commands. The IA-trigger family (10..14) is rare in
# the corpus but confirmed on the reference rig (func 10 = IA ON trigger, b1 = IA-slot number). A handful of
# other special-function codes appear (<0.13%); they round-trip raw and show as "Fn N".
FUNC_EMPTY = 0
FUNC_MIDI = 1
# Programming-command function codes (the "Function" dropdown). RE'd byte-for-byte from LF+ Editor
# v6.31 by loading crafted presets (func bytes 0..67) and reading the names the editor displays —
# see docs/LF_DATA_MODEL.md. NOTE: codes 13/14 were previously mis-mapped (IA Resend / IA Set Step);
# the real IA Resend (map) is 21 and IA Set Step Number is 56.
CMD_FUNCS = {
    0: "Empty",
    1: "MIDI Command",
    2: "G-Tuner",
    3: "Step",
    4: "Sysex Send",
    5: "Delay ms",
    6: "Preset last used",
    7: "Page last used",
    8: "Page Change",
    9: "Preset trigger",
    10: "IA ON Trig (map)",
    11: "IA OFF Trig (map)",
    12: "IA Toggle (map)",
    13: "Set Color",
    14: "Preset Store",
    15: "Preset Recall Store",
    16: "Preset Trig 1st Button",
    17: "Go Global",
    18: "EXPR Mod CC#",
    19: "EXPR Send Value",
    20: "EXPR Resend Current",
    21: "IA Resend (map)",
    22: "EXPR Mod MIDI #",
    23: "System SnapShot",
    24: "System SnapShot 2",
    25: "EXPR Change IA trigger",
    26: "IA Force Color Change",
    27: "Activate MTC",
    28: "Set Status#1 LED",
    29: "Auto-Tap-Tempo",
    30: "Preset Resend IA",
    31: "Song # Store Current",
    32: "Song # Recall Store",
    33: "Song Change",
    34: "Page Toggle Function #1/#2",
    35: "EXPR Slot 2 MIDI",
    36: "EXPR Slot 2 CC",
    37: "EXPR Slot 2 Invert",
    38: "Device Sync",
    39: "IA-Map Change",
    40: "IF IA is OFF, Stop",
    41: "IF IA is ON, Stop",
    42: "IF IA is OFF, Skip",
    43: "IF IA is ON, Skip",
    44: "IF Processing Trigger",
    45: "Stop",
    46: "EXPR Min Send Value",
    47: "EXPR Max Send Value",
    48: "Page Button Display",
    49: "Page LOCK to current",
    50: "Page UNLOCK current",
    51: "Looper Turn On",
    52: "Looper Turn Off",
    53: "EXPR Slot 2 CLEAR",
    54: "Page Change to",
    55: "Preset Momentary then Jump",
    56: "IA Set Step Number",
    57: "PC# +",
    58: "PC# -",
    59: "PC# Save",
    60: "MIDI Clock (ms)",
    61: "MIDI Clock (BPM)",
    62: "IA Trigger",
    63: "IA Resend",
    64: "EXPR Block Xmit",
    65: "EXPR unBlock Xmit",
    66: "AXE3 Chan/State",
    67: "AXE3 Chg SCENE#",
}

# Functions whose b1 byte is an IA-slot / map number (shown as "… slot N").
_SLOT_FUNCS = {10, 11, 12, 21, 39, 56, 62, 63}

# For a MIDI Command (func == 1), b1 is the raw MIDI **status byte**: high nibble = message
# type, low nibble = channel (0-based). Confirmed: every func==1 entry in the corpus carries a
# valid 0x80-0xEF status byte (0 exceptions in 28,695 rows). Data layout per type:
#   Note Off/On, Poly Pressure, Control Change: b2 = data1, b3 = data2
#   Program Change: program = (b2 << 8) + b3  (b2 is 0 for normal gear, non-zero for AXE-FX's
#                   0..383 range — 8,759 corpus rows use the high byte)
#   Channel Pressure: b3 = pressure (single data byte)        Pitch Bend: value = (b3 << 7) | b2
MIDI_MSG_TYPES = {
    0x8: "Note Off", 0x9: "Note On", 0xA: "Poly Pressure", 0xB: "Control Change",
    0xC: "Program Change", 0xD: "Channel Pressure", 0xE: "Pitch Bend",
}


def decode_command(func: int, b1: int, b2: int, b3: int) -> str:
    """Human-readable one-line summary of a preset command entry (display-only; lossless raw
    bytes remain the source of truth)."""
    if func == FUNC_EMPTY:
        return ""
    if func == FUNC_MIDI:
        mtype, chan = b1 >> 4, (b1 & 0x0F) + 1
        name = MIDI_MSG_TYPES.get(mtype, f"status 0x{b1:02X}")
        if mtype == 0xC:   # Program Change
            return f"PC ch{chan} → prog {(b2 << 8) + b3}"
        if mtype == 0xB:   # Control Change
            return f"CC ch{chan} #{b2} = {b3}"
        if mtype == 0xD:   # Channel Pressure
            return f"Chan Pressure ch{chan} = {b3}"
        if mtype == 0xE:   # Pitch Bend
            return f"Pitch ch{chan} = {(b3 << 7) | b2}"
        if mtype in (0x8, 0x9, 0xA):  # Note Off / Note On / Poly Pressure
            return f"{name} ch{chan} note {b2} = {b3}"
        return f"{name} ch{chan} ({b2}, {b3})"
    name = CMD_FUNCS.get(func, f"Fn {func}")
    if func in _SLOT_FUNCS:
        return f"{name} slot {b1}"
    extra = " ".join(str(x) for x in (b1, b2, b3) if x)
    return f"{name} {extra}".strip()

# Boolean flags packed into two bytes (value index, bitmask, label) — diff-mapped.
PRESET_FLAGS: list[tuple[int, int, str]] = [
    (41, 0x01, "Resend IA-slot states"),
    (41, 0x02, "Resend globals"),
    (41, 0x04, "Replace global IAs w/ initial states"),
    (41, 0x10, "Act as IA-Slot (vs Preset)"),
    (41, 0x20, "Allow multi-presses (process steps/reset)"),
    (41, 0x80, "Reset button: non-preset function"),
    (42, 0x01, "IA effects"),
    (42, 0x02, "Process preset commands after IAs"),
    (42, 0x04, "Sync preset name (IN)"),
    (42, 0x08, "Reset button: preset function"),
    (42, 0x20, "Send as [bypass] for initial BLOCKED"),
    (160, 0x01, "Block exp pedal #1 until assigned"),
    (160, 0x02, "Block exp pedal #2 until assigned"),
    (160, 0x04, "Block exp pedal #3 until assigned"),
    (160, 0x08, "Block exp pedal #4 until assigned"),
]


class Preset(Record):
    has_name = True

    # --- initial IA-slot on/off states (bitfield at value[24:32]) ---
    def ia_on(self, slot: int) -> bool:
        """slot is 1-based (1..60)."""
        byte, bit = divmod(slot - 1, 8)
        return bool(self.values[IA_ONSTATE_OFF + byte] & (1 << bit))

    def set_ia_on(self, slot: int, on: bool) -> None:
        byte, bit = divmod(slot - 1, 8)
        off = IA_ONSTATE_OFF + byte
        if on:
            self.values[off] |= (1 << bit)
        else:
            self.values[off] &= ~(1 << bit) & 0xFF

    # --- command programming (16 rows x 4 bytes) ---
    def command(self, row: int) -> tuple[int, int, int, int]:
        """Return the raw (func, b1, b2, b3) tuple for command `row` (0-based)."""
        o = CMDS_OFF + row * 4
        return tuple(self.values[o:o + 4])  # type: ignore[return-value]

    def command_text(self, row: int) -> str:
        """Human-readable summary of command `row` ("" when empty)."""
        return decode_command(*self.command(row))

    @property
    def default_page(self) -> int:
        return self.values[DEFAULT_PAGE_OFF]

    @property
    def ia_slot_map(self) -> int:
        return self.values[IA_SLOT_MAP_OFF]
