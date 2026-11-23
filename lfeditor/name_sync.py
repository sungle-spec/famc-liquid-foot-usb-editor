"""When do renamed IA-Slots / Pages show up in the pickers that list them? (Qt-free, unit-testable)

Several editors list records *by name*: the IA-Maps tab (60 IA-Slot dropdowns), the Preset tab's
IA-state list, and the Pages tab's IA Slot / Page Select dropdowns and button tiles. They cache
the names when a file is loaded, so a rename made on the IA-Slot or Pages tab used to appear there
only after reloading the file. The user chooses how that should behave (Settings menu):

* ``original`` — the historical behaviour: nothing propagates until a file is (re)loaded. Default.
* ``auto``     — propagate shortly after typing stops and whenever you switch tabs.
* ``manual``   — propagate only when you press *Edit ▸ Refresh Names*.

*Refresh Names* is always available, in every mode.
"""
from __future__ import annotations

MODE_ORIGINAL = "original"
MODE_AUTO = "auto"
MODE_MANUAL = "manual"
MODES = (MODE_ORIGINAL, MODE_AUTO, MODE_MANUAL)
DEFAULT_MODE = MODE_ORIGINAL
SETTINGS_KEY = "nameSyncMode"

MODE_LABELS = {
    MODE_ORIGINAL: "Original — update names only when a file is loaded",
    MODE_AUTO: "Automatic — update names as I edit",
    MODE_MANUAL: "Manual — update only when I choose Edit ▸ Refresh Names",
}

IA_SLOT_TYPE = 3
PAGE_TYPE = 7
NAME_TYPES = (IA_SLOT_TYPE, PAGE_TYPE)   # record types whose names other tabs display

AUTO_DELAY_MS = 300   # quiet time after the last keystroke before an automatic refresh


def normalize_mode(value) -> str:
    """Any stored/unknown value -> a valid mode (unknown falls back to the default)."""
    return value if value in MODES else DEFAULT_MODE


def ia_names(dump) -> list[str]:
    return [(getattr(r, "name", "") or "").strip() for r in dump.records(IA_SLOT_TYPE)]


def page_names(dump) -> list[str]:
    """Pages are shown by nick when set, else name (matches the Pages tab)."""
    return [((getattr(r, "nick", "") or getattr(r, "name", "") or "").strip())
            for r in dump.records(PAGE_TYPE)]


def names_signature(dump) -> tuple:
    """Cheap fingerprint of every name the dependent pickers display; equal => nothing to refresh."""
    return (tuple(ia_names(dump)), tuple(page_names(dump)))


# ---- IA Map to use for display (Pages tab) -------------------------------------------------------
# A Page button's "IA Slot" value N (1..60) is a *position in the IA-Map the LF is using when the
# page runs* (the preset's map, or the page's own "Force IA map"), not a fixed IA-Slot number. The
# editor cannot know which map will be live, so — like the original editor's display-only "IA Map
# to Use for Display" dropdown — it lets you pick one to label the 60 choices with. Nothing is
# written to the file by this choice.
DISPLAY_MAP_AUTO = "auto"        # the page's Force IA map if set (1..60), else map 1 (the default)
DISPLAY_MAP_PRESET = "preset"    # the IA-Map in use by the last selected Preset
DISPLAY_MAP_NONE = "none"        # no map: choice N is labelled with IA-Slot N (the old behaviour)
IA_MAP_TYPE = 8
IA_MAP_CELLS = 60


def display_map_index(choice, force_ia_map: int, map_count: int, preset_map: int | None = None) -> int | None:
    """0-based IA-Map record to label with, or None for 'no map'. `choice` is DISPLAY_MAP_AUTO,
    DISPLAY_MAP_PRESET, DISPLAY_MAP_NONE or a 0-based map index; `force_ia_map` is the page's
    Force-IA-map byte (0 = none, else 1-based map number); `preset_map` is the last selected
    Preset's own 0-based map index (None when no preset has been selected)."""
    if choice == DISPLAY_MAP_NONE or map_count <= 0:
        return None
    if choice == DISPLAY_MAP_AUTO:
        return force_ia_map - 1 if 1 <= force_ia_map <= map_count else 0
    if choice == DISPLAY_MAP_PRESET:
        return preset_map if preset_map is not None and 0 <= preset_map < map_count else 0
    return choice if isinstance(choice, int) and 0 <= choice < map_count else 0


def labels_for_map(ia_slot_names: list[str], map_cells, map_index_cells: int = IA_MAP_CELLS) -> list[str]:
    """Names for the 60 IA-Slot choices when `map_cells` (an IA-Map's 60 button→slot cells, each a
    0-based IA-Slot index) is the live map: entry n is the name of the slot map position n+1 holds."""
    out = []
    for n in range(map_index_cells):
        slot = map_cells[n] if n < len(map_cells) else n
        out.append(ia_slot_names[slot] if 0 <= slot < len(ia_slot_names) else "")
    return out


def preset_map_index(preset) -> int | None:
    """The 0-based IA-Map a Preset record uses (None if there is no preset)."""
    from .model.preset import IA_SLOT_MAP_OFF
    return None if preset is None else preset.values[IA_SLOT_MAP_OFF]


def display_names(dump, choice=DISPLAY_MAP_AUTO, force_ia_map: int = 0, preset=None) -> list[str]:
    """The 60 IA-Slot labels the Pages tab shows, for the chosen display map. `preset` is the last
    selected Preset record (or None)."""
    from .model.iamap import MAP_OFF
    slots = ia_names(dump)
    maps = dump.records(IA_MAP_TYPE)
    idx = display_map_index(choice, force_ia_map, len(maps), preset_map_index(preset))
    if idx is None:
        return slots[:IA_MAP_CELLS]
    return labels_for_map(slots, maps[idx].values[MAP_OFF:MAP_OFF + IA_MAP_CELLS])


def display_map_options(dump, preset=None) -> list[tuple[object, str, bool]]:
    """[(choice, label, enabled)] for the picker: Auto, Per last selected Preset (greyed out until a
    preset has been selected), No map, then every IA-Map by number and name."""
    maps = dump.records(IA_MAP_TYPE)
    if preset is None:
        per_preset = (DISPLAY_MAP_PRESET, "Per last selected Preset (none selected yet)", False)
    else:
        m = preset_map_index(preset)
        pname = (getattr(preset, "name", "") or "").strip()
        label = f"Per last selected Preset — #{preset.number} {pname}".rstrip()
        if m is not None and 0 <= m < len(maps):
            label += f" → Map {m + 1:03d}"
        per_preset = (DISPLAY_MAP_PRESET, label, True)
    opts: list[tuple[object, str, bool]] = [
        (DISPLAY_MAP_AUTO, "Auto — page's Force IA map, else Map 1", True),
        per_preset,
        (DISPLAY_MAP_NONE, "No map — IA-Slot number", True),
    ]
    for n, rec in enumerate(maps):
        nm = (getattr(rec, "name", "") or "").strip()
        opts.append((n, f"Map {n + 1:03d}" + (f" — {nm}" if nm else ""), True))
    return opts
