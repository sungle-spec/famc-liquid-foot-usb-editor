"""Qt-free UI schema for the web frontend.

Introspects the desktop's spec-driven tab definitions (`ui/specs.py` → `Field`/`Section`/`TabSpec`,
all importable without PySide6 — see `ui/fields.py::_HAVE_QT`) and emits a JSON description of every
tab: columns → titled sections → fields with their byte offsets, kinds, labels and options. The web
app (running this module under Pyodide) renders the faithful UI from this single source of truth, so
the browser editor and the desktop editor never drift.

Two tabs are bespoke Qt widgets on the desktop (no `TabSpec`): **Pages** (graphical pedalboard) and
**Midi/Groups** (channel grid). They get hand-written descriptors here carrying the byte offsets
their JS renderers need.
"""
from __future__ import annotations

import json

from . import __version__

# desktop tab order (mirrors ui/app.py::TAB_ORDER)
TAB_ORDER = [
    "Presets", "Set-List", "IA-Slot", "IA-Maps", "Midi/Groups", "Global",
    "Songs", "Pages", "Sysex Msgs", "Exp Pedals", "Colors",
]

# Field subclass name -> web widget kind
KIND = {
    "StringField": "string", "NameField": "name", "NickField": "nick",
    "IntField": "int", "Int16Field": "int16", "FlagField": "flag", "ToggleField": "toggle",
    "EnumField": "enum", "MidiTableField": "midi_table", "PresetCmdTableField": "command_table",
    "CommandTableField": "command_table", "BitGridField": "bitgrid", "ByteGridField": "bytegrid",
    "Int16GridField": "int16grid", "SlotPickerField": "slotpicker", "HexBytesField": "hexbytes",
    "IAStateGridField": "iastate", "LabelGridField": "labelgrid", "MMCField": "mmc",
    "ChannelNameField": "channelname",
}

# plain scalar attributes to carry through when present on a field
_ATTRS = (
    "start", "offset", "length", "count", "lo", "hi", "plus_one", "invert", "low_nibble",
    "bitmask", "nibble", "cols", "width", "target_type", "unused_raw", "unused_label",
    "unused_display", "ext_type", "data_start", "data_count",
)


def _field_dict(f, tab_title: str = "") -> dict:
    from .ui.help_text import tooltip_for
    cls = type(f).__name__
    # ToggleField renders its text *inside* the rocker, so it sets `label = ""` and stashes the
    # visible text in `_caption`. Fall back to it so the web rockers aren't captionless.
    label = getattr(f, "label", "") or getattr(f, "_caption", "") or ""
    d: dict = {"kind": KIND.get(cls, "unknown"), "cls": cls, "label": label}
    help_ = tooltip_for(tab_title, label)
    if help_:
        d["help"] = help_
    for attr in _ATTRS:
        if hasattr(f, attr):
            v = getattr(f, attr)
            if isinstance(v, (int, float, str, bool)) or v is None:
                d[attr] = v
    # combo options / command-function maps — JSON keys must be strings
    for name in ("options", "funcs"):
        val = getattr(f, name, None)
        if isinstance(val, dict):
            d[name] = {str(k): v for k, v in val.items()}
    return d


def _section_dict(s, tab_title: str = "") -> dict:
    from .ui.help_text import section_tooltip
    return {
        "title": s.title,
        "note": getattr(s, "note", "") or "",
        "labeled": bool(getattr(s, "labeled", True)),
        "record": int(getattr(s, "record", 0)),
        "help": section_tooltip(tab_title, s.title),
        "fields": [_field_dict(f, tab_title) for f in s.fields],
    }


def _columns(spec) -> list:
    title = getattr(spec, "title", "")
    return [[_section_dict(s, title) for s in col] for col in spec.columns]


def _record_tab(name, spec) -> dict:
    return {
        "name": name, "kind": "record", "type": spec.type, "title": spec.title,
        "has_name": bool(getattr(spec, "has_name", True)),
        "raw_from": int(getattr(spec, "raw_from", 0)),
        "columns": _columns(spec),
    }


def _global_tab(name, spec) -> dict:
    return {
        "name": name, "kind": "global", "type": spec.type, "title": spec.title,
        "live_calibrate": bool(getattr(spec, "live_calibrate", False)),
        "columns": _columns(spec),
    }


