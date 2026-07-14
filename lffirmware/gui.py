"""Single-window GUI for the firmware loader. Every safety gate from the CLI, made visual:
the FLASH button only arms when the image is verified, matches the selected model, a port is
chosen, every checklist item is ticked, and the user has typed the model name."""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton, QRadioButton, QTextEdit, QVBoxLayout,
    QWidget,
)

from . import __version__
from .images import MODELS, describe, validate_image
from .send import SessionLog, estimate_seconds, list_ports, send_firmware

ROUTE_A = ("Bricked / dead unit  (power-up recovery)",
           "1. Device OFF.  2. Hold the firmware-wait button while powering ON (see the manual's "
           "\"Special Commands During Power Up\" table) until it waits for MIDI firmware.")
ROUTE_B = ("Working unit  (menu update)",
           "1. BACK UP YOUR RIG FIRST (editor → From LF+ → Backup).  2. Device menu → Utilities "
           "→ FIRMWARE LOADING → SELECT → \"Waiting For Firmware\".")

CHECKS = (
    "Computer MIDI OUT is cabled to the device MIDI IN (DIN, via a USB-MIDI interface)",
    "The device display shows it is waiting for firmware",
    "No other MIDI software is running on this computer",
    "Laptop is on AC power; I will not touch anything until the device restarts",
)


