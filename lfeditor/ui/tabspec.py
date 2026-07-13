"""Qt-free tab/section spec dataclasses.

These carry only *data* (titles, record types, the field list, layout hints) — no Qt — so they can
be imported and introspected without PySide6. The desktop tabs (`tabs/base.py`, `tabs/global_tab.py`)
build Qt widgets from them; the web build (`lfeditor/schema.py`, run under Pyodide) introspects the
same objects to emit a JSON UI schema. Keeping them here is what lets both share one definition.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field


@dataclass
class Section:
    """A titled panel holding a set of fields. `note` shows a small caption under the title.
    `labeled` renders "label : widget" rows (else widgets full-width). `record` selects which
    Config record a *global* tab binds this section to (0 or 1); record tabs ignore it."""
    title: str
    fields: list  # list[Field] — annotated loosely to avoid importing the Qt-bearing fields module
    note: str = ""
    labeled: bool = True
    record: int = 0


@dataclass
class TabSpec:
    title: str
    type: int
    columns: list[list[Section]]
    raw_from: int = 0
    default_row: int = 0
    has_name: bool = True
    extra: list = dc_field(default_factory=list)  # extra full-width widgets/sections at bottom


@dataclass
class GlobalSpec:
    title: str
    type: int            # 4 (Config)
    columns: list[list[Section]]
    live_calibrate: bool = False   # Exp-Pedals tab adds a "Live Calibrate…" button