def _pages_tab() -> dict:
    """Bespoke descriptor for the graphical Pages pedalboard + button/parameter editor (model/page.py)."""
    from .model import page as P
    from .model.config import COLOR_NAMES
    from .ui.help_text import FIELD_HELP
    return {
        "help": dict(FIELD_HELP.get("Pages", {})),
        "name": "Pages", "kind": "pages", "type": 7,
        "buttons": P.NUM_BUTTONS,
        "func1_off": P.FUNC1_OFF, "func2_off": P.FUNC2_OFF,
        "button_param_off": P.BUTTON_PARAM_OFF,
        "trigger_type_mask": P.BTN_TRIGGER_TYPE_MASK,
        "trigger_types": {str(k): v for k, v in P.BTN_TRIGGER_TYPES.items()},
        "flags": {
            "func1_scrolls": P.BTN_FUNC1_SCROLLS_BIT, "func2_scrolls": P.BTN_FUNC2_SCROLLS_BIT,
            "double_tap": P.BTN_DOUBLE_TAP_BIT, "wait_release": P.BTN_WAIT_RELEASE_BIT,
        },
        # how a Function byte encodes its target (model/page.py::decode_button_function)
        "func_encoding": {
            "none": P.FUNC_NONE, "preset_lo": P.PRESET_BTN_LO, "preset_hi": P.PRESET_BTN_HI,
            "system_base": P.SYSTEM_FUNC_BASE, "ia_base": P.IA_SLOT_BASE, "ia_count": P.NUM_BUTTONS,
            "page_base": P.PAGE_SWITCH_BASE, "page_count": 56,
        },
        "system_functions": {str(k): v for k, v in P.PAGE_SYSTEM_FUNCTIONS.items()},
        "params": {
            "status1_led_off": P.STATUS1_LED_OFF,
            "force_mode_off": P.FORCE_MODE_OFF, "all_btn_dbl_bit": P.ALL_BTN_DBL_BIT,
            "menu_trigger_off": P.MENU_TRIGGER_OFF,
            "force_ia_map_off": P.FORCE_IA_MAP_OFF, "preset_btn_colors_off": P.PRESET_BTN_COLORS_OFF,
            "ia_slot_trig_num_off": P.IA_SLOT_TRIG_NUM_OFF,
        },
        "color_names": {str(k): v for k, v in COLOR_NAMES.items()},
        "preset_btn_color_names": {str(k): v for k, v in P.PRESET_BTN_COLOR_NAMES.items()},
    }


def _midi_groups_tab() -> dict:
    """Bespoke descriptor for the Midi/Groups channel grid (model/config.py)."""
    from .model import config as C
    from .ui.help_text import FIELD_HELP, SECTION_HELP
    return {
        "name": "Midi/Groups", "kind": "midi_groups", "type": 4,
        "help": dict(FIELD_HELP.get("Midi/Groups", {})),
        "section_help": dict(SECTION_HELP.get("Midi/Groups", {})),
        "channels": C.NUM_MIDI_CHANNELS,
        "chan_name": {"off": C.CHAN_NAME_OFF, "stride": C.CHAN_NAME_STRIDE, "record": 1},
        "bank_plus1_off": C.CHAN_BANK_PLUS1_OFF,
        "bank_send_off": C.CHAN_BANK_SEND_OFF, "bank_msb_off": C.CHAN_BANK_MSB_OFF,
        "max_pre": {"off": C.CHAN_MAX_PRE_OFF, "stride": C.CHAN_MAX_PRE_STRIDE,
                    "plus_one": C.CHAN_MAX_PRE_PLUS_ONE},
        # value[122+i] = IA-slot # (0 = none); "Always" LED is not in the verified map, so omitted.
        "exclusive_groups": {"off": C.EXCLUSIVE_GROUP_OFF, "count": C.NUM_EXCLUSIVE_GROUPS},
        # one byte of per-group bits: group n (1..7) -> bit n; set = "Break, then Make".
        "grouped_ia": {"off": C.GROUPED_IA_CONFIG_OFF, "count": C.NUM_EXCLUSIVE_GROUPS,
                       "options": {str(k): v for k, v in C.GROUPED_IA_CONFIG.items()}},
    }


def tab_schema() -> dict:
    """The full UI schema: every tab in desktop order, ready to render."""
    from .ui import specs  # Qt-free import path (see ui/fields.py::_HAVE_QT)

    by_name: dict[str, dict] = {}
    for name, spec in specs.RECORD_TABS.items():
        by_name[name] = _record_tab(name, spec)
    for name, spec in specs.GLOBAL_TABS.items():
        by_name[name] = _global_tab(name, spec)
    by_name["Pages"] = _pages_tab()
    by_name["Midi/Groups"] = _midi_groups_tab()

    tabs = [by_name[n] for n in TAB_ORDER if n in by_name]
    return {"version": __version__, "tab_order": TAB_ORDER, "tabs": tabs}


def schema_json() -> str:
    return json.dumps(tab_schema())
