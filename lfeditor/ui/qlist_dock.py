"""
Q-LIST — a left-side quick-pick dock (mirrors the original editor's Q-LIST panel).

It follows the current editor tab: on a record tab it lists that type (Preset / Songs / Set-List /
IA-Slot / IA-Maps / Pages / Sysex); on a tab with no record list (Global, Midi/Groups, Exp Pedals,
Colors) it shows nothing. Single-click an item to jump straight to it; click a type button to switch
to that tab; drag an item onto a slot picker / command row (same payload as the Find results).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QGridLayout, QPushButton, QButtonGroup, QLineEdit,
    QListWidget, QListWidgetItem,
)

from . import dnd

# (record type, button label) in the original's order
TYPES = [
    (1, "Preset"), (2, "Songs"), (5, "Set-List"),
    (3, "IA-Slot"), (8, "IA-Maps"), (7, "Pages"), (6, "Sysex"),
]


class _DragList(QListWidget):
    """Record list whose rows drag a `type:number` reference (for drop onto slots / commands)."""

    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragOnly)
        self.setUniformItemSizes(True)

    def mimeData(self, items):
        if len(items) != 1:
            return None
        ref = items[0].data(Qt.UserRole)
        return dnd.encode(ref[0], ref[1]) if ref else None


class QListDock(QDockWidget):
    def __init__(self, parent, get_dump, on_select, on_pick_type):
        super().__init__("Q-LIST", parent)
        self._get_dump = get_dump
        self._on_select = on_select        # (type, number) -> jump to that record
        self._on_pick_type = on_pick_type  # (type) -> switch to that type's tab
        self._type = None
        self._records: list = []
        self.setObjectName("qlist")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
                         | QDockWidget.DockWidgetClosable)

        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        grid = QGridLayout()
        grid.setSpacing(3)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[int, QPushButton] = {}
        for i, (type_, label) in enumerate(TYPES):
            b = QPushButton(label)
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, t=type_: self._on_pick_type(t))
            self._group.addButton(b)
            self._buttons[type_] = b
            grid.addWidget(b, i // 3, i % 3)
        v.addLayout(grid)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Search (number / name)…")
        self.filter.textChanged.connect(self._apply_filter)
        v.addWidget(self.filter)

        self.list = _DragList()
        self.list.itemClicked.connect(self._jump)     # single click jumps
        v.addWidget(self.list, 1)

        self.setWidget(body)

    def show_type(self, type_) -> None:
        """Show records of `type_` (or clear, if `type_` is None — a tab with no record list).
        Highlights the matching type button."""
        self._type = type_
        dump = self._get_dump()
        self._records = dump.records(type_) if (dump is not None and type_ is not None) else []
        # reflect the active type on the buttons (none checked on a non-record tab)
        self._group.setExclusive(False)
        for t, b in self._buttons.items():
            b.setChecked(t == type_)
        self._group.setExclusive(True)
        self._apply_filter(self.filter.text())

    def refresh(self) -> None:
        self.show_type(self._type)

    def _apply_filter(self, text: str) -> None:
        text = text.strip().lower()
        self.list.clear()
        for rec in self._records:
            name = (getattr(rec, "name", "") or "").strip()
            label = f"({rec.number:03d}) {name}"
            if text and text not in label.lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, (self._type, rec.number))
            self.list.addItem(item)

    def _jump(self, item):
        ref = item.data(Qt.UserRole)
        if ref:
            self._on_select(ref[0], ref[1])
