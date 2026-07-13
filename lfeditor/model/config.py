"""
Global Config record (type 4). There are two type-4 records per device; the editor's
global tabs (Midi/Groups, Global, Exp Pedals, Colors) are all views onto them.

Offsets here are pinned by **diff-RE** (change one control in the real LF+ Editor, re-export,
diff — see scripts/diff_dumps.py). Verified so far: the Colours block in record #1.
"""
from __future__ import annotations

# --- Global settings in Config record #0 (diff-mapped) ---
# Hardware block — contiguous with the MIDI-Thru/Allow-MIDI toggles at 46/47:
#   value[48] = Sysex device ID, value[49] = global MIDI channel (0-based).
# Pinned by static analysis, not diff-RE: the live editor's NumericStepper controls reject
# synthetic input, so these were located by their known values and corroborated across all
# three device dumps. value[48]=124=0x7C is *self-confirming* — it equals the device-ID byte
# in every sysex frame header (F0 00 00 7C …). value[49]=15 → editor shows "MIDI Chan 16".
SYSEX_ID_OFF = 48          # device sysex ID (0..127); 124 = 0x7C, the frame-header ID byte
MIDI_CHANNEL_OFF = 49      # global MIDI channel, 0-based (0 → editor "1", 15 → "16")
# Hardware steppers — pinned by a clean single-pass diff (user changed only these three on real
# hardware-grade clicks, since the editor's NumericSteppers reject synthetic input):
PHYS_BTN_START_OFF = 44    # "Physical Btn / Page Btn (Start Value)", 0-based (display = value+1)
HOLD_2ND_FUNC_OFF = 106    # "2nd func hold time", encoded in 0.5 s units (value = seconds × 2)
HOLD_2ND_FUNC_TIMES = {1: "0.5s", 2: "1.0s", 3: "1.5s", 4: "2.0s", 5: "2.5s"}
SCROLL_DELAY_OFF = 107     # "Scroll Delay", raw (0..~30+)
GUITAR_TUNER_OFF = 104
GUITAR_TUNERS = {0: "Liquid Device", 1: "Axe-FX", 2: "Kemper KPA"}
POWERUP_MODE_OFF = 185
POWERUP_MODES = {0: "Last mode used", 1: "Preset", 2: "Song", 3: "Set-List"}
# Power-up targets (0 = ignore / use last, except page which is a 0-based index):
POWERUP_PAGE_OFF = 99      # 0-based page (0 = page 1)
POWERUP_SONG_OFF = 186     # 0 = ignore, else song number
POWERUP_SETLIST_OFF = 187  # 0 = ignore, else set-list number
POWERUP_PRESET_OFF = 189   # 0 = ignore, else preset number
EXT_DEVICE_OFF = 194       # external-device model override (0 = ignore; debug use)
TAP_TEMPO_TYPE_OFF = 118   # display type
TAP_TEMPO_TYPES = {0: "Actual BPM", 1: "Average BPM"}
TAP_TEMPO_SOURCE_OFF = 121  # beat source
TAP_TEMPO_SOURCES = {0: "Liquid Device", 1: "Axe-FX", 2: "Kemper KPA"}
TAP_TEMPO_BUTTON_OFF = 181  # 0 = no blink, 1 = auto-detect, 2..61 = force button 1..60

# Global boolean toggles (value index, bitmask, label). Polarity is the stored bit; for
# MIDI Thru the editor's "on" (green) corresponds to value 0 (noted inline).
# "Combo Button Press Blocking" — value[50], one bit per combo. MENU (bit 0) CONFIRMED by live
# diff (2026-06-15); PAGE/PRESET/SAVE-COPY (bits 1-3) inferred from panel order. 1 = block.
COMBO_BLOCK_OFF = 50
COMBO_BLOCKS = [(0x01, "MENU"), (0x02, "PAGE"), (0x04, "PRESET"), (0x08, "SAVE / COPY")]

# "Reset Page Button Function Order" — value[132], all three CONFIRMED by live diff (2026-06-15,
# chain 1->3->7): Bank Chg = bit 0, Song/Set Chg = bit 1, Page Chg = bit 2.
RESET_PAGE_ORDER_OFF = 132
RESET_PAGE_ORDER = [(0x01, "Bank change"), (0x02, "Song/Set change"), (0x04, "Page change")]

