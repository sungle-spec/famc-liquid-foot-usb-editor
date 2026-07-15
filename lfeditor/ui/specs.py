"""
Sectioned tab specs — the faithful LF+ Editor v6.31 layouts.

Each record tab is a `TabSpec` (rail + per-record header + columns of titled `Section`s); each
global (Config) tab is a `GlobalSpec` (no rail, Send/Get buttons, sections bound to a Config
record). Fields are the existing ui/fields.py editors, grouped to mirror the original's panels.
The codec/model are untouched: every edit writes into a record's `values` and re-encodes
losslessly. Midi/Groups and Pages are built as bespoke tabs (see ui/tabs/).
"""
from __future__ import annotations

from .fields import (
    HexBytesField, EnumField, FlagField, ToggleField, IAStateGridField,
    CommandTableField, StringField, ByteGridField, IntField, Int16Field, SlotPickerField,
    LabelGridField, ChannelNameField,
)
from .tabspec import Section, TabSpec, GlobalSpec   # Qt-free (so specs.py imports without PySide6)
from ..model.iamap import MAP_OFF as IAMAP_OFF, NUM_BUTTONS as IAMAP_BUTTONS
from ..model.page import (
    FUNC1_OFF, FUNC2_OFF, NUM_BUTTONS as PAGE_BUTTONS, BUTTON_PARAM_OFF,
)
from ..model.config import (
    COLOR_NAMES, CONFIG1_COLORS, PRESET_BTN_COLORS,
    GUITAR_TUNER_OFF, GUITAR_TUNERS, POWERUP_MODE_OFF, POWERUP_MODES, GLOBAL_FLAGS,
    POWERUP_PAGE_OFF, POWERUP_SONG_OFF, POWERUP_SETLIST_OFF, POWERUP_PRESET_OFF,
    EXT_DEVICE_OFF, TAP_TEMPO_TYPE_OFF, TAP_TEMPO_TYPES, TAP_TEMPO_SOURCE_OFF,
    TAP_TEMPO_SOURCES, TAP_TEMPO_BUTTON_OFF, SYSEX_ID_OFF, MIDI_CHANNEL_OFF,
    PHYS_BTN_START_OFF, HOLD_2ND_FUNC_OFF, HOLD_2ND_FUNC_TIMES, SCROLL_DELAY_OFF,
    EXCLUSIVE_GROUP_OFF, NUM_EXCLUSIVE_GROUPS, CHAN_BANK_PLUS1_OFF,
    CHAN_BANK_SEND_OFF, CHAN_BANK_MSB_OFF, CHAN_MAX_PRE_OFF, CHAN_MAX_PRE_STRIDE,
    CHAN_MAX_PRE_PLUS_ONE, NUM_MIDI_CHANNELS, GROUPED_IA_CONFIG_OFF,
    PRESET_PARAM_FLAGS, GUITAR_TUNER_FLAGS, EXT_SYNC_FLAGS, TAP_TEMPO_FLAGS,
    HARDWARE_FLAGS, EXTENDER_FLAGS, RESET_PAGE_ORDER_OFF, RESET_PAGE_ORDER,
    COMBO_BLOCK_OFF, COMBO_BLOCKS, NAME_SRC_OFF, TAP_AUTO_MSGS_OFF, TAP_LIGHT_ON_OFF,
    EXTENDER_TYPE_OFF, EXTENDER_DEVICE_ID_OFF, EXTENDER_HUB_OFF,
    EXTENDER_EXPANDER_CHAN_OFF, IA_DISPLAY_MAIN_LCD_OFF,
)
from ..model.preset import (
    IA_ONSTATE_OFF, DEFAULT_PAGE_OFF, IA_SLOT_MAP_OFF, NUM_IA_SLOTS, PRESET_FLAGS,
    CMDS_OFF, NUM_CMDS, CMD_FUNCS, STEP_NAMES_OFF, STEP_NAME_LEN, NUM_STEPS,
)
from ..model.song import (
    TRIGGER_TYPE_OFF, TRIGGER_TYPES, SLOT_OFF, NUM_SLOTS, SLOT_UNUSED,
    CMDS_OFF as SONG_CMDS_OFF, NUM_CMDS as SONG_NUM_CMDS,
    MTC_HOUR_OFF, MTC_MIN_OFF, MTC_SEC_OFF, MTC_FRAME_OFF, MTC_ENABLE_OFF, MTC_ENABLE_BIT,
)
from ..model.setlist import (
    END_CYCLE_OFF, END_CYCLES, SONG_SLOT_OFF, NUM_SONG_SLOTS, SONG_COUNT_OFF,
)
from ..model.iaswitch import (
    SWITCH_TYPE_OFF, ON_COLOR_OFF, OFF_COLOR_OFF, BYPASS_COLOR_OFF, BLOCKED_COLOR_OFF,
    SWITCH_TYPES, ON_CMDS_OFF, BYPASS_CMDS_OFF, NUM_CMDS as IA_NUM_CMDS,
    SYNC_DEVICE_OFF, GROUP_ID_OFF, ENABLE_OFF, ENABLE_BIT, PRESET_LABEL_OFF,
    SYNC_DEVICES, GROUP_IDS, PRESET_LABELS,
    SYNC_EFFECT_OFF, SYNC_EFFECTS, REMEMBER_STEP_OFF, REMEMBER_STEP_BIT,
    FORCE_STEP_OFF, FORCE_STEP_BIT, GLOBAL_IA_OFF, GLOBAL_IA_BIT,
    STEP_NAMES_OFF as IA_STEP_NAMES_OFF, STEP_NAME_LEN as IA_STEP_NAME_LEN,
    NUM_STEPS as IA_NUM_STEPS,
)

