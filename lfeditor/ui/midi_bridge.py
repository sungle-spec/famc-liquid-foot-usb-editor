"""Bidirectional LF+ USB-MIDI bridge over the hardware-confirmed FTDI serial stream.

The original editor's sequence is C9 (validated identification handshake), CA (session setup),
then CF (start live USB-MIDI). In that mode the same open serial link carries conservative
computer→LF+ CC/PC messages and raw LF+→computer channel MIDI. CC stops the stream before close.

macOS/Linux use one virtual input/output endpoint pair named ``LF+ IN PORT / LF+ OUT PORT``. python-rtmidi cannot
create virtual ports on Windows, so users select two existing loopback endpoints there. Editor
record transfers and bridge streaming remain mutually exclusive owners of the serial device.
"""
from __future__ import annotations

import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from ..comms.midi_stream import RawMidiStreamParser
from ..comms.transport import split_sysex

try:
    import mido
except Exception:  # noqa: BLE001
    mido = None

VIRTUAL_INPUT_PORT_NAME = "LF+ IN PORT"
VIRTUAL_OUTPUT_PORT_NAME = "LF+ OUT PORT"
STOP_SETTLE_SECONDS = 0.05
#: Proven CC/PC plus non-destructive transport/clock realtime. Active Sensing and System Reset
#: remain blocked computer→LF+.
FORWARD_TYPES = (
    "control_change",
    "program_change",
    "clock",
    "start",
    "continue",
    "stop",
)


def wire_bytes(msg) -> bytes | None:
    """Return byte-identical UART data for a safe computer-originated message, else ``None``.

    CC/PC retain the existing hardware-proven route. Clock/Start/Continue/Stop are safe
    single-byte realtime messages and are forwarded for hardware validation. Computer-originated
    SysEx, Active Sensing, System Reset, and unverified channel types remain filtered.
    """
    if getattr(msg, "type", None) not in FORWARD_TYPES:
        return None
    try:
        return bytes(msg.bytes())
    except Exception:  # noqa: BLE001
        return None


def is_identification_reply(data: bytes, model: int = 0x7C) -> bool:
    """Whether ``data`` contains the normal complete LF+ identification reply frame."""
    return any(
        len(frame) >= 5
        and frame[:4] == bytes([0xF0, 0x05, 0x00, model & 0x7F])
        and frame[-1] == 0xF7
        for frame in split_sysex(data)
    )


class BridgeCore:
    """UI-free simultaneous forwarding engine, directly testable with fake ports/transports."""

    def __init__(self, in_port, out_port, transport, busy=lambda: False, parser=None):
        self.in_port = in_port
        self.out_port = out_port
        self.transport = transport
        self.busy = busy
        self.parser = parser or RawMidiStreamParser()
        self.daw_to_lf = 0
        self.lf_to_daw = 0
        self.dropped_busy = 0
        self.dropped_filtered = 0

    def pump(self) -> None:
        """Perform one non-blocking pump in both directions.

        I/O exceptions deliberately propagate to the dialog's shared cleanup boundary.
        """
        for msg in self.in_port.iter_pending():
            data = wire_bytes(msg)
            if data is None:
                self.dropped_filtered += 1
                continue
            if self.busy():
                self.dropped_busy += 1
                continue
            self.transport.send(data)
            self.daw_to_lf += 1

        chunk = self.transport.read_available()
        if not chunk:
            return
        if mido is None:
            raise RuntimeError("mido is not available")
        for raw in self.parser.feed(chunk):
            self.out_port.send(mido.Message.from_bytes(list(raw)))
            self.lf_to_daw += 1

    def reset(self) -> None:
        self.parser.reset()


def _headless() -> bool:
    try:
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.platformName() == "offscreen"
    except Exception:  # noqa: BLE001
        return False


