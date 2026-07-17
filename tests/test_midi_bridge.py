"""Offline tests for the bidirectional LF+ USB-MIDI bridge; all I/O uses fakes."""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
mido = pytest.importorskip("mido")

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

import lfeditor.comms as comms
import lfeditor.ui.midi_bridge as bridge_module
from lfeditor.ui.midi_bridge import (
    BridgeCore,
    UsbMidiBridgeDialog,
    is_identification_reply,
    wire_bytes,
)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeMidiPort:
    def __init__(self, msgs=(), events=None, name="midi", fail_send=False):
        self._msgs = list(msgs)
        self.events = events if events is not None else []
        self.name = name
        self.sent = []
        self.closed = False
        self.fail_send = fail_send

    def iter_pending(self):
        while self._msgs:
            yield self._msgs.pop(0)

    def send(self, msg):
        if self.fail_send:
            raise OSError("MIDI endpoint failed")
        self.sent.append(msg)

    def close(self):
        self.closed = True
        self.events.append(("midi_close", self.name))


class FakeSerial:
    def __init__(self, replies=None, available=(), events=None):
        self.sent = []
        self.replies = list(
            replies
            if replies is not None
            else [bytes.fromhex("f005007c06204b01000af7"), b""]
        )
        self.available = list(available)
        self.events = events if events is not None else []
        self.closed = False
        self.flushed = 0
        self.fail_read = False

    def send(self, data):
        payload = bytes(data)
        self.sent.append(payload)
        self.events.append(("serial_send", payload))

    def read_raw(self, idle_timeout=1.0, overall_timeout=10.0):
        if not self.replies:
            return []
        item = self.replies.pop(0)
        return [item] if item else []

    def read_available(self, max_bytes=4096):
        if self.fail_read:
            raise OSError("device removed")
        return self.available.pop(0) if self.available else b""

    def flush_input(self):
        self.flushed += 1
        self.available.clear()
        self.events.append(("serial_flush", None))

    def close(self):
        self.closed = True
        self.events.append(("serial_close", None))


def _window():
    w = QMainWindow()
    w.transport = None
    w.dump = None
    w._device_busy = False
    return w


def _install_start_fakes(monkeypatch, serial, midi_in=None, midi_out=None):
    midi_in = midi_in or FakeMidiPort(events=serial.events, name="input")
    midi_out = midi_out or FakeMidiPort(events=serial.events, name="output")
    monkeypatch.setattr(comms, "find_serial_ports", lambda: [SimpleNamespace(name="/dev/fake")])
    monkeypatch.setattr(comms, "SerialTransport", lambda _name: serial)
    monkeypatch.setattr(bridge_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(mido, "open_input", lambda *_a, **_k: midi_in)
    monkeypatch.setattr(mido, "open_output", lambda *_a, **_k: midi_out)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *_a, **_k: QMessageBox.Ok)
    return midi_in, midi_out


# ---- computer → LF+ filtering ----

def test_wire_bytes_passes_cc_pc_and_transport_realtime_byte_identical():
    messages = [
        (mido.Message("control_change", channel=15, control=0, value=0),
         bytes([0xBF, 0x00, 0x00])),
        (mido.Message("program_change", channel=15, program=1), bytes([0xCF, 0x01])),
        (mido.Message("clock"), bytes([0xF8])),
        (mido.Message("start"), bytes([0xFA])),
        (mido.Message("continue"), bytes([0xFB])),
        (mido.Message("stop"), bytes([0xFC])),
    ]
    for msg, expected in messages:
        assert wire_bytes(msg) == expected


def test_wire_bytes_drops_unverified_and_protocol_colliding_types():
    dropped = [
        mido.Message("sysex", data=[0x00, 0x00, 0x7C]),
        mido.Message("active_sensing"),
        mido.Message("reset"),
        mido.Message("note_on", note=60, velocity=100),
        mido.Message("pitchwheel", pitch=1000),
    ]
    assert all(wire_bytes(msg) is None for msg in dropped)


# ---- BridgeCore simultaneous pumping ----

def test_core_pumps_both_directions_and_emits_serial_message_once():
    midi_in = FakeMidiPort([
        mido.Message("control_change", channel=2, control=0, value=0),
        mido.Message("program_change", channel=2, program=5),
    ])
    midi_out = FakeMidiPort()
    serial = FakeSerial(replies=[], available=[bytes([0x92, 60, 100]), b""])
    core = BridgeCore(midi_in, midi_out, serial)

    core.pump()
    core.pump()

    assert serial.sent == [bytes([0xB2, 0, 0]), bytes([0xC2, 5])]
    assert [bytes(msg.bytes()) for msg in midi_out.sent] == [bytes([0x92, 60, 100])]
    assert core.daw_to_lf == 2
    assert core.lf_to_daw == 1