PAGE_OPTS = {0: "Use current page", **{n: f"Page {n:02}" for n in range(1, 51)}}
MAP_OPTS = {n: f"Map {n + 1:03}" for n in range(60)}
LAST_SONG_OPTS = {0: "ALL", **{n: str(n) for n in range(1, NUM_SONG_SLOTS + 1)}}
SYSEX_LINK_OPTS = {0: "NO LINK", **{n: f"SYX #{n:03d}" for n in range(1, 256)}}


# ----------------------------------------------------------------------------- record tabs
def _preset_tab() -> TabSpec:
    flags = [ToggleField(off, mask, label) for off, mask, label in PRESET_FLAGS]
    initial = Section("Initial IA States", [
        EnumField(DEFAULT_PAGE_OFF, "Default page", PAGE_OPTS),
        EnumField(IA_SLOT_MAP_OFF, "IA-slot map", MAP_OPTS),
    ] + flags, labeled=True)
    cmd = Section("Command Programming",
                  [CommandTableField(CMDS_OFF, NUM_CMDS, "", CMD_FUNCS)], labeled=False)
    steps = Section("Step Names",
                    [StringField(STEP_NAMES_OFF + i * STEP_NAME_LEN, STEP_NAME_LEN, f"Step {i+1}")
                     for i in range(NUM_STEPS)], labeled=True)
    ia_labels = Section("IA-Slot Defined Labels",
                        [LabelGridField(9, 10, "", cols=2)], labeled=False)
    map_labels = Section("Preset MAP Labels",
                         [LabelGridField(10, 20, "", cols=2)], labeled=False)
    ia_states = Section("MAP Label / Initial IA-Slot States",
                        [IAStateGridField(IA_ONSTATE_OFF, NUM_IA_SLOTS, "")], labeled=False)
    return TabSpec("Preset", 1, [[initial], [cmd, steps, ia_labels], [ia_states, map_labels]],
                   raw_from=24, default_row=0)


def _setlist_tab() -> TabSpec:
    params = Section("Set-List Parameters", [
        EnumField(SONG_COUNT_OFF, "Last Song Slot Used", LAST_SONG_OPTS),
        EnumField(END_CYCLE_OFF, "End of List Cycle Type", END_CYCLES),
    ], labeled=True)
    songs = Section("Song Definitions for the Set-List",
                    [SlotPickerField(SONG_SLOT_OFF, NUM_SONG_SLOTS, "", target_type=2, width=1,
                                     cols=5)], labeled=False)
    return TabSpec("Set-List", 5, [[params, songs]], raw_from=86)


