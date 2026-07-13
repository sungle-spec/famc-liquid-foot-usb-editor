"""
MIDI command-message encoding shared by IA-Slot and Preset command grids.

Each message is 3 decoded bytes: [status, data1, data2], stored as real MIDI:
status high nibble = command, low nibble = channel (0-based). status 0x00 = empty slot.
"""
from __future__ import annotations

# command code (status high byte, channel masked out) -> editor label
MIDI_CMDS = {
    0x00: "—",
    0x80: "Note Off",
    0x90: "Note On",
    0xA0: "Poly Pressure",
    0xB0: "CC#",
    0xC0: "PC#",
    0xD0: "Aftertouch",
    0xE0: "Pitch Bend",
}


def decode_msg(values: list[int], off: int) -> tuple[int, int, int, int]:
    """Return (cmd_code, channel0, data1, data2) for the message at `off`.
    cmd_code is the status high byte (e.g. 0xB0 for CC#); channel0 is 0-based."""
    status = values[off]
    return status & 0xF0, status & 0x0F, values[off + 1], values[off + 2]