def test_core_preserves_fragmented_serial_message_between_pumps():
    midi_out = FakeMidiPort()
    serial = FakeSerial(replies=[], available=[bytes([0xE1, 1]), bytes([2])])
    core = BridgeCore(FakeMidiPort(), midi_out, serial)
    core.pump()
    assert midi_out.sent == []
    core.pump()
    assert [bytes(msg.bytes()) for msg in midi_out.sent] == [bytes([0xE1, 1, 2])]


def test_core_forwards_lf_realtime_and_ordinary_sysex_once():
    midi_out = FakeMidiPort()
    serial = FakeSerial(
        replies=[],
        available=[
            bytes.fromhex("b001f802fe") + bytes.fromhex("f07d0102f7"),
            b"",
        ],
    )
    core = BridgeCore(FakeMidiPort(), midi_out, serial)
    core.pump()
    core.pump()
    assert [bytes(msg.bytes()) for msg in midi_out.sent] == [
        bytes([0xF8]),
        bytes([0xB0, 1, 2]),
        bytes([0xFE]),
        bytes.fromhex("f07d0102f7"),
    ]
    assert core.lf_to_daw == 4


def test_core_forwards_only_safe_computer_realtime():
    midi_in = FakeMidiPort([
        mido.Message("clock"),
        mido.Message("start"),
        mido.Message("continue"),
        mido.Message("stop"),
        mido.Message("active_sensing"),
        mido.Message("reset"),
    ])
    serial = FakeSerial(replies=[])
    core = BridgeCore(midi_in, FakeMidiPort(), serial)
    core.pump()
    assert serial.sent == [
        bytes([0xF8]),
        bytes([0xFA]),
        bytes([0xFB]),
        bytes([0xFC]),
    ]
    assert core.daw_to_lf == 4
    assert core.dropped_filtered == 2


def test_core_drops_daw_messages_while_device_busy():
    midi_in = FakeMidiPort([mido.Message("program_change", channel=15, program=5)])
    serial = FakeSerial(replies=[])
    core = BridgeCore(midi_in, FakeMidiPort(), serial, busy=lambda: True)
    core.pump()
    assert serial.sent == []
    assert core.dropped_busy == 1


def test_core_counts_filtered_messages():
    midi_in = FakeMidiPort([
        mido.Message("active_sensing"),
        mido.Message("note_on", note=1, velocity=1),
    ])
    serial = FakeSerial(replies=[])
    core = BridgeCore(midi_in, FakeMidiPort(), serial)
    core.pump()
    assert serial.sent == []
    assert core.dropped_filtered == 2


def test_identification_reply_requires_complete_normal_device_frame():
    assert is_identification_reply(bytes.fromhex("00f005007c0620f7"))
    assert not is_identification_reply(bytes.fromhex("f005007a0620f7"))
    assert not is_identification_reply(bytes.fromhex("f005007c0620"))


# ---- dialog lifecycle and ordering ----

def test_dialog_constructs_headless(qapp):
    dlg = UsbMidiBridgeDialog(_window())
    assert dlg.start_btn.text() == "Start"
    assert "Bidirectional" in dlg.windowTitle()
    labels = [label.text() for label in dlg.findChildren(bridge_module.QLabel)]
    assert any("two-way MIDI connection" in text for text in labels)
    assert "MIDI to LF+:" in labels
    assert "MIDI from LF+:" in labels
    dlg.close()


def test_start_without_device_warns_and_opens_nothing(qapp, monkeypatch):
    warnings = []
    monkeypatch.setattr(comms, "find_serial_ports", lambda: [])
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: warnings.append(True))
    dlg = UsbMidiBridgeDialog(_window())
    dlg.start()
    assert warnings
    assert not dlg.running
    assert dlg._serial is None


def test_start_sequence_is_c9_then_ca_then_cf(qapp, monkeypatch):
    serial = FakeSerial()
    _install_start_fakes(monkeypatch, serial)
    dlg = UsbMidiBridgeDialog(_window())
    dlg.start()

    assert dlg.running
    assert serial.sent == [
        comms.handshake_frame(),
        comms.session_frame(),
        comms.usb_midi_stream_start_frame(),
    ]
    dlg.stop()


def test_stop_sends_cc_before_midi_and_serial_close_and_discards_input(qapp, monkeypatch):
    events = []
    serial = FakeSerial(events=events)
    midi_in = FakeMidiPort(events=events, name="input")
    midi_out = FakeMidiPort(events=events, name="output")
    _install_start_fakes(monkeypatch, serial, midi_in, midi_out)
    dlg = UsbMidiBridgeDialog(_window())
    dlg.start()
    dlg.stop()

    cc_event = ("serial_send", comms.usb_midi_stream_stop_frame())
    assert cc_event in events
    assert events.index(cc_event) < events.index(("midi_close", "input"))
    assert events.index(cc_event) < events.index(("serial_close", None))
    assert serial.flushed == 1
    assert not dlg.running


