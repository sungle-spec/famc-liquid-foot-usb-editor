"""Guided setup checklist for the Hardware ▸ USB MIDI Bridge feature.

Checks the three things the bridge needs — the LF+ itself, usable MIDI endpoints (only an
issue on Windows, where python-rtmidi can't create virtual ports), and the device's "Allow
MIDI in" global — and, on Windows, walks through getting loopback ports via a third-party
driver such as loopMIDI. Read-only: nothing here writes to the device or the filesystem.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..comms import find_midi_ports, find_serial_ports
from .midi_bridge import (
    VIRTUAL_INPUT_PORT_NAME,
    VIRTUAL_OUTPUT_PORT_NAME,
    allow_midi_in_state,
    base_port_name,
)
from .theme import AMBER, GREEN, RED, TEXT_DIM

LOOPMIDI_URL = "https://www.tobias-erichsen.de/software/loopmidi.html"

_DOT = {"ok": GREEN, "warn": AMBER, "bad": RED, "unknown": TEXT_DIM}


class _StatusRow(QHBoxLayout):
    """A colored-dot + text checklist line, updated in place by set()."""

    def __init__(self):
        super().__init__()
        self.dot = QLabel("●")
        self.dot.setFixedWidth(18)
        self.addWidget(self.dot)
        self.text = QLabel("")
        self.text.setWordWrap(True)
        self.addWidget(self.text, 1)

    def set(self, level: str, message: str):
        self.dot.setStyleSheet(f"color:{_DOT.get(level, TEXT_DIM)}; font-size:16px;")
        self.text.setText(message)


class MidiBridgeSetupWizard(QDialog):
    """Non-modal Hardware ▸ USB MIDI Bridge Setup… window. ``window`` is the MainWindow."""

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self.setWindowTitle("USB MIDI Bridge Setup")
        self.setMinimumWidth(560)
        self.setWindowModality(Qt.NonModal)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("USB MIDI Bridge — Setup Check")
        title.setObjectName("tabTitle")
        root.addWidget(title)

        blurb = QLabel(
            "The bridge turns your LF+ editor cable into a live two-way MIDI connection "
            "with your computer. This checks what it needs before you click Start."
        )
        blurb.setWordWrap(True)
        blurb.setStyleSheet(f"color:{TEXT_DIM};")
        root.addWidget(blurb)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color:{TEXT_DIM};")
        root.addWidget(line)

        self.row_device = _StatusRow()
        root.addLayout(self.row_device)
        self.row_endpoints = _StatusRow()
        root.addLayout(self.row_endpoints)
        self.row_allow_in = _StatusRow()
        root.addLayout(self.row_allow_in)

        self._is_windows = sys.platform.startswith("win")
        if self._is_windows:
            steps = QLabel(
                "Windows can't create virtual MIDI ports itself, so:\n"
                "1. Install a MIDI loopback driver — loopMIDI (free) is a common choice:\n"
                f"   {LOOPMIDI_URL}\n"
                f"2. Create two ports named exactly “{VIRTUAL_INPUT_PORT_NAME}” and "
                f"“{VIRTUAL_OUTPUT_PORT_NAME}” (one per direction — reusing one port for both "
                "causes a feedback loop).\n"
                "3. Click Refresh below."
            )
            steps.setWordWrap(True)
            steps.setTextInteractionFlags(Qt.TextSelectableByMouse)
            root.addWidget(steps)

            self.ports_lbl = QLabel("")
            self.ports_lbl.setWordWrap(True)
            self.ports_lbl.setStyleSheet(f"color:{TEXT_DIM};")
            root.addWidget(self.ports_lbl)
        else:
            self.ports_lbl = None

        btns = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        btns.addWidget(refresh)
        btns.addStretch(1)
        open_bridge = QPushButton("Open USB MIDI Bridge…")
        open_bridge.clicked.connect(self._open_bridge)
        btns.addWidget(open_bridge)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        btns.addWidget(close)
        root.addLayout(btns)

        self.refresh()

    def refresh(self):
        ports = find_serial_ports()
        if ports:
            self.row_device.set("ok", f"LF+ detected on {ports[0].name}")
        else:
            self.row_device.set(
                "warn",
                "LF+ not detected — plug it in (Hardware ▸ Device Connection Setup… enables "
                "the serial port id).",
            )

        midi_in, midi_out = find_midi_ports()
        in_names = [p.name for p in midi_in]
        out_names = [p.name for p in midi_out]
        if not self._is_windows:
            self.row_endpoints.set(
                "ok", "Created automatically when the bridge starts — nothing to set up."
            )
        elif (
            any(base_port_name(n) == VIRTUAL_INPUT_PORT_NAME for n in in_names)
            and any(base_port_name(n) == VIRTUAL_OUTPUT_PORT_NAME for n in out_names)
        ):
            self.row_endpoints.set(
                "ok", f"“{VIRTUAL_INPUT_PORT_NAME}” / “{VIRTUAL_OUTPUT_PORT_NAME}” detected "
                "— the bridge will select them automatically."
            )
        elif in_names and out_names and set(in_names) != set(out_names):
            self.row_endpoints.set(
                "warn",
                "Loopback ports found, but not named to match — the bridge can still use "
                f"them if you pick them manually. Rename them to “{VIRTUAL_INPUT_PORT_NAME}” / "
                f"“{VIRTUAL_OUTPUT_PORT_NAME}” so they're picked automatically.",
            )
        else:
            self.row_endpoints.set(
                "bad", "No usable loopback ports found yet — follow the steps below."
            )

        if self.ports_lbl is not None:
            if in_names or out_names:
                self.ports_lbl.setText(
                    "Detected MIDI ports — in: " + (", ".join(in_names) or "none")
                    + "  ·  out: " + (", ".join(out_names) or "none")
                )
            else:
                self.ports_lbl.setText("Detected MIDI ports — none")

        dump = getattr(self._window, "dump", None)
        state = allow_midi_in_state(dump)
        if state is None:
            self.row_allow_in.set(
                "unknown", "“Allow MIDI in” — no data loaded, can't check (only affects "
                "computer → LF+ control; LF+ → computer output doesn't need it)."
            )
        elif state:
            self.row_allow_in.set("ok", "“Allow MIDI in” is YES — computer → LF+ control will work.")
        else:
            self.row_allow_in.set(
                "warn",
                "“Allow MIDI in” is OFF in the loaded data — DAW → LF+ commands will be "
                "ignored until it's set to YES (Global tab, then To LF+).",
            )

    def _open_bridge(self):
        self._window.open_midi_bridge()
        self.close()
