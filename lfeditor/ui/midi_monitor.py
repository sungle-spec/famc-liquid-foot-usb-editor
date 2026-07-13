"""
MIDI Monitor / Pass-Thru utility — the original editor's Utilities ▸ MIDI Monitor + Pass-Thru.

Monitor: open a MIDI input port and log every incoming message (timestamp + hex + decoded text).
Pass-Thru: also relay each message to a chosen output port, so the editor sits between the LF+ and
a DAW. Polling is done on a Qt timer (no extra thread); messages are read non-blocking.

The Liquid Foot+ presents as USB-serial in this build, so this is a general MIDI tool — it works
with whatever DIN/USB-MIDI ports the OS exposes (and degrades gracefully when there are none).
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
)

try:
    import mido
except Exception:  # noqa: BLE001
    mido = None


def _headless() -> bool:
    """True when running without a real display (offscreen Qt). Used to avoid touching the MIDI
    backend on construction — enumerating ports can error (Linux without an ALSA sequencer) or
    block on a headless CI runner. The user can still enumerate later via 'Refresh ports'."""
    try:
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.platformName() == "offscreen"
    except Exception:  # noqa: BLE001
        return False


def _decode(msg) -> tuple[str, str]:
    """Return (hex bytes, human description) for a mido message."""
    try:
        hexs = " ".join(f"{b:02X}" for b in msg.bytes())
    except Exception:  # noqa: BLE001
        hexs = ""
    return hexs, str(msg)


class MidiMonitorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MIDI Monitor / Pass-Thru")
        self.setMinimumSize(680, 480)
        self.setWindowModality(Qt.NonModal)
        self._in_port = None
        self._out_port = None
        self._t0 = 0.0
        self._rows: list[tuple[str, str, str]] = []

        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._poll)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ---- port selection ----
        ports = QHBoxLayout()
        ports.addWidget(QLabel("Input:"))
        self.in_combo = QComboBox()
        self.in_combo.setMinimumWidth(200)
        ports.addWidget(self.in_combo)
        self.passthru = QCheckBox("Pass-thru to output:")
        ports.addWidget(self.passthru)
        self.out_combo = QComboBox()
        self.out_combo.setMinimumWidth(200)
        ports.addWidget(self.out_combo)
        refresh = QPushButton("Refresh ports")
        refresh.clicked.connect(self.refresh_ports)
        ports.addWidget(refresh)
        ports.addStretch(1)
        root.addLayout(ports)

        # ---- controls ----
        ctrl = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.toggle)
        ctrl.addWidget(self.start_btn)
        self.state_lbl = QLabel("stopped")
        ctrl.addWidget(self.state_lbl)
        ctrl.addStretch(1)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_log)
        ctrl.addWidget(clear)
        self.save_btn = QPushButton("Save log…")
        self.save_btn.clicked.connect(self.save_log)
        ctrl.addWidget(self.save_btn)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        ctrl.addWidget(close)
        root.addLayout(ctrl)

        # ---- log ----
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time (s)", "Bytes (hex)", "Message"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        if mido is None:
            self.state_lbl.setText("mido not available")
            self.start_btn.setEnabled(False)
        elif _headless():
            # No display (tests / CI): don't enumerate ports on construction.
            self.state_lbl.setText("click ‘Refresh ports’")
            self.start_btn.setEnabled(False)
        else:
            self.refresh_ports()

    # ---- ports ----
    def refresh_ports(self):
        if mido is None:
            return
        try:
            ins = mido.get_input_names()
            outs = mido.get_output_names()
        except Exception as exc:  # noqa: BLE001 — no MIDI backend (e.g. Linux without ALSA seq)
            self.in_combo.clear()
            self.out_combo.clear()
            self.in_combo.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.state_lbl.setText("MIDI unavailable")
            return
        self.in_combo.clear()
        self.out_combo.clear()
        self.in_combo.addItems(ins or ["(no MIDI input ports)"])
        self.out_combo.addItems(outs or ["(no MIDI output ports)"])
        self.in_combo.setEnabled(bool(ins))
        self.start_btn.setEnabled(bool(ins))

    # ---- start / stop ----
    def toggle(self):
        if self._in_port is None:
            self.start()
        else:
            self.stop()

    def start(self):
        if mido is None:
            return
        name = self.in_combo.currentText()
        try:
            self._in_port = mido.open_input(name)
            if self.passthru.isChecked() and self.out_combo.isEnabled():
                self._out_port = mido.open_output(self.out_combo.currentText())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "MIDI", f"Could not open port:\n{exc}")
            self.stop()
            return
        self._t0 = time.monotonic()
        self._timer.start()
        self.start_btn.setText("Stop")
        self.state_lbl.setText(f"monitoring {name}"
                               + (" → " + self.out_combo.currentText() if self._out_port else ""))

    def stop(self):
        self._timer.stop()
        for p in (self._in_port, self._out_port):
            try:
                if p is not None:
                    p.close()
            except Exception:  # noqa: BLE001
                pass
        self._in_port = self._out_port = None
        self.start_btn.setText("Start")
        self.state_lbl.setText("stopped")

    # ---- polling / logging ----
    def _poll(self):
        if self._in_port is None:
            return
        for msg in self._in_port.iter_pending():
            self._log(msg)
            if self._out_port is not None:
                try:
                    self._out_port.send(msg)
                except Exception:  # noqa: BLE001
                    pass

    def _log(self, msg):
        hexs, text = _decode(msg)
        row = (f"{time.monotonic() - self._t0:8.3f}", hexs, text)
        self._rows.append(row)
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, val in enumerate(row):
            self.table.setItem(r, c, QTableWidgetItem(val))
        self.table.scrollToBottom()

    def clear_log(self):
        self._rows.clear()
        self.table.setRowCount(0)

    def save_log(self):
        if not self._rows:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save MIDI log", "midi_log.csv", "CSV (*.csv)")
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["Time (s)", "Bytes (hex)", "Message"])
            w.writerows(self._rows)

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)
