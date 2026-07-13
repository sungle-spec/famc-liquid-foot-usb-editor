"""Device Connection Setup wizard — enables the Liquid Foot+ as a USB-serial port by rewriting
its FTDI EEPROM PID (0x87C0 → 0x6015), with a backup taken first. Launched from Hardware menu.

The actual EEPROM write goes through comms/eeprom.py and is gated: it only runs after the user
confirms in this dialog (allow_write=True). Detection and backup are read-only.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox, QFrame,
)

from ..comms import eeprom as ee
from .theme import ACCENT, GREEN, RED, AMBER, TEXT_DIM

BACKUP_DIR = os.path.expanduser("~/Documents/FAMC/EEPROM_Backups")

_DOT = {
    ee.READY: GREEN, ee.ENABLED_NO_PORT: AMBER, ee.NEEDS_ENABLE: AMBER,
    ee.OTHER_FTDI: AMBER, ee.NO_DEVICE: RED, ee.NO_BACKEND: RED,
}


class EepromWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Device Connection Setup")
        self.setMinimumWidth(560)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("Liquid Foot+ — USB Connection Setup")
        title.setObjectName("tabTitle")
        root.addWidget(title)

        blurb = QLabel(
            "FAMC ships the Foot with a custom USB id (0x87C0) that macOS doesn't expose as a "
            "serial port. This rewrites the FTDI EEPROM id to the standard 0x6015 so the editor "
            "can connect — a full EEPROM backup is saved first, and only the id changes.")
        blurb.setWordWrap(True)
        blurb.setStyleSheet(f"color:{TEXT_DIM};")
        root.addWidget(blurb)

        line = QFrame(); line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color:{TEXT_DIM};")
        root.addWidget(line)

        status_row = QHBoxLayout()
        self.dot = QLabel("●"); self.dot.setFixedWidth(18)
        status_row.addWidget(self.dot)
        self.status = QLabel("Checking…")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("font-weight:700;")
        status_row.addWidget(self.status, 1)
        root.addLayout(status_row)

        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet(f"color:{TEXT_DIM};")
        root.addWidget(self.detail)

        btns = QHBoxLayout()
        self.btn_enable = QPushButton("Enable (write EEPROM)")
        self.btn_enable.setObjectName("xfer")
        self.btn_enable.clicked.connect(self._enable)
        self.btn_revert = QPushButton("Revert to 0x87C0")
        self.btn_revert.clicked.connect(self._revert)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._refresh)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        btns.addWidget(self.btn_enable)
        btns.addWidget(self.btn_revert)
        btns.addStretch(1)
        btns.addWidget(self.btn_refresh)
        btns.addWidget(close)
        root.addLayout(btns)

        self._refresh()

    # --- actions ---
    def _refresh(self):
        st = ee.detect_state()
        self._state = st
        self.dot.setStyleSheet(f"color:{_DOT.get(st.state, TEXT_DIM)}; font-size:16px;")
        self.status.setText(st.message)
        bits = []
        if st.pid is not None:
            bits.append(f"Detected USB product id: 0x{st.pid:04x}")
        if st.serial_ports:
            bits.append("Serial port: " + ", ".join(st.serial_ports))
        self.detail.setText("\n".join(bits))
        self.btn_enable.setEnabled(st.can_enable)
        reason = ee.revert_blocked_reason()
        self.btn_revert.setEnabled(reason is None and st.state in (ee.READY, ee.ENABLED_NO_PORT))
        self.btn_revert.setToolTip(reason or "Rewrite the EEPROM back to FAMC's 0x87C0")

    def _enable(self):
        if QMessageBox.warning(
                self, "Write EEPROM?",
                "This will rewrite the FTDI EEPROM product id to 0x6015 so the Foot appears as a "
                "serial port.\n\nA full EEPROM backup is saved first. Don't unplug the device "
                "during the write. Continue?",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        res = ee.set_product_id(ee.FAMC_CUSTOM_PID, ee.SERIAL_PID, BACKUP_DIR, allow_write=True)
        self._report(res)
        self._refresh()

    def _revert(self):
        reason = ee.revert_blocked_reason()
        if reason:
            QMessageBox.information(self, "Revert not available here", reason)
            return
        if QMessageBox.warning(
                self, "Revert EEPROM?",
                "This rewrites the EEPROM id back to FAMC's 0x87C0 (for use with the original "
                "editor). A backup is saved first. Continue?",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        res = ee.set_product_id(ee.SERIAL_PID, ee.FAMC_CUSTOM_PID, BACKUP_DIR, allow_write=True)
        self._report(res)
        self._refresh()

    def _report(self, res: "ee.WriteResult"):
        icon = QMessageBox.information if res.ok else QMessageBox.critical
        icon(self, "Result", res.message)
