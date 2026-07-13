"""
Page record (type 7) — a physical foot-controller button layout. v6 record = 210 values;
full name [0:16], nick [16:24].

The body holds parallel 60-entry button arrays (confirmed by diffing the Skrydstrup vs Kemper
pages, which differ exactly in these ranges):
  value[24:84]  = button "Function 1" assignments
  value[84:144] = button "Function 2" assignments
Each entry encodes a target (low values 1..~64 = system functions like Preset Up/Down; higher
values = IA-slot / preset references). A third 60-entry array at value[144:204] packs each
button's flags (mapped 2026-06-15, see BUTTON_PARAM_* below); value[204:210] is the page-param
block. Exposed as editable byte grids without over-claiming the per-entry function encoding.
"""
from __future__ import annotations

from .base import Record
from .config import COLOR_NAMES

FUNC1_OFF = 24
FUNC2_OFF = 84
NUM_BUTTONS = 60

# Per-button packed-flags array: value[144 + button] for button 0..59. Pinned by diff-RE
# (toggling one button-1 control at a time and watching value[144]):
#   bits 0-1 = Button Pressed Trigger Type   bit 2 = Function-1 "Trigger Scrolls"
#   bit 3   = Function-2 "Trigger Scrolls"    bit 6 = Enable Double-Tap
#   bit 7   = Button Press action (1 = Wait for Release, 0 = Immediate)
# (bits 4-5 unused in the reference rigs; the "IA Map to use for Display" dropdown is editor-
#  display-only and writes no byte.)
BUTTON_PARAM_OFF = 144
BTN_TRIGGER_TYPE_MASK = 0x03
BTN_TRIGGER_TYPES = {0: "Toggle & Trigger", 1: "Trigger Only", 2: "Toggle Only"}
BTN_FUNC1_SCROLLS_BIT = 0x04
BTN_FUNC2_SCROLLS_BIT = 0x08
BTN_DOUBLE_TAP_BIT = 0x40
BTN_WAIT_RELEASE_BIT = 0x80

# Page-parameter block near the end of the record. Re-verified byte-for-byte by live hardware
# diff on a real LF+ 12+ (fw 6.32, 2026-06-16) — this corrected three earlier mis-maps (the
# menu-trigger, all-buttons-double-tap, and preset-button-colour bytes were previously wrong).
STATUS1_LED_OFF = 204     # "Status #1 LED" colour (COLOR_NAMES 0..15)
FORCE_MODE_OFF = 205      # "Force Mode Change" packed byte; bit 0x02 = "all buttons double tap"
ALL_BTN_DBL_BIT = 0x02    #   (live diff: toggling double-tap set value[205] 0 -> 2)
MENU_TRIGGER_OFF = 206    # "menu button trigger" (0 = "B2+B3=Menu", 1..60 = trigger button #)
FORCE_IA_MAP_OFF = 207    # "Force IA Map" (map number; 0 = none) — live-confirmed 0 -> 7
# "Preset-button colours": one packed byte, low nibble = SELECTED colour, high nibble = NOT-
# SELECTED colour (COLOR_NAMES nibble; 0 = "Use Global Settings"). Live diff: selected Green-Dim
# + not-sel Red-Dim -> value[208] = 0x21. (This byte was previously mis-mapped as an IA-slot ref.)
PRESET_BTN_COLORS_OFF = 208
IA_SLOT_TRIG_NUM_OFF = 209  # "IA-Slot to Trigger" slot number (0 = none, 1..60) — live-confirmed 0 -> 7
# Preset-button colour enum: like COLOR_NAMES but 0 = "Use Global Settings" for these dropdowns.
PRESET_BTN_COLOR_NAMES = {0: "Use Global Settings",
                          **{k: v for k, v in COLOR_NAMES.items() if k != 0}}


# Per-button "Function" byte encoding (FUNC1/FUNC2 arrays). Decoded from the official manual's
# "Defining Button Functions" table cross-checked against the corpus (2026-06-15):
#   0          NOT DEFINED
#   1..60      PRESET B#NN  (a preset button within the current bank)
#   61..80     SYSTEM FUNCTION 1..20 (byte = 60 + fn) — see PAGE_SYSTEM_FUNCTIONS
#   81..127    higher system functions (fn 21+); v6.31 defines none, shown generically
#   128..187   IA-slot trigger, slot = byte - 127  (resolves to the IA-switch name)
#   200..255   Page switch, page = byte - 199        (resolves to the page nickname)
# The function names are the exact strings the v6.31 editor shows — confirmed by reading its
# page-button Function dropdown directly (2026-06-16, inverted probe). The list ends at fn 20
# ("Change PAGE"); fn 19 is "Current MODE" (the 2015 manual's older "MODE CYCLE" name).
FUNC_NONE = 0
PRESET_BTN_LO, PRESET_BTN_HI = 1, 60
SYSTEM_FUNC_BASE = 60       # byte = SYSTEM_FUNC_BASE + fn  (fn 1..20)
SYSTEM_FUNC_HI = 127        # bytes 61..127 are system functions (fn 1..67); v6.31 names 1..20
IA_SLOT_BASE = 127          # byte = IA_SLOT_BASE + slot    (slot 1..60)
PAGE_SWITCH_BASE = 199      # byte = PAGE_SWITCH_BASE + page (page 1..56)

PAGE_SYSTEM_FUNCTIONS = {
    1: "MENU", 2: "Enter/Select", 3: "Context UP", 4: "Context DWN", 5: "Preset UP",
    6: "Preset DWN", 7: "Bank UP", 8: "Bank DWN", 9: "Song UP", 10: "Song DWN",
    11: "SetList UP", 12: "SetList DWN", 13: "Page UP", 14: "Page DWN", 15: "Global Page",
    16: "Last Page", 17: "Last Preset", 18: "Save Preset", 19: "Current MODE", 20: "Change PAGE",
}


def decode_button_function(byte: int, ia_names=None, page_names=None) -> str:
    """Human-readable label for a page-button Function byte (matches the original editor's tiles)."""
    if byte == FUNC_NONE:
        return ""
    if PRESET_BTN_LO <= byte <= PRESET_BTN_HI:
        return f"PRESET B#{byte:02d}"
    if 61 <= byte <= SYSTEM_FUNC_HI:
        fn = byte - SYSTEM_FUNC_BASE
        return PAGE_SYSTEM_FUNCTIONS.get(fn, f"SYS FN {fn}")
    if 128 <= byte <= 187:
        slot = byte - IA_SLOT_BASE
        nm = ia_names[slot - 1] if ia_names and slot - 1 < len(ia_names) else ""
        return f"({slot:03d}) {nm}".rstrip()
    if byte >= 200:
        pg = byte - PAGE_SWITCH_BASE
        nm = page_names[pg - 1] if page_names and pg - 1 < len(page_names) else ""
        return f"({pg:03d}) {nm}".rstrip() if nm else f"Page #{pg:02d}"
    return f"[{byte}]"


class Page(Record):
    has_name = True

    def func1(self, button: int) -> int:
        return self.values[FUNC1_OFF + button]

    def func2(self, button: int) -> int:
        return self.values[FUNC2_OFF + button]