def test_repeated_stop_is_harmless(qapp, monkeypatch):
    serial = FakeSerial()
    _install_start_fakes(monkeypatch, serial)
    dlg = UsbMidiBridgeDialog(_window())
    dlg.start()
    dlg.stop()
    dlg.stop()
    assert serial.sent.count(comms.usb_midi_stream_stop_frame()) == 1


def test_invalid_handshake_never_sends_cf_or_opens_midi(qapp, monkeypatch):
    serial = FakeSerial(replies=[bytes.fromhex("f001f7"), b""])
    opened = []
    _install_start_fakes(monkeypatch, serial)
    monkeypatch.setattr(mido, "open_input", lambda *_a, **_k: opened.append("input"))
    monkeypatch.setattr(mido, "open_output", lambda *_a, **_k: opened.append("output"))
    dlg = UsbMidiBridgeDialog(_window())
    dlg.start()

    assert not dlg.running
    assert comms.usb_midi_stream_start_frame() not in serial.sent
    assert serial.sent[-1] == comms.usb_midi_stream_stop_frame()
    assert opened == []
    assert serial.closed


def test_partial_endpoint_start_failure_closes_every_opened_resource(qapp, monkeypatch):
    serial = FakeSerial()
    midi_in = FakeMidiPort(events=serial.events, name="input")
    _install_start_fakes(monkeypatch, serial, midi_in=midi_in)
    monkeypatch.setattr(mido, "open_output", lambda *_a, **_k: (_ for _ in ()).throw(
        OSError("output failed")
    ))
    dlg = UsbMidiBridgeDialog(_window())
    dlg.start()

    assert not dlg.running
    assert midi_in.closed
    assert serial.closed
    assert serial.sent[-1] == comms.usb_midi_stream_stop_frame()


def test_unplug_read_failure_transitions_to_stopped(qapp, monkeypatch):
    serial = FakeSerial()
    _install_start_fakes(monkeypatch, serial)
    dlg = UsbMidiBridgeDialog(_window())
    dlg.start()
    serial.fail_read = True
    dlg._poll()

    assert not dlg.running
    assert serial.closed
    assert "I/O failed" in dlg.state_lbl.text()


def test_failed_midi_send_uses_same_cleanup_boundary(qapp, monkeypatch):
    serial = FakeSerial(available=[bytes([0x90, 60, 100])])
    midi_out = FakeMidiPort(fail_send=True)
    _install_start_fakes(monkeypatch, serial, midi_out=midi_out)
    dlg = UsbMidiBridgeDialog(_window())
    dlg.start()
    dlg._poll()

    assert not dlg.running
    assert serial.sent[-1] == comms.usb_midi_stream_stop_frame()
    assert serial.closed


def test_start_offers_to_close_editor_session_and_decline_preserves_it(qapp, monkeypatch):
    w = _window()
    w.transport = object()
    disconnected = []
    w.disconnect_device = lambda: disconnected.append(True)
    dlg = UsbMidiBridgeDialog(w)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.No)
    dlg.start()
    assert disconnected == []
    assert not dlg.running


def test_start_closes_editor_session_before_opening_bridge(qapp, monkeypatch):
    serial = FakeSerial()
    _install_start_fakes(monkeypatch, serial)
    w = _window()
    w.transport = object()
    disconnected = []

    def disconnect():
        disconnected.append(True)
        w.transport = None

    w.disconnect_device = disconnect
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.Yes)
    dlg = UsbMidiBridgeDialog(w)
    dlg.start()

    assert disconnected == [True]
    assert dlg.running
    dlg.stop()


def test_start_refuses_to_interrupt_active_record_transfer(qapp, monkeypatch):
    w = _window()
    w._device_busy = True
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: warnings.append(True))
    dlg = UsbMidiBridgeDialog(w)
    dlg.start()
    assert warnings
    assert not dlg.running


def test_editor_connect_stops_running_bridge_before_port_discovery(qapp, monkeypatch):
    from lfeditor.ui.app import MainWindow

    class BridgeStub:
        running = True

        def __init__(self):
            self.stopped = 0

        def stop(self):
            self.stopped += 1

    window = MainWindow()
    bridge = BridgeStub()
    window._midi_bridge = bridge
    monkeypatch.setattr(comms, "find_serial_ports", lambda: [])
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: QMessageBox.Ok)
    window.connect_device()
    assert bridge.stopped == 1


def test_main_window_shutdown_stops_bridge(qapp):
    from lfeditor.ui.app import MainWindow

    class BridgeStub:
        def __init__(self):
            self.stopped = 0

        def stop(self):
            self.stopped += 1

    window = MainWindow()
    bridge = BridgeStub()
    window._midi_bridge = bridge
    window.close()
    assert bridge.stopped == 1
