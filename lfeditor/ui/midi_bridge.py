"""
USB MIDI In Bridge — drive the LF+ from a DAW/sequencer over the editor's USB cable.

**Hardware-confirmed 2026-07-15**: with the device global "Allow MIDI CMDS = YES", the LF+
acts on channel-voice MIDI (Bank CC#0 / Program Change / the manual's CC#1-8 trigger set)
arriving raw on its USB-serial UART. **Editor Mode blocks those commands** (confirmed: a PC
sent mid-session is discarded, not just hidden by the LCD), so the bridge and the editor
session are mutually exclusive uses of the port: the bridge opens the serial port itself,
WITHOUT the Editor-Mode handshake, and starting it offers to close an active editor session.
This recovers the useful half of the old FAMC driver's "USB MIDI port": computer→device MIDI
commands. (The other half stays firmware-limited: the device never sources MIDI on the UART,
and realtime clock is ignored.)

The bridge exposes a MIDI *input* the rest of the computer can see and forwards what arrives
to the device:

* macOS / Linux: creates a **virtual port "LF+ USB"** (rtmidi virtual ports) — pick it as a
  MIDI output in any DAW.
* Windows: rtmidi can't create virtual ports; pick an existing loopback input instead
  (e.g. a loopMIDI port) from the dropdown.

Only Control Change + Program Change are forwarded (the device's documented MIDI command set);
sysex is dropped so DAW traffic can never collide with the device's F0…F7 protocol framing,
and realtime is dropped because the firmware ignores it. Polling runs on a Qt timer, same
pattern as the MIDI Monitor.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QRadioButton,
    QMessageBox,
)

try:
    import mido
except Exception:  # noqa: BLE001
    mido = None

VIRTUAL_PORT_NAME = "LF+ USB"
#: message types the LF+ documents in its MIDI Implementation chart (PC + the CC trigger set)
FORWARD_TYPES = ("control_change", "program_change")


def wire_bytes(msg) -> bytes | None:
    """The exact bytes to put on the UART for one mido message — or None to drop it.

    Channel-voice CC/PC pass through byte-identical; everything else (sysex, realtime, notes,
    pitch-bend…) is dropped: sysex could collide with the editor's own F0…F7 framing, and the
    rest is outside the device's documented MIDI command set."""
    if getattr(msg, "type", None) not in FORWARD_TYPES:
        return None
    try:
        return bytes(msg.bytes())
    except Exception:  # noqa: BLE001
        return None


class BridgeCore:
    """The forwarding engine, UI-free so it can be tested against fakes.

    `pump()` drains the MIDI input and writes each forwardable message to the transport,
    unless `busy()` says a device transfer is running — then messages are dropped (not
    queued: replaying stale preset changes after a long transfer would be worse)."""

    def __init__(self, in_port, transport, busy=lambda: False):
        self.in_port = in_port
        self.transport = transport
        self.busy = busy
        self.forwarded = 0
        self.dropped_busy = 0
        self.dropped_filtered = 0

    def pump(self) -> None:
        for msg in self.in_port.iter_pending():
            data = wire_bytes(msg)
            if data is None:
                self.dropped_filtered += 1
                continue
            if self.busy():
                self.dropped_busy += 1
                continue
            self.transport.send(data)
            self.forwarded += 1


def _headless() -> bool:
    try:
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.platformName() == "offscreen"
    except Exception:  # noqa: BLE001
        return False


