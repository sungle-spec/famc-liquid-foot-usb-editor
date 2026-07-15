"""
IA-Switch record (type 3) — one IA slot. v6 record = 250 values; full name [0:16],
nick name [16:24], body from 24. Offsets pinned via diff_dumps.py against the live editor.
"""
from __future__ import annotations

from .base import Record

# Verified v6 offsets:
SWITCH_TYPE_OFF = 24    # behaviour of the slot
SYNC_DEVICE_OFF = 25    # external real-time-sync device
SYNC_EFFECT_OFF = 26    # effect slot within the sync'd device (Kemper etc.)
GROUP_ID_OFF = 28       # exclusive group (only one IA on per group)
GLOBAL_IA_OFF, GLOBAL_IA_BIT = 27, 0x80  # "Global IA Settings" flag (bit 7 of value[27])
# On/Bypass command tables: 20 entries of 4 bytes [func, b1, b2, b3] — the SAME format as preset
# commands (model/preset.py). Pinned by func-validity across all 180 IA-slots of the reference rig: entry byte 0 is
# a valid function code (0 / 1 / 2..67) only when the region starts at 29 / 109 (not 30 / 110). The
# old 30/110 read the MIDI *status* byte as the function (e.g. "Fn 176"), and a bogus "Group Post
# Trigger" field (then at 29) landed on the first command's func byte.
ON_CMDS_OFF = 29
BYPASS_CMDS_OFF = 109
# 4 step names x 8 ASCII chars, immediately after the command tables (109+20*4=189). Same layout
# as Preset's Step Names (model/preset.py STEP_NAMES_OFF/STEP_NAME_LEN); found via a real-device
# backup where every slot still held the factory default "STEP # 1".."STEP # 4" text — confirmed
# real by the adjacent REMEMBER_STEP/FORCE_STEP flags, which are meaningless without named steps.
STEP_NAMES_OFF = 189
STEP_NAME_LEN = 8
NUM_STEPS = 4
ENABLE_OFF, ENABLE_BIT = 221, 0x01           # slot enabled
REMEMBER_STEP_OFF, REMEMBER_STEP_BIT = 222, 0x01  # remember last step across power cycle
FORCE_STEP_OFF, FORCE_STEP_BIT = 231, 0x01   # force step #1 on preset change
ON_COLOR_OFF = 225      # colour when active + ON
OFF_COLOR_OFF = 226     # colour when active + OFF
BYPASS_COLOR_OFF = 227  # colour when active + BYPASS
BLOCKED_COLOR_OFF = 228  # colour when active + BLOCKED
PRESET_LABEL_OFF = 230  # 0 = use nick name, else preset-defined label number
NUM_CMDS = 20

SWITCH_TYPES = {
    0: "Stomp", 1: "Momentary", 2: "Step", 3: "Quick-Tap", 4: "Tap Tempo",
}
SYNC_DEVICES = {
    0: "None", 1: "Liquid Reserve 1", 2: "AXE-FX III", 3: "AXE-FX Ultra/II", 4: "KEMPER KPA",
}
GROUP_IDS = {0: "Not grouped", **{n: f"Group {n}" for n in range(1, 16)}}
PRESET_LABELS = {0: "No (use nick)", **{n: str(n) for n in range(1, 11)}}
SYNC_EFFECTS = {
    0: "Stomp A", 1: "Stomp B", 2: "Stomp C", 3: "Stomp D", 4: "Stomp X",
    5: "Stomp Mod", 6: "Stomp Delay", 7: "Stomp Reverb",
    8: "Performance Rig 1", 9: "Performance Rig 2", 10: "Performance Rig 3",
    11: "Performance Rig 4", 12: "Performance Rig 5",
    13: "Performance Up", 14: "Performance Down", 15: "Tap Tempo",
}


class IASwitch(Record):
    has_name = True

    @property
    def switch_type(self) -> int:
        return self.values[SWITCH_TYPE_OFF]

    @property
    def on_color(self) -> int:
        return self.values[ON_COLOR_OFF]

    @property
    def off_color(self) -> int:
        return self.values[OFF_COLOR_OFF]

    @property
    def bypass_color(self) -> int:
        return self.values[BYPASS_COLOR_OFF]

    @property
    def blocked_color(self) -> int:
        return self.values[BLOCKED_COLOR_OFF]