def _iaslot_tab() -> TabSpec:
    settings = Section("IA Slot Settings", [
        ToggleField(ENABLE_OFF, ENABLE_BIT, "Enabled"),
        EnumField(SWITCH_TYPE_OFF, "Switch type", SWITCH_TYPES),
        EnumField(ON_COLOR_OFF, "On colour", COLOR_NAMES),
        EnumField(OFF_COLOR_OFF, "Off colour", COLOR_NAMES),
        EnumField(BYPASS_COLOR_OFF, "Bypass colour", COLOR_NAMES),
        EnumField(BLOCKED_COLOR_OFF, "Blocked colour", COLOR_NAMES),
        EnumField(GROUP_ID_OFF, "Group ID", GROUP_IDS),
        EnumField(PRESET_LABEL_OFF, "Preset label", PRESET_LABELS),
        EnumField(SYNC_DEVICE_OFF, "Sync device", SYNC_DEVICES),
        EnumField(SYNC_EFFECT_OFF, "Sync effect", SYNC_EFFECTS),
        ToggleField(GLOBAL_IA_OFF, GLOBAL_IA_BIT, "Global IA settings"),
        ToggleField(REMEMBER_STEP_OFF, REMEMBER_STEP_BIT, "Remember last step state"),
        ToggleField(FORCE_STEP_OFF, FORCE_STEP_BIT, "Force step #1 on preset change"),
    ], labeled=True)
    on_cmd = Section("On Command Programming",
                     [CommandTableField(ON_CMDS_OFF, IA_NUM_CMDS, "", CMD_FUNCS)], labeled=False)
    off_cmd = Section("BYPASS (OFF) Command Programming",
                      [CommandTableField(BYPASS_CMDS_OFF, IA_NUM_CMDS, "", CMD_FUNCS)], labeled=False)
    steps = Section("Step Names",
                    [StringField(IA_STEP_NAMES_OFF + i * IA_STEP_NAME_LEN, IA_STEP_NAME_LEN,
                                 f"Step {i+1}") for i in range(IA_NUM_STEPS)], labeled=True)
    return TabSpec("IA-Slot", 3, [[settings, steps], [on_cmd], [off_cmd]], raw_from=24)


def _iamap_tab() -> TabSpec:
    grid = Section("IA Slot Mapping",
                   [SlotPickerField(IAMAP_OFF, IAMAP_BUTTONS, "", target_type=3, width=1,
                                    cols=6)], labeled=False)
    return TabSpec("IA-Map", 8, [[grid]], raw_from=100)


def _songs_tab() -> TabSpec:
    slots = Section("Song Preset Definitions (and labels for 1-12)",
                    [SlotPickerField(SLOT_OFF, NUM_SLOTS, "", target_type=1, width=2,
                                     unused_raw=SLOT_UNUSED, cols=2)], labeled=False)
    labels = Section("LCD Button Labels (1-12)",
                     [LabelGridField(11, 12, "", cols=2)], labeled=False)
    cmd = Section("Command Programming",
                  [CommandTableField(SONG_CMDS_OFF, SONG_NUM_CMDS, "", CMD_FUNCS)], labeled=False)
    params = Section("Parameters", [
        EnumField(TRIGGER_TYPE_OFF, "Trigger type", TRIGGER_TYPES),
        ToggleField(MTC_ENABLE_OFF, MTC_ENABLE_BIT, "Enable MTC Mode"),
        IntField(MTC_HOUR_OFF, "Hour", 0, 23),
        IntField(MTC_MIN_OFF, "Min", 0, 59),
        IntField(MTC_SEC_OFF, "Sec", 0, 59),
        IntField(MTC_FRAME_OFF, "Frame", 0, 30),
    ], labeled=True)
    return TabSpec("Song", 2, [[slots, labels], [cmd, params]], raw_from=56)


def _sysex_tab() -> TabSpec:
    from .fields import MMCField
    data_field = HexBytesField(24, 16, "")
    data = Section("Sysex Message Data", [data_field],
                   note="DEC 0-128, or hex (&h). FF inside F0..F7 = checksum; FF outside = end.",
                   labeled=False)
    links = Section("Pre and Post Sysex Message Send Links", [
        EnumField(40, "Pre Sysex Link", SYSEX_LINK_OPTS),
        EnumField(41, "Post Sysex Link", SYSEX_LINK_OPTS),
    ], labeled=True)
    mmc = Section("Auto-Create MMC Messages", [MMCField(24, 16, data_field)], labeled=False)
    return TabSpec("Sysex Msg", 6, [[data, links, mmc]], raw_from=42)