# Guitar-tuner / external-sync / tap-tempo flag groups — all CONFIRMED by live diff (2026-06-15).
GUITAR_TUNER_FLAGS = [
    (183, 0x80, "Blink display"),
    (183, 0x01, "Auto start"),
]
EXT_SYNC_FLAGS = [
    (135, 0x01, "Force changes"),
    (135, 0x02, "Save sync preset name"),
    (135, 0x04, "Save sync IA states"),
]
TAP_TEMPO_FLAGS = [
    (196, 0x01, "MIDI Clock Out enable"),
    (197, 0x01, "Show / send MIDI Clock OUT"),
    (198, 0x01, "Sync taps to MIDI Clock IN"),
    (118, 0x80, "IA-Slot toggle (tap tempo)"),  # shares value[118] with tap-tempo display type
]
# More single flags CONFIRMED by live diff (2026-06-15):
HARDWARE_FLAGS = [
    (182, 0x01, "Force 2nd function ASAP"),
]
EXTENDER_FLAGS = [
    (45, 0x01, "Extender 'End'"),
]
PRESET_PARAM_FLAGS = [
    (111, 0x01, "[OFF] IA's send [BYPASS] commands"),
    (100, 0x01, "Force IA Cmd send with Presets"),
    (112, 0x01, "Block Multiple Preset Presses"),
    (184, 0x01, "Block Boot-Up MIDI Transmission"),
]

# Global selector offsets CONFIRMED by user-assisted live diff (2026-06-15). These are
# enum/value steppers (option labels read from the editor's dropdowns; offsets verified).
NAME_SRC_OFF = 129               # External "Preset/Scene/Perf Name Src"
TAP_SOURCE_OFF = 121             # Tap Tempo source
TAP_AUTO_MSGS_OFF = 195          # Tap Tempo "Auto-Tap-Msgs"
TAP_LIGHT_ON_OFF = 199           # Tap Tempo "Tap Light ON Time"
EXTENDER_TYPE_OFF = 41           # Extender type (0 None / 1 Expansion connector / 2 MIDI)
EXTENDER_DEVICE_ID_OFF = 42      # Extender device ID
EXTENDER_HUB_OFF = 119           # Extender hub connection
EXTENDER_EXPANDER_CHAN_OFF = 201  # Expander via MIDI CHAN
IA_DISPLAY_MAIN_LCD_OFF = 188    # "IA Display on Main LCD"

GLOBAL_FLAGS = [
    (46, 0x01, "MIDI Thru disabled (1)"),   # green/on in editor = 0; checked = thru off
    (47, 0x01, "Allow MIDI in (Hardware)"),
    (109, 0x01, "Show bypass as OFF"),
    (110, 0x01, "Clear button LCD when off"),
    (117, 0x01, "Show 2nd function"),
    (180, 0x02, "Line 1 state (upper)"),
    (180, 0x01, "Line 2 state (upper)"),
    (182, 0x01, "Force 2nd function (Hardware)"),
    (192, 0x01, "Reverse main display"),
]

# Colour dropdown encoding, read directly from the editor's Colors combo box (0..15).
COLOR_NAMES: dict[int, str] = {
    0: "Off",
    1: "Green – Dim", 2: "Red – Dim", 3: "Yellow – Dim", 4: "Blue – Dim",
    5: "Cyan – Dim", 6: "Purple – Dim", 7: "White – Dim",
    8: "Off ",
    9: "Green – Bright", 10: "Red – Bright", 11: "Yellow – Bright", 12: "Blue – Bright",
    13: "Cyan – Bright", 14: "Purple – Bright", 15: "White – Bright",
}

