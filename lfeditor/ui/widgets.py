"""Reusable widgets shared across tabs."""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel,
)

from ..model import Record


class RecordRail(QWidget):
    """A left-hand vertical rail listing records of one type, with a type-to-filter box.

    Mirrors the LF+ Editor's record selector: number + name, filterable by number or name.
    Emits `selected(index)` with the position in the *unfiltered* record list.
    """

    selected = Signal(int)

    def __init__(self, title: str):
        super().__init__()
        self._records: list[Record] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        header = QLabel(title)
        header.setObjectName("h")
        lay.addWidget(header)

        self.filter = QLineEdit(placeholderText="filter  (number / name)…")
        self.filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row)
        lay.addWidget(self.list, 1)

        self.count = QLabel("")
        self.count.setObjectName("status")
        lay.addWidget(self.count)

    def set_records(self, records: list[Record]) -> None:
        self._records = records
        self._apply_filter(self.filter.text())

    def _apply_filter(self, text: str) -> None:
        text = text.strip().lower()
        prev = self.list.currentItem()
        prev_idx = prev.data(Qt.UserRole) if prev is not None else None
        self.list.blockSignals(True)
        self.list.clear()
        shown = 0
        target_row = 0
        for idx, rec in enumerate(self._records):
            label = f"{rec.number:>3}  {rec.name}" if rec.has_name else f"{rec.number:>3}"
            if text and text not in label.lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, idx)
            self.list.addItem(item)
            if idx == prev_idx:               # keep the same record selected across a refresh
                target_row = shown
            shown += 1
        self.list.blockSignals(False)
        self.count.setText(f"{shown} of {len(self._records)}")
        if shown:
            self.list.setCurrentRow(target_row)

    def _on_row(self, row: int) -> None:
        if row < 0:
            return
        item = self.list.item(row)
        if item is not None:
            self.selected.emit(item.data(Qt.UserRole))