RECORD_TABS: dict[str, TabSpec] = {
    "Presets": _preset_tab(),
    "Set-List": _setlist_tab(),
    "IA-Slot": _iaslot_tab(),
    "IA-Maps": _iamap_tab(),
    "Songs": _songs_tab(),
    "Sysex Msgs": _sysex_tab(),
}


# ----------------------------------------------------------------------------- global tabs
def _flags(group):
    return [ToggleField(off, mask, label) for off, mask, label in group]


def _global_tab() -> GlobalSpec:
    # Column 1 — Preset Parameters + Power-Up
    preset_params = Section("Preset Parameters", _flags(PRESET_PARAM_FLAGS), record=0)
    powerup = Section("Power-Up", [
        EnumField(POWERUP_MODE_OFF, "Mode", POWERUP_MODES),
        IntField(POWERUP_PAGE_OFF, "Page", 0, 49, plus_one=True),
        IntField(POWERUP_PRESET_OFF, "Preset (0=ignore)", 0, 384),
        IntField(POWERUP_SONG_OFF, "Song (0=ignore)", 0, 254),
        IntField(POWERUP_SETLIST_OFF, "Set-List (0=ignore)", 0, 128),
    ], record=0)

    # Column 2 — External Device Sync Items + Tap Tempo
    sync = Section("External Device Sync Items", [
        EnumField(GUITAR_TUNER_OFF, "Guitar tuner", GUITAR_TUNERS),
        *_flags(GUITAR_TUNER_FLAGS),
        IntField(NAME_SRC_OFF, "Name Src", 0, 255),
        IntField(EXT_DEVICE_OFF, "Ext. Model", 0, 255),
        *_flags(EXT_SYNC_FLAGS),
    ], record=0)
    tap = Section("Tap Tempo", [
        EnumField(TAP_TEMPO_SOURCE_OFF, "Source", TAP_TEMPO_SOURCES),
        EnumField(TAP_TEMPO_TYPE_OFF, "Type", TAP_TEMPO_TYPES),
        IntField(TAP_TEMPO_BUTTON_OFF, "Button", 0, 61),
        IntField(TAP_AUTO_MSGS_OFF, "Auto-Tap-Msgs", 0, 127),
        IntField(TAP_LIGHT_ON_OFF, "Tap Light ON Time", 0, 127),
        *_flags(TAP_TEMPO_FLAGS),
    ], record=0)

    # Column 3 — Hardware + Reset Page Button Order + Combo Button Blocking
    hardware = Section("Hardware", [
        ToggleField(46, 0x01, "MIDI Thru", invert=True),
        IntField(SYSEX_ID_OFF, "Sysex device ID", 0, 127),
        ToggleField(47, 0x01, "Allow MIDI in"),
        IntField(MIDI_CHANNEL_OFF, "MIDI channel", 0, 15, plus_one=True),
        IntField(PHYS_BTN_START_OFF, "Physical/Page Btn start", 0, 63, plus_one=True),
        EnumField(HOLD_2ND_FUNC_OFF, "2nd-function hold time", HOLD_2ND_FUNC_TIMES),
        IntField(SCROLL_DELAY_OFF, "Scroll delay", 0, 99),
        *_flags(HARDWARE_FLAGS),
    ], record=0)
    reset_order = Section("Reset Page Button Function Order",
                          [ToggleField(RESET_PAGE_ORDER_OFF, mask, label)
                           for mask, label in RESET_PAGE_ORDER], record=0)
    combo = Section("Combo Button Press Blocking",
                    [ToggleField(COMBO_BLOCK_OFF, mask, label)
                     for mask, label in COMBO_BLOCKS], record=0)

    # Column 4 — Extender
    extender = Section("Extender", [
        IntField(EXTENDER_TYPE_OFF, "Type", 0, 255),
        IntField(EXTENDER_DEVICE_ID_OFF, "Device ID", 0, 127),
        *_flags(EXTENDER_FLAGS),
        IntField(EXTENDER_HUB_OFF, "Hub connection", 0, 255),
        IntField(EXTENDER_EXPANDER_CHAN_OFF, "Expander via MIDI CHAN", 0, 15, plus_one=True),
    ], record=0)

    # Column 5 — LCD Behavior
    lcd = Section("LCD Behavior", [
        ToggleField(192, 0x01, "Reverse main display lines"),
        ToggleField(180, 0x02, "Line 1 state (UPPER/lower)"),
        ToggleField(117, 0x01, "Show 2nd function name"),
        ToggleField(180, 0x01, "Line 2 state (UPPER/lower)"),
        ToggleField(109, 0x01, "Show bypass as OFF on button"),
        ToggleField(110, 0x01, "Clear button LCD when off"),
        IntField(IA_DISPLAY_MAIN_LCD_OFF, "IA Display on Main LCD", 0, 255),
    ], record=0)

    return GlobalSpec("Global Settings", 4, [
        [preset_params, powerup],
        [sync, tap],
        [hardware, reset_order, combo],
        [extender],
        [lcd],
    ])