class UsbMidiBridgeDialog(QDialog):
    """Non-modal Hardware ▸ USB MIDI In Bridge window. `window` is the MainWindow.

    The bridge opens the serial port itself, RAW (no Editor-Mode handshake) — the firmware
    discards MIDI commands while in Editor Mode, so bridging and the editor session cannot
    share the link. Starting the bridge offers to close an active editor session first, and
    the editor's Connect stops a running bridge (see MainWindow.connect_device)."""

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._core: BridgeCore | None = None
        self._port = None       # the mido input (virtual or existing)
        self._serial = None     # our own raw SerialTransport

        self.setWindowTitle("USB MIDI In Bridge")
        self.setMinimumWidth(520)
        self.setWindowModality(Qt.NonModal)

        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._poll)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(QLabel(
            "Send MIDI commands to the LF+ over this USB cable — preset changes (Bank + PC)\n"
            "and the manual's CC trigger set (IA on/off/bypass/toggle, page functions, MTC).\n"
            "Requires the device global “Allow MIDI CMDS = YES” (Global tab, or the front\n"
            "panel’s Global menu). The device ignores MIDI while in Editor Mode, so starting\n"
            "the bridge closes any editor connection — reconnect to transfer records again."))

        mode = QHBoxLayout()
        self.rb_virtual = QRadioButton(f"Create virtual port “{VIRTUAL_PORT_NAME}”")
        self.rb_existing = QRadioButton("Listen on existing input:")
        self.in_combo = QComboBox()
        self.in_combo.setMinimumWidth(200)
        if sys.platform.startswith("win"):
            # rtmidi can't create virtual ports on Windows — use a loopMIDI port instead.
            self.rb_existing.setChecked(True)
            self.rb_virtual.setEnabled(False)
            self.rb_virtual.setToolTip("Windows can’t create virtual MIDI ports — install "
                                       "loopMIDI and pick its port here instead.")
        else:
            self.rb_virtual.setChecked(True)
        mode.addWidget(self.rb_virtual)
        mode.addWidget(self.rb_existing)
        mode.addWidget(self.in_combo)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_ports)
        mode.addWidget(refresh)
        mode.addStretch(1)
        root.addLayout(mode)

        ctrl = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.toggle)
        ctrl.addWidget(self.start_btn)
        self.state_lbl = QLabel("stopped")
        ctrl.addWidget(self.state_lbl, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        ctrl.addWidget(close)
        root.addLayout(ctrl)

        if mido is None:
            self.state_lbl.setText("mido not available")
            self.start_btn.setEnabled(False)
        elif not _headless():
            self.refresh_ports()

    # ---- ports ----
    def refresh_ports(self):
        if mido is None:
            return
        try:
            ins = mido.get_input_names()
        except Exception:  # noqa: BLE001 — no MIDI backend
            ins = []
        self.in_combo.clear()
        self.in_combo.addItems(ins or ["(no MIDI input ports)"])
        self.in_combo.setEnabled(bool(ins))

    # ---- start / stop ----
    def toggle(self):
        if self._core is None:
            self.start()
        else:
            self.stop()

    def start(self):
        if mido is None:
            return
        # The firmware discards MIDI commands in Editor Mode — an editor session must end first.
        if getattr(self._window, "transport", None) is not None:
            if QMessageBox.question(
                self, "USB MIDI In Bridge",
                "The LF+ ignores MIDI commands while in Editor Mode.\n\n"
                "Close the editor connection and start the bridge?",
            ) != QMessageBox.Yes:
                return
            self._window.disconnect_device()
        self._warn_if_midi_cmds_off()

        from ..comms import find_serial_ports, SerialTransport
        ports = find_serial_ports()
        if not ports:
            QMessageBox.warning(self, "USB MIDI In Bridge", "No USB-serial device found.\n\n"
                                "Plug in the Liquid Foot+ (its FTDI port must be at PID 0x6015).")
            return
        try:
            # Raw open — deliberately NO Editor-Mode handshake.
            self._serial = SerialTransport(ports[0].name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "USB MIDI In Bridge", f"Could not open the port:\n{exc}")
            return
        try:
            if self.rb_virtual.isChecked():
                self._port = mido.open_input(VIRTUAL_PORT_NAME, virtual=True)
                src = f"virtual port “{VIRTUAL_PORT_NAME}”"
            else:
                name = self.in_combo.currentText()
                self._port = mido.open_input(name)
                src = name
        except Exception as exc:  # noqa: BLE001
            self._serial.close()
            self._serial = None
            QMessageBox.critical(self, "USB MIDI In Bridge", f"Could not open port:\n{exc}")
            return
        self._core = BridgeCore(self._port, self._serial,
                                busy=lambda: getattr(self._window, "_device_busy", False))
        self._timer.start()
        self.start_btn.setText("Stop")
        self.state_lbl.setText(f"bridging {src} → LF+")

    def stop(self):
        self._timer.stop()
        for p in (self._port, self._serial):
            try:
                if p is not None:
                    p.close()
            except Exception:  # noqa: BLE001
                pass
        core, self._core, self._port, self._serial = self._core, None, None, None
        self.start_btn.setText("Start")
        if core is not None:
            self.state_lbl.setText(f"stopped — forwarded {core.forwarded} message(s)")
        else:
            self.state_lbl.setText("stopped")

    @property
    def running(self) -> bool:
        return self._core is not None

    def _warn_if_midi_cmds_off(self):
        """Passive check: if the loaded dump says Allow-MIDI-in is OFF, say so (never
        auto-write a device global)."""
        dump = getattr(self._window, "dump", None)
        if dump is None:
            return
        cfg0 = next((f for f in dump.frames if f.type == 4 and f.rec_num == 0), None)
        if cfg0 is not None and len(cfg0.values) > 47 and cfg0.values[47] == 0:
            QMessageBox.warning(self, "USB MIDI In Bridge",
                                "The device global “Allow MIDI CMDS” is OFF in the loaded "
                                "data — the LF+ will ignore bridged commands until it is set "
                                "to YES (Global tab, then To LF+; or the front-panel Global "
                                "menu).")

    # ---- polling ----
    def _poll(self):
        core = self._core
        if core is None:
            return
        try:
            core.pump()
        except Exception:  # noqa: BLE001 — serial gone (device unplugged)
            self.stop()
            self.state_lbl.setText("stopped — the serial port went away (device unplugged?)")
            return
        if core.forwarded:
            self.state_lbl.setText(self.state_lbl.text().split("  ·")[0]
                                   + f"  · {core.forwarded} forwarded")

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)
