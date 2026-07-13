"""
Find / Q-LIST dialog — a faithful take on the original editor's FIND / EDIT / EXPORT window.

Non-modal: it stays open beside the editor. Enter a wildcard name query and/or a MIDI command
criterion (channel / message type / CC#-or-PC#), restrict by record type and number range, hit
Search, then double-click a result to jump to that record in the main window, or Export to CSV.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QComboBox, QSpinBox,
    QCheckBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QFileDialog,
    QMessageBox,
)

from .. import search as searchmod
from .theme import ACCENT
from . import dnd  # noqa: F401  (used by _ResultsTable.mimeData)


class _ResultsTable(QTableWidget):
    """Results grid whose rows can be dragged (carrying the record reference) onto slot pickers
    and command rows elsewhere in the editor."""

    def __init__(self, owner):
        super().__init__(0, 5)
        self._owner = owner
        self.setDragEnabled(True)
        self.setDragDropMode(QTableWidget.DragOnly)

    def mimeData(self, items):
        rows = {i.row() for i in items}
        if len(rows) != 1:
            return None
        m = self._owner._matches[rows.pop()]
        return dnd.encode(m.type_, m.number)


class FindDialog(QDialog):
    def __init__(self, parent, get_dump, reveal, on_close=None):
        super().__init__(parent)
        self._get_dump = get_dump
        self._reveal = reveal
        self._on_close = on_close
        self._matches: list = []
        self.setWindowTitle("Find / Q-LIST")
        self.setMinimumSize(720, 560)
        self.setWindowModality(Qt.NonModal)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ---- record filter ----
        rec = QGroupBox("Record filter")
        rg = QGridLayout(rec)
        rg.addWidget(QLabel("Quick search (name, * / ? wildcards):"), 0, 0)
        self.text = QLineEdit()
        self.text.setPlaceholderText("e.g.  *delay*   or   Lead*")
        self.text.returnPressed.connect(self.run_search)
        rg.addWidget(self.text, 0, 1, 1, 5)

        self.type_boxes: dict[int, QCheckBox] = {}
        col = 0
        for t in searchmod.SEARCHABLE_TYPES:
            cb = QCheckBox(searchmod.TYPE_NAMES[t])
            cb.setChecked(True)
            self.type_boxes[t] = cb
            rg.addWidget(cb, 1, col)
            col += 1

        rg.addWidget(QLabel("Number range:"), 2, 0)
        self.num_min = QSpinBox(); self.num_min.setRange(1, 9999); self.num_min.setValue(1)
        self.num_max = QSpinBox(); self.num_max.setRange(1, 9999); self.num_max.setValue(9999)
        rg.addWidget(self.num_min, 2, 1)
        rg.addWidget(QLabel("to"), 2, 2, alignment=Qt.AlignCenter)
        rg.addWidget(self.num_max, 2, 3)
        root.addWidget(rec)

        # ---- command filter ----
        cmd = QGroupBox("Command filter (optional — find a MIDI command)")
        cg = QGridLayout(cmd)
        cg.addWidget(QLabel("MIDI channel:"), 0, 0)
        self.chan = QComboBox(); self.chan.addItem("Any", None)
        for c in range(1, 17):
            self.chan.addItem(str(c), c)
        cg.addWidget(self.chan, 0, 1)
        cg.addWidget(QLabel("Message type:"), 0, 2)
        self.mtype = QComboBox(); self.mtype.addItem("Any", None)
        for code, name in searchmod.MSG_TYPE_CHOICES.items():
            self.mtype.addItem(name, code)
        cg.addWidget(self.mtype, 0, 3)
        cg.addWidget(QLabel("CC# / PC#:"), 0, 4)
        self.number = QLineEdit(); self.number.setPlaceholderText("Any")
        self.number.setMaximumWidth(80)
        self.number.returnPressed.connect(self.run_search)
        cg.addWidget(self.number, 0, 5)
        self.first_only = QCheckBox("List each record once")
        cg.addWidget(self.first_only, 1, 0, 1, 3)
        root.addWidget(cmd)

        # ---- actions ----
        bar = QHBoxLayout()
        self.search_btn = QPushButton("Search")
        self.search_btn.setDefault(True)
        self.search_btn.clicked.connect(self.run_search)
        bar.addWidget(self.search_btn)
        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet(f"color:{ACCENT};")
        bar.addWidget(self.count_lbl)
        bar.addStretch(1)
        self.export_btn = QPushButton("Export results (CSV)…")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export_results)
        bar.addWidget(self.export_btn)
        close = QPushButton("Close"); close.clicked.connect(self.close)
        bar.addWidget(close)
        root.addLayout(bar)

        # ---- results ----
        self.table = _ResultsTable(self)
        self.table.setHorizontalHeaderLabels(["Type", "#", "Name", "Where", "Data"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._jump)
        root.addWidget(self.table, 1)

    def _criteria(self):
        types = {t for t, cb in self.type_boxes.items() if cb.isChecked()}
        num_txt = self.number.text().strip()
        number = int(num_txt) if num_txt.isdigit() else None
        return dict(
            text=self.text.text(),
            types=types,
            num_min=self.num_min.value(),
            num_max=self.num_max.value(),
            channel=self.chan.currentData(),
            msgtype=self.mtype.currentData(),
            number=number,
            first_only=self.first_only.isChecked(),
        )

    def run_search(self):
        dump = self._get_dump()
        if dump is None:
            QMessageBox.information(self, "Find", "Open a .syx file first.")
            return
        self._matches = searchmod.search(dump, **self._criteria())
        self.table.setRowCount(len(self._matches))
        for r, m in enumerate(self._matches):
            for c, val in enumerate((m.type_name, str(m.number), m.name, m.where, m.detail)):
                item = QTableWidgetItem(val)
                if c == 1:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, item)
        self.count_lbl.setText(f"{len(self._matches)} result(s)")
        self.export_btn.setEnabled(bool(self._matches))

    def _jump(self, row, _col):
        if 0 <= row < len(self._matches):
            m = self._matches[row]
            self._reveal(m.type_, m.number)

    def export_results(self):
        if not self._matches:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export results", "find_results.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            fh.write(searchmod.results_csv(self._matches))

    def closeEvent(self, event):
        if self._on_close is not None:
            self._on_close()
        super().closeEvent(event)