def _exp_pedals_tab() -> GlobalSpec:
    from ..model.expedal import (
        NUM_PEDALS, type_offset, cc_offset, chan_offset, PEDAL_TYPES,
        AUTO_CALIBRATE_OFF, BLOCK_RESET_OFF, FORCE_ZIPPER_OFF, MIN_SWEEP_OFF, MAX_SWEEP_OFF,
        TOE_TRIG_OFF, HEEL_TRIG_OFF, MAX_SWEEP_INVERT, SENS_LEVEL_OFF, SENS_LEVELS,
        PEDAL_FLAGS_OFF, BLK_HEELTOE_SENS_BIT, HIRES_MODE_BIT,
    )
    cols = []
    for p in range(NUM_PEDALS):
        sec = Section(f"Expression Pedal {p + 1}", [
            EnumField(type_offset(p), "Type", PEDAL_TYPES),
            IntField(cc_offset(p), "CC#", 0, 127),
            ChannelNameField(chan_offset(p), "Chan"),
            ToggleField(AUTO_CALIBRATE_OFF, 1 << p, "Auto-calibrate"),
            ToggleField(BLOCK_RESET_OFF, 1 << p, "Block reset"),
            ToggleField(FORCE_ZIPPER_OFF, 1 << p, "Force-zipper"),
            IntField(MIN_SWEEP_OFF + p, "CC sweep min", 0, 127),
            IntField(MAX_SWEEP_OFF + p, "CC sweep max", 0, 127, invert=MAX_SWEEP_INVERT),
            IntField(TOE_TRIG_OFF + p, "Toe trigger (0=none)", 0, 127),
            IntField(HEEL_TRIG_OFF + p, "Heel trigger (0=none)", 0, 127),
            EnumField(SENS_LEVEL_OFF + p, "Sensitivity", SENS_LEVELS),
            ToggleField(PEDAL_FLAGS_OFF + p, BLK_HEELTOE_SENS_BIT, "Blk Heel/Toe Sens"),
            ToggleField(PEDAL_FLAGS_OFF + p, HIRES_MODE_BIT, "Hi-Res Mode"),
        ], record=0)
        cols.append([sec])
    return GlobalSpec("Expression Pedals", 4, cols, live_calibrate=True)


def _colors_tab() -> GlobalSpec:
    # Function Button Colours, grouped into the original's four columns.
    groups = [
        ["Menu", "Enter / Select", "Change Page", "Context Up", "Context Down"],
        ["Preset Up", "Preset Down", "Current Mode", "Bank Up", "Bank Down"],
        ["Song Up", "Song Down", "SetList Up", "SetList Down", "Global Page"],
        ["Page Up", "Page Down", "Last Preset", "Save Preset", "Last Page"],
    ]
    func_cols = []
    for n, labels in enumerate(groups):
        title = "Function Button Colors" if n == 0 else " "
        sec = Section(title, [EnumField(CONFIG1_COLORS[lab], lab, COLOR_NAMES)
                              for lab in labels if lab in CONFIG1_COLORS], record=1)
        func_cols.append([sec])
    preset = Section("Preset Button Colors",
                     [EnumField(off, label, COLOR_NAMES) for label, off in PRESET_BTN_COLORS.items()],
                     record=0)
    return GlobalSpec("Colours", 4, func_cols + [[preset]])


GLOBAL_TABS: dict[str, GlobalSpec] = {
    "Global": _global_tab(),
    "Exp Pedals": _exp_pedals_tab(),
    "Colors": _colors_tab(),
}