class UsbMidiBridgeDialog(QDialog):
    """Non-modal Hardware ▸ USB MIDI Bridge window. ``window`` is the MainWindow."""

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._core: BridgeCore | None = None
        self._midi_in = None
        self._midi_out = None
        self._serial = None
        self._session_active = False
        self._stream_started = False
        self._input_names: list[str] = []
        self._output_names: list[str] = []
        self._source_description = ""

        self.setWindowTitle("Bidirectional USB MIDI Bridge")
        self.setMinimumWidth(620)
        self.setWindowModality(Qt.NonModal)

        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._poll)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(QLabel(
            "Use your LF+ editor cable as a two-way MIDI connection between the LF+ and your\n"
            "computer.\n\n"
            "MIDI sent from the LF+ appears at the “LF+ OUT PORT”. Supported MIDI sent to\n"
            "the “LF+ IN PORT” is forwarded to the controller.\n\n"
            "Starting the bridge temporarily disconnects the editor. Stop the bridge and\n"
            "reconnect before reading or writing LF+ data.\n\n"
            "For computer-to-LF+ control, enable “Allow MIDI in” in the LF+ Global settings."))

        mode = QGridLayout()
        self.rb_virtual = QRadioButton(
            f"Create virtual ports “{VIRTUAL_INPUT_PORT_NAME}” and "
            f"“{VIRTUAL_OUTPUT_PORT_NAME}”"
        )
        self.rb_existing = QRadioButton("Use existing MIDI endpoints")
        if sys.platform.startswith("win"):
            self.rb_existing.setChecked(True)
            self.rb_virtual.setEnabled(False)
            self.rb_virtual.setToolTip(
                "python-rtmidi cannot create virtual MIDI ports on Windows. Create two distinct "
                "loopback ports (one per direction) and select them below."
            )
        else:
            self.rb_virtual.setChecked(True)
        mode.addWidget(self.rb_virtual, 0, 0, 1, 2)
        mode.addWidget(self.rb_existing, 0, 2, 1, 2)

        mode.addWidget(QLabel("MIDI to LF+:"), 1, 0)
        self.in_combo = QComboBox()
        self.in_combo.setMinimumWidth(220)
        mode.addWidget(self.in_combo, 1, 1)
        mode.addWidget(QLabel("MIDI from LF+:"), 1, 2)
        self.out_combo = QComboBox()
        self.out_combo.setMinimumWidth(220)
        mode.addWidget(self.out_combo, 1, 3)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_ports)
        mode.addWidget(refresh, 1, 4)
        root.addLayout(mode)

        self.rb_virtual.toggled.connect(self._sync_port_controls)
        self.rb_existing.toggled.connect(self._sync_port_controls)

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
        else:
            self._sync_port_controls()

    # ---- MIDI endpoints ----
    def refresh_ports(self):
        if mido is None:
            return
        try:
            self._input_names = list(mido.get_input_names())
        except Exception:  # noqa: BLE001 — backend may be unavailable
            self._input_names = []
        try:
            self._output_names = list(mido.get_output_names())
        except Exception:  # noqa: BLE001 — backend may be unavailable
            self._output_names = []

        self.in_combo.clear()
        self.in_combo.addItems(self._input_names or ["(no MIDI input ports)"])
        self.out_combo.clear()
        self.out_combo.addItems(self._output_names or ["(no MIDI output ports)"])
        self._sync_port_controls()

    def _sync_port_controls(self):
        existing = self.rb_existing.isChecked()
        self.in_combo.setEnabled(existing and bool(self._input_names))
        self.out_combo.setEnabled(existing and bool(self._output_names))

    def _open_midi_endpoints(self) -> str:
        if self.rb_virtual.isChecked():
            self._midi_in = mido.open_input(
                VIRTUAL_INPUT_PORT_NAME,
                virtual=True,
            )
            self._midi_out = mido.open_output(
                VIRTUAL_OUTPUT_PORT_NAME,
                virtual=True,
            )
            return (
                f"virtual ports “{VIRTUAL_INPUT_PORT_NAME}” / "
                f"“{VIRTUAL_OUTPUT_PORT_NAME}”"
            )

        if not self._input_names or not self._output_names:
            raise RuntimeError(
                "Select an existing MIDI input and output (Refresh to re-scan)."
            )

        in_name = self.in_combo.currentText()
        out_name = self.out_combo.currentText()

        if in_name == out_name:
            raise RuntimeError(
                "Choose distinct existing endpoints for the two directions to prevent "
                "a MIDI feedback loop."
            )

        self._midi_in = mido.open_input(in_name)
        self._midi_out = mido.open_output(out_name)
        return f"{in_name} / {out_name}"

    # ---- start / stop ----
    def toggle(self):
        if self._core is None:
            self.start()
        else:
            self.stop()

    def start(self):
        if mido is None or self._core is not None:
            return
        # A previous partial failure should never leak ownership into a restart attempt.
        if self._serial is not None or self._midi_in is not None or self._midi_out is not None:
            self.stop()

        if getattr(self._window, "_device_busy", False):
            QMessageBox.warning(
                self,
                "USB MIDI Bridge",
                "A device record transfer is still running. Wait for it to finish before "
                "starting the MIDI bridge.",
            )
            return

        if getattr(self._window, "transport", None) is not None:
            if QMessageBox.question(
                self,
                "USB MIDI Bridge",
                "An Editor Mode record session is active.\n\n"
                "Disconnect it cleanly and start the bidirectional MIDI bridge?",
            ) != QMessageBox.Yes:
                return
            self._window.disconnect_device()
            if getattr(self._window, "transport", None) is not None:
                QMessageBox.warning(
                    self, "USB MIDI Bridge", "The editor connection did not close; bridge not started."
                )
                return

        self._warn_if_midi_cmds_off()

        from ..comms import (
            MODEL_FOOT,
            SerialTransport,
            connect,
            find_serial_ports,
            usb_midi_stream_start_frame,
        )

        ports = find_serial_ports()
        if not ports:
            QMessageBox.warning(
                self,
                "USB MIDI Bridge",
                "No USB-serial device found.\n\n"
                "Plug in the Liquid Foot+ (its FTDI port must be at PID 0x6015).",
            )
            return

        try:
            self._serial = SerialTransport(ports[0].name)
            # From this point even a failed/invalid handshake is cleaned up with context-sensitive
            # CC while the port remains open, so the device cannot be stranded in Editor Mode.
            self._session_active = True
            reply = connect(self._serial, MODEL_FOOT)
            if not is_identification_reply(reply, MODEL_FOOT):
                raise RuntimeError(
                    "LF+ identification handshake failed; C9/CA completed without a valid reply."
                )
            self._serial.send(usb_midi_stream_start_frame(MODEL_FOOT))
            self._stream_started = True
            self._source_description = self._open_midi_endpoints()
            self._core = BridgeCore(
                self._midi_in,
                self._midi_out,
                self._serial,
                busy=lambda: getattr(self._window, "_device_busy", False),
            )
        except Exception as exc:  # noqa: BLE001
            self.stop()
            QMessageBox.critical(self, "USB MIDI Bridge", f"Could not start the bridge:\n{exc}")
            return

        self._timer.start()
        self.start_btn.setText("Stop")
        self._update_running_status()

    def stop(self, reason: str | None = None):
        """Idempotent shared cleanup for Stop, close, failure, unplug, and app shutdown."""
        self._timer.stop()

        core = self._core
        midi_in = self._midi_in
        midi_out = self._midi_out
        serial = self._serial
        session_active = self._session_active

        # Clear ownership first so a nested/repeated cleanup is harmless.
        self._core = None
        self._midi_in = None
        self._midi_out = None
        self._serial = None
        self._session_active = False
        self._stream_started = False
        self._source_description = ""

        if serial is not None and session_active:
            from ..comms import MODEL_FOOT, usb_midi_stream_stop_frame

            try:
                serial.send(usb_midi_stream_stop_frame(MODEL_FOOT))
                time.sleep(STOP_SETTLE_SECONDS)
            except Exception:  # noqa: BLE001 — unplug still continues through all cleanup
                pass
            try:
                # Stop-only discard: normal streaming exclusively uses read_available() and never
                # resets the input buffer.
                serial.flush_input()
            except Exception:  # noqa: BLE001
                pass

        # MIDI endpoints close before the serial transport, matching the explicit lifecycle.
        for endpoint in (midi_in, midi_out):
            try:
                if endpoint is not None:
                    endpoint.close()
            except Exception:  # noqa: BLE001
                pass
        if serial is not None:
            try:
                serial.close()
            except Exception:  # noqa: BLE001
                pass
        if core is not None:
            core.reset()

        self.start_btn.setText("Start")
        if reason:
            self.state_lbl.setText(f"stopped — {reason}")
        elif core is not None:
            self.state_lbl.setText(
                f"stopped — DAW → LF+: {core.daw_to_lf}  ·  LF+ → DAW: {core.lf_to_daw}"
            )
        else:
            self.state_lbl.setText("stopped")

    @property
    def running(self) -> bool:
        return self._core is not None

    def _warn_if_midi_cmds_off(self):
        """Passive check only; never auto-write the device global."""
        dump = getattr(self._window, "dump", None)
        if dump is None:
            return
        cfg0 = next((f for f in dump.frames if f.type == 4 and f.rec_num == 0), None)
        if cfg0 is not None and len(cfg0.values) > 47 and cfg0.values[47] == 0:
            QMessageBox.warning(
                self,
                "USB MIDI Bridge",
                "The device global “Allow MIDI in” is OFF in the loaded data — DAW → LF+ "
                "commands will be ignored until it is set to YES (Global tab, then To LF+; or "
                "the front-panel Global menu). LF+ → DAW output does not use that write route.",
            )

    # ---- polling ----
    def _update_running_status(self):
        core = self._core
        if core is None:
            return
        self.state_lbl.setText(
            f"bridging {self._source_description}  ·  DAW → LF+: {core.daw_to_lf}"
            f"  ·  LF+ → DAW: {core.lf_to_daw}"
        )

    def _poll(self):
        core = self._core
        if core is None:
            return
        try:
            core.pump()
        except Exception as exc:  # noqa: BLE001 — serial removal or MIDI endpoint failure
            self.stop(f"I/O failed ({exc})")
            return
        self._update_running_status()

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)
