"""Quick Repeated Command Programmer dialog (Utilities menu)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QComboBox, QSpinBox, QCheckBox, QLabel,
    QPushButton, QGroupBox, QMessageBox,
)

from .. import quickprog
from ..model.preset import MIDI_MSG_TYPES, FUNC_MIDI

_IA_FUNCS = {10: "IA ON Trig", 11: "IA OFF Trig", 12: "IA Toggle", 21: "IA Resend"}


class QuickProgDialog(QDialog):
    def __init__(self, parent, get_dump, on_applied):
        super().__init__(parent)
        self._get_dump = get_dump
        self._on_applied = on_applied
        self.setWindowTitle("Quick Repeated Command Programmer")
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        target = QGroupBox("Where to write")
        form = QFormLayout(target)
        self.area = QComboBox()
        for key, (_t, _o, _n, label) in quickprog.AREAS.items():
            self.area.addItem(label, key)
        self.area.currentIndexChanged.connect(self._area_changed)
        form.addRow("Command area:", self.area)
        self.row = QSpinBox(); self.row.setRange(1, 16)
        form.addRow("Programming row:", self.row)
        rng = QHBoxLayout()
        self.lo = QSpinBox(); self.lo.setRange(1, 9999); self.lo.setValue(1)
        self.hi = QSpinBox(); self.hi.setRange(1, 9999); self.hi.setValue(9999)
        rng.addWidget(self.lo); rng.addWidget(QLabel("to")); rng.addWidget(self.hi)
        form.addRow("Record range:", rng)
        root.addWidget(target)

        cmd = QGroupBox("Command to write")
        cform = QFormLayout(cmd)
        self.func = QComboBox()
        self.func.addItem("Empty", 0)
        self.func.addItem("MIDI Command", FUNC_MIDI)
        for code, name in _IA_FUNCS.items():
            self.func.addItem(name, code)
        self.func.currentIndexChanged.connect(self._func_changed)
        cform.addRow("Function:", self.func)

        self.chan = QComboBox()
        for c in range(1, 17):
            self.chan.addItem(str(c), c)
        cform.addRow("MIDI channel:", self.chan)
        self.mtype = QComboBox()
        for code, name in MIDI_MSG_TYPES.items():
            self.mtype.addItem(name, code)
        self.mtype.setCurrentIndex(list(MIDI_MSG_TYPES).index(0xC))  # default Program Change
        self.mtype.currentIndexChanged.connect(self._mtype_changed)
        cform.addRow("Message type:", self.mtype)
        self.d1 = QSpinBox(); self.d1.setRange(0, 16383)
        self.d1_label = QLabel("Program #:")
        cform.addRow(self.d1_label, self.d1)
        self.d2 = QSpinBox(); self.d2.setRange(0, 127)
        self.d2_label = QLabel("Value:")
        cform.addRow(self.d2_label, self.d2)
        self.slot = QSpinBox(); self.slot.setRange(1, 180)
        self.slot_label = QLabel("IA-slot #:")
        cform.addRow(self.slot_label, self.slot)
        self.pc_inc = QCheckBox("Auto-increment Program # per record")
        self.pc_inc.setChecked(True)
        cform.addRow(self.pc_inc)
        root.addWidget(cmd)

        bar = QHBoxLayout()
        bar.addStretch(1)
        apply_btn = QPushButton("Apply"); apply_btn.clicked.connect(self.apply)
        bar.addWidget(apply_btn)
        close = QPushButton("Close"); close.clicked.connect(self.close)
        bar.addWidget(close)
        root.addLayout(bar)

        self._area_changed()
        self._func_changed()

    def _area_changed(self):
        key = self.area.currentData()
        _t, _o, nrows, _l = quickprog.AREAS[key]
        self.row.setMaximum(nrows)

    def _func_changed(self):
        is_midi = self.func.currentData() == FUNC_MIDI
        is_ia = self.func.currentData() in _IA_FUNCS
        for w in (self.chan, self.mtype):
            w.setVisible(is_midi)
        self._set_row_visible(self.chan, is_midi)
        self._set_row_visible(self.mtype, is_midi)
        self._set_row_visible(self.slot, is_ia, self.slot_label)
        self._mtype_changed()

    def _mtype_changed(self):
        is_midi = self.func.currentData() == FUNC_MIDI
        is_pc = is_midi and self.mtype.currentData() == 0xC
        self._set_row_visible(self.d1, is_midi, self.d1_label)
        self._set_row_visible(self.d2, is_midi and not is_pc, self.d2_label)
        self.d1_label.setText("Program #:" if is_pc else "Data 1:")
        self.pc_inc.setVisible(is_pc)

    def _set_row_visible(self, widget, vis, label=None):
        widget.setVisible(vis)
        if label is not None:
            label.setVisible(vis)

    def _build_command(self):
        func = self.func.currentData()
        if func == 0:
            return quickprog.empty_command()
        if func == FUNC_MIDI:
            return quickprog.midi_command(self.mtype.currentData(), self.chan.currentData(),
                                          self.d1.value(), self.d2.value())
        return quickprog.ia_command(func, self.slot.value())

    def apply(self):
        dump = self._get_dump()
        if dump is None:
            QMessageBox.information(self, "Quick Programmer", "Open a .syx file first.")
            return
        key = self.area.currentData()
        cmd = self._build_command()
        pc_inc = self.pc_inc.isChecked() and self.pc_inc.isVisible()
        try:
            n = quickprog.apply_command(dump, key, self.row.value(), self.lo.value(),
                                        self.hi.value(), cmd, pc_increment=pc_inc)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Quick Programmer", str(exc))
            return
        self._on_applied()
        QMessageBox.information(self, "Quick Programmer",
                               f"Wrote the command into row {self.row.value()} of {n} record(s).")
