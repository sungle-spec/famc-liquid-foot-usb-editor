"""Offline tests for the USB MIDI In Bridge (lfeditor/ui/midi_bridge.py).

The forwarding rules these lock in come from the 2026-07-15 hardware probe: the LF+ acts on
channel-voice CC/PC on its USB-serial UART (with the Allow-MIDI-CMDS global on), ignores
realtime, and its editor protocol shares the wire — so sysex must never be forwarded.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
mido = pytest.importorskip("mido")

from PySide6.QtWidgets import QApplication

from lfeditor.ui.midi_bridge import BridgeCore, wire_bytes, UsbMidiBridgeDialog


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class FakePort:
    def __init__(self, msgs):
        self._msgs = list(msgs)

    def iter_pending(self):
        while self._msgs:
            yield self._msgs.pop(0)

    def close(self):
        pass


class FakeTransport:
    def __init__(self):
        self.sent = []

    def send(self, data):
        self.sent.append(bytes(data))


# ---- wire_bytes: the filter is the safety property ----

def test_wire_bytes_passes_cc_and_pc_byte_identical():
    cc = mido.Message("control_change", channel=15, control=0, value=0)
    pc = mido.Message("program_change", channel=15, program=1)
    assert wire_bytes(cc) == bytes([0xBF, 0x00, 0x00])
    assert wire_bytes(pc) == bytes([0xCF, 0x01])


def test_wire_bytes_drops_everything_else():
    dropped = [
        mido.Message("sysex", data=[0x00, 0x00, 0x7C]),   # could collide with editor framing
        mido.Message("clock"),                              # firmware ignores realtime
        mido.Message("start"),
        mido.Message("note_on", note=60, velocity=100),     # outside the device's command set
        mido.Message("pitchwheel", pitch=1000),
    ]
    for msg in dropped:
        assert wire_bytes(msg) is None, f"{msg.type} should be dropped"


# ---- BridgeCore: forwarding, busy-pause, counters ----

def test_core_forwards_in_order():
    msgs = [mido.Message("control_change", channel=15, control=0, value=0),
            mido.Message("program_change", channel=15, program=5)]
    t = FakeTransport()
    core = BridgeCore(FakePort(msgs), t)
    core.pump()
    assert t.sent == [bytes([0xBF, 0x00, 0x00]), bytes([0xCF, 0x05])]
    assert core.forwarded == 2 and core.dropped_busy == 0


def test_core_drops_while_device_transfer_running():
    msgs = [mido.Message("program_change", channel=15, program=5)]
    t = FakeTransport()
    core = BridgeCore(FakePort(msgs), t, busy=lambda: True)
    core.pump()
    assert t.sent == []            # nothing may interleave into a record transfer
    assert core.dropped_busy == 1


def test_core_counts_filtered_messages():
    msgs = [mido.Message("clock"), mido.Message("note_on", note=1, velocity=1)]
    t = FakeTransport()
    core = BridgeCore(FakePort(msgs), t)
    core.pump()
    assert t.sent == [] and core.dropped_filtered == 2


# ---- dialog: headless construction + guard rails ----

class _StubWindow:
    transport = None
    dump = None
    _device_busy = False


def test_dialog_constructs_headless(qapp):
    from PySide6.QtWidgets import QMainWindow
    w = QMainWindow()
    dlg = UsbMidiBridgeDialog(w)
    assert dlg.start_btn.text() == "Start"
    dlg.close()


def test_dialog_start_offers_to_close_editor_session(qapp, monkeypatch):
    """The firmware discards MIDI commands in Editor Mode, so starting the bridge while the
    editor is connected must ask to disconnect — and declining leaves everything untouched."""
    from PySide6.QtWidgets import QMainWindow, QMessageBox
    w = QMainWindow()
    w.transport = object()   # an "open editor session"
    disconnected = []
    w.disconnect_device = lambda: disconnected.append(True)
    dlg = UsbMidiBridgeDialog(w)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    dlg.start()
    assert disconnected == [] and dlg._core is None and not dlg.running
    dlg.close()


def test_dialog_start_without_device_warns(qapp, monkeypatch):
    from PySide6.QtWidgets import QMainWindow, QMessageBox
    import lfeditor.comms as comms
    w = QMainWindow()
    w.transport = None
    dlg = UsbMidiBridgeDialog(w)
    monkeypatch.setattr(comms, "find_serial_ports", lambda: [])
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2] if len(a) > 2 else ""))
    dlg.start()
    assert warned and "No USB-serial" in warned[0]
    assert dlg._core is None and dlg._serial is None
    dlg.close()