# Verified colour-assignment offsets in Config record #1 (Colors tab → Function Button Colours).
# label -> value index. Each is individually pinned via diff_dumps.py.
#
# NOTE: the device's storage order is NOT the editor's visual grid order — e.g. "Change Page"
# lives at 147, not next to its grid neighbours. So every colour must be measured, not inferred.
# Extend this map one measured field at a time.
CONFIG1_COLORS: dict[str, int] = {
    "Menu": 128,
    "Enter / Select": 129,
    "Change Page": 147,
    "Context Up": 130,
    "Context Down": 131,
    "Preset Up": 132,
    "Preset Down": 133,
    "Current Mode": 146,
    "Bank Up": 134,
    "Bank Down": 135,
    "Song Up": 136,
    "Song Down": 137,
    "SetList Up": 138,
    "SetList Down": 139,
    "Global Page": 142,
    "Page Up": 140,
    "Page Down": 141,
    "Last Preset": 144,
    "Save Preset": 145,
    "Last Page": 143,
}

# "Preset as Button" colours live in Config record #0 (the global/numeric record), NOT the
# record-#1 colour block above — so they surface on the Global tab. Pinned by diff-RE.
PRESET_BTN_COLORS: dict[str, int] = {
    "Preset-btn Func 1 selected": 113,
    "Preset-btn Func 1 not selected": 114,
    "Preset-btn Func 2 selected": 133,
    "Preset-btn Func 2 not selected": 134,
}

# Midi/Groups settings that live in Config record #0 (the channel *names* are in record #1, but
# these are in #0, so they surface on the Global tab). Pinned by diff-RE.
EXCLUSIVE_GROUP_OFF = 122     # 7 "Exclusive Group Trigger IA" slots: value[122+i] = IA-slot # (0=none)
NUM_EXCLUSIVE_GROUPS = 7

# Per-MIDI-channel device config (the "MIDI Channel Device Configuration" grid). Each is a
# 16-bit-wide field expressed as two parallel bitfield bytes (ch1-8 / ch9-16), one bit/channel:
#   value[off] bit i  -> channel i+1   (channels 1-8)
#   value[off+1] bit i -> channel i+9  (channels 9-16)
NUM_MIDI_CHANNELS = 16
CHAN_BANK_PLUS1_OFF = 101     # "+1"      bitfield: value[101] ch1-8, value[102] ch9-16
CHAN_BANK_SEND_OFF = 144      # "BANK send" bitfield: value[144] ch1-8, value[145] ch9-16
CHAN_BANK_MSB_OFF = 146       # "BANK msb"  bitfield: value[146] ch1-8, value[147] ch9-16

# "Max Pre" (maximum preset number reachable on that channel): a per-channel 2-byte
# little-endian value, base+2*ch, where the *displayed* number is (low + high*256) + 1.
# e.g. stored (127,0) -> shows 128; (240,2) -> 752+1 = 753.
CHAN_MAX_PRE_OFF = 148        # 16 channels x 2 bytes = value[148..179]
CHAN_MAX_PRE_STRIDE = 2
CHAN_MAX_PRE_PLUS_ONE = 1

# "Grouped IA config": one bit per Exclusive Group in a single byte. bit n (1..7) = group #n;
# bit SET = "Break, then Make", bit CLEAR = "Make, then Break". bit0 is unused. The flag picks
# whether the group sends the selected IA-slot's ON commands before the others' BYPASS, or after.
GROUPED_IA_CONFIG_OFF = 105
GROUPED_IA_CONFIG = {0: "Make, then Break", 1: "Break, then Make"}

# The 16 MIDI-channel device names ("MR10", "Whammy1", …) live in Config record #1 as
# 8-char ASCII runs, channel i at value[i*8 : i*8+8].
CHAN_NAME_OFF = 0
CHAN_NAME_STRIDE = 8


def channel_names(dump) -> list[str]:
    """The 16 MIDI-channel device names from Config record #1 (stripped; "" where unnamed).

    Returns a fixed list of `NUM_MIDI_CHANNELS` entries even when the config record is absent,
    so callers can index it by channel without bounds checks."""
    from ..text import decode_ascii
    cfgs = dump.records(4) if dump is not None else []
    if len(cfgs) < 2:
        return ["" for _ in range(NUM_MIDI_CHANNELS)]
    v1 = cfgs[1].values
    return [decode_ascii(v1, ch * CHAN_NAME_STRIDE, CHAN_NAME_STRIDE)
            for ch in range(NUM_MIDI_CHANNELS)]
