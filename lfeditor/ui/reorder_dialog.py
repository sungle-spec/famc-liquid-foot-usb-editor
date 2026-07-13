"""Re-order records (Save / Sync) dialog (Utilities menu)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QListWidget, QPushButton, QCheckBox, QLabel,
    QSpinBox, QMessageBox,
)

from .. import reorder


class ReorderDialog(QDialog):
    TYPES = [(1, "Presets"), (2, "Songs")]

    def __init__(self, parent, get_dump, on_applied):
        super().__init__(parent)
        self._get_dump = get_dump
        self._on_applied = on_applied
        self.setWindowTitle("Re-order records (Save / Sync)")
        self.setMinimumSize(420, 520)

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Record type:"))
        self.type_combo = QComboBox()
        for t, label in self.TYPES:
            self.type_combo.addItem(label, t)
        self.type_combo.currentIndexChanged.connect(self._reload)
        top.addWidget(self.type_combo)
        top.addStretch(1)
        self.sync = QCheckBox("Sync references")
        self.sync.setChecked(True)
        self.sync.setToolTip("Update Song / Set-List references so they follow the moved record")
        top.addWidget(self.sync)
        root.addLayout(top)

        self.list = QListWidget()
        root.addWidget(self.list, 1)

        ctrl = QHBoxLayout()
        up = QPushButton("Move ▲"); up.clicked.connect(lambda: self._nudge(-1))
        dn = QPushButton("Move ▼"); dn.clicked.connect(lambda: self._nudge(+1))
        ctrl.addWidget(up); ctrl.addWidget(dn)
        ctrl.addWidget(QLabel("to #"))
        self.target = QSpinBox(); self.target.setRange(1, 9999)
        ctrl.addWidget(self.target)
        moveto = QPushButton("Move to"); moveto.clicked.connect(self._move_to)
        ctrl.addWidget(moveto)
        ctrl.addStretch(1)
        close = QPushButton("Close"); close.clicked.connect(self.close)
        ctrl.addWidget(close)
        root.addLayout(ctrl)

        self._reload()

    def _type(self):
        return self.type_combo.currentData()

    def _reload(self):
        self.list.clear()
        dump = self._get_dump()
        if dump is None:
            return
        recs = dump.records(self._type())
        self.target.setMaximum(max(1, len(recs)))
        for r in recs:
            self.list.addItem(f"{r.number:>3}  {(r.name or '').strip()}")

    def _move(self, src_num, dst_num):
        dump = self._get_dump()
        if dump is None or src_num == dst_num:
            return
        try:
            reorder.move_record(dump, self._type(), src_num, dst_num, self.sync.isChecked())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Re-order", str(exc))
            return
        self._on_applied()
        self._reload()
        self.list.setCurrentRow(dst_num - 1)

    def _nudge(self, delta):
        row = self.list.currentRow()
        if row < 0:
            return
        dst = row + 1 + delta
        if 1 <= dst <= self.list.count():
            self._move(row + 1, dst)

    def _move_to(self):
        row = self.list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Re-order", "Select a record to move first.")
            return
        self._move(row + 1, self.target.value())