class LoaderWindow(QWidget):
    _progress = Signal(float, float)
    _finished = Signal(dict)
    _failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LF+ Firmware Loader {__version__} (beta)")
        self.rep = None
        self._busy = False
        root = QVBoxLayout(self)

        warn = QLabel("⚠  Firmware flashing can permanently damage your device. "
                      "Read docs/FIRMWARE_LOADER.md. Always have a backup. Use at your own risk.")
        warn.setWordWrap(True)
        warn.setStyleSheet("color:#e05a4e; font-weight:bold;")
        root.addWidget(warn)

        # image
        g1 = QGroupBox("1 — Firmware image (.syx from your original editor install)")
        v1 = QVBoxLayout(g1)
        row = QHBoxLayout()
        self.pick = QPushButton("Choose firmware file…")
        self.pick.clicked.connect(self.choose_file)
        row.addWidget(self.pick); row.addStretch(1)
        v1.addLayout(row)
        self.report = QTextEdit(); self.report.setReadOnly(True)
        self.report.setFixedHeight(110)
        self.report.setStyleSheet("font-family: Menlo, 'Courier New', monospace; font-size: 11px;")
        v1.addWidget(self.report)
        self.override = QCheckBox("This image is not in the known-good list — flash it anyway "
                                  "(I am certain it is genuine FAMC firmware)")
        self.override.setVisible(False)
        self.override.toggled.connect(self.rearm)
        v1.addWidget(self.override)
        root.addWidget(g1)

        # model + port
        g2 = QGroupBox("2 — Your hardware")
        v2 = QVBoxLayout(g2)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Model:"))
        self.model = QComboBox(); self.model.addItem(""); self.model.addItems(MODELS)
        self.model.currentTextChanged.connect(self.rearm)
        row2.addWidget(self.model)
        row2.addSpacing(16)
        row2.addWidget(QLabel("MIDI out:"))
        self.port = QComboBox(); row2.addWidget(self.port, 1)
        refresh = QPushButton("Refresh"); refresh.clicked.connect(self.refresh_ports)
        row2.addWidget(refresh)
        v2.addLayout(row2)
        self.route_a = QRadioButton(ROUTE_A[0]); self.route_b = QRadioButton(ROUTE_B[0])
        self.route_a.setChecked(True)
        self.route_hint = QLabel(ROUTE_A[1]); self.route_hint.setWordWrap(True)
        self.route_hint.setStyleSheet("color:#9aa4ad;")
        for r in (self.route_a, self.route_b):
            r.toggled.connect(self._route_changed); v2.addWidget(r)
        v2.addWidget(self.route_hint)
        root.addWidget(g2)

        # checklist + confirm
        g3 = QGroupBox("3 — Final checks")
        v3 = QVBoxLayout(g3)
        self.checks = []
        for text in CHECKS:
            cb = QCheckBox(text); cb.toggled.connect(self.rearm)
            self.checks.append(cb); v3.addWidget(cb)
        rowc = QHBoxLayout()
        rowc.addWidget(QLabel("Type your model name to arm the button:"))
        self.confirm = QLineEdit(); self.confirm.textChanged.connect(self.rearm)
        rowc.addWidget(self.confirm)
        v3.addLayout(rowc)
        root.addWidget(g3)

        # send
        self.flash = QPushButton("FLASH FIRMWARE")
        self.flash.setEnabled(False)
        self.flash.setStyleSheet("QPushButton:enabled { background:#7a1f1f; color:white; "
                                 "font-weight:bold; padding:8px; }")
        self.flash.clicked.connect(self.do_flash)
        root.addWidget(self.flash)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setValue(0)
        root.addWidget(self.bar)
        self.status = QLabel("Pick a firmware file to begin.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        self._failed.connect(self._on_failed)
        self.refresh_ports()
        self.resize(680, 640)

    # ---- ui plumbing ----
    def _route_changed(self):
        self.route_hint.setText(ROUTE_A[1] if self.route_a.isChecked() else ROUTE_B[1])

    def refresh_ports(self):
        cur = self.port.currentText()
        self.port.clear()
        try:
            ports = list_ports()
        except Exception as exc:  # noqa: BLE001
            ports = []
            self.status.setText(f"Could not list MIDI ports: {exc}")
        self.port.addItems(ports)
        if cur in ports:
            self.port.setCurrentText(cur)
        self.rearm()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Firmware image", "", "Sysex (*.syx)")
        if not path:
            return
        self.rep = validate_image(path)
        self.report.setPlainText(describe(self.rep))
        self.override.setVisible(self.rep.is_plausible and not self.rep.is_known_good)
        self.override.setChecked(False)
        self.rearm()

    def rearm(self, *_):
        r = self.rep
        ok = (r is not None
              and (r.is_known_good or (r.is_plausible and self.override.isChecked()))
              and self.model.currentText() in MODELS
              and r.model_for(self.model.currentText())
              and bool(self.port.currentText())
              and all(c.isChecked() for c in self.checks)
              and self.confirm.text().strip() == self.model.currentText()
              and not self._busy)
        if r is not None and self.model.currentText() in MODELS \
                and not r.model_for(self.model.currentText()):
            self.status.setText(f"BLOCKED: that image is for "
                                f"{r.known_model or r.filename_model or 'another model'}, "
                                f"not {self.model.currentText()}.")
        self.flash.setEnabled(ok)

    # ---- send ----
    def do_flash(self):
        est = estimate_seconds(self.rep.size)
        if QMessageBox.warning(
                self, "Last chance",
                f"Flash {self.model.currentText()} firmware"
                f"{' v' + self.rep.known_version if self.rep.known_version else ''} "
                f"({self.rep.size:,} bytes, ~{est:.0f}s)?\n\n"
                "Do NOT power off, unplug, or press any buttons until the device restarts.",
                QMessageBox.Cancel | QMessageBox.Yes, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        self._busy = True
        self.flash.setEnabled(False)
        self.status.setText("Sending — do not touch the device or cables…")
        image = open(self.rep.path, "rb").read()
        log = SessionLog()
        self._log = log

        def work():
            try:
                res = send_firmware(self.port.currentText(), image, self.rep, log,
                                    on_progress=lambda e, t: self._progress.emit(e, t))
                self._finished.emit(res)
            except Exception as exc:  # noqa: BLE001 — surfaced to the user
                log.write(f"ERROR: {exc}")
                self._failed.emit(str(exc))
            finally:
                log.close()

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, elapsed: float, est: float):
        self.bar.setValue(min(99, int(elapsed / max(est, 1) * 100)))

    def _on_finished(self, res: dict):
        self._busy = False
        self.bar.setValue(100)
        self.status.setText(
            f"Sent in {res['seconds']:.0f}s ({len(res['replies'])} device replies). Watch the "
            f"device — it should program itself and restart. Log: {res['log']}")
        self.rearm()

    def _on_failed(self, err: str):
        self._busy = False
        self.status.setText(f"FAILED: {err} — log: {self._log.path}")
        self.rearm()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    try:
        from lfeditor.ui.theme import build_stylesheet
        app.setStyleSheet(build_stylesheet())
    except Exception:  # noqa: BLE001 — theme is cosmetic
        pass
    win = LoaderWindow()
    win.show()
    return app.exec()
