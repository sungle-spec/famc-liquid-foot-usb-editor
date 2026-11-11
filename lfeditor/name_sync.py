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
