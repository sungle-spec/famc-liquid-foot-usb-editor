"""Offline tests for the USB MIDI Bridge Setup wizard checklist; all I/O uses fakes."""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("mido")

from PySide6.QtWidgets import QApplication, QMainWindow

import lfeditor.ui.midi_bridge_wizard as wizard_module
from lfeditor.comms import PortInfo
from lfeditor.ui.midi_bridge_wizard import MidiBridgeSetupWizard


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _window():
    w = QMainWindow()
    w.dump = None
    w.open_midi_bridge = lambda: None
    return w


def _patch_ports(monkeypatch, serial=(), midi_in=(), midi_out=()):
    monkeypatch.setattr(
        wizard_module, "find_serial_ports",
        lambda: [PortInfo("serial", n, n) for n in serial],
    )
    monkeypatch.setattr(
        wizard_module, "find_midi_ports",
        lambda: (
            [PortInfo("midi-in", n, n) for n in midi_in],
            [PortInfo("midi-out", n, n) for n in midi_out],
        ),
    )


def _dot_color(row) -> str:
    return row.dot.styleSheet()


def test_macos_endpoints_row_is_always_ready(qapp, monkeypatch):
    monkeypatch.setattr(wizard_module.sys, "platform", "darwin")
    _patch_ports(monkeypatch)
    dlg = MidiBridgeSetupWizard(_window())
    assert "nothing to set up" in dlg.row_endpoints.text.text()
    assert dlg.ports_lbl is None
    dlg.close()


def test_windows_no_ports_is_not_ready(qapp, monkeypatch):
    monkeypatch.setattr(wizard_module.sys, "platform", "win32")
    _patch_ports(monkeypatch)
    dlg = MidiBridgeSetupWizard(_window())
    assert "No usable loopback ports" in dlg.row_endpoints.text.text()
    assert dlg.ports_lbl is not None
    assert "none" in dlg.ports_lbl.text()
    dlg.close()


def test_windows_generic_ports_are_usable_but_flagged(qapp, monkeypatch):
    monkeypatch.setattr(wizard_module.sys, "platform", "win32")
    _patch_ports(monkeypatch, midi_in=["Foo In"], midi_out=["Foo Out"])
    dlg = MidiBridgeSetupWizard(_window())
    assert "not named to match" in dlg.row_endpoints.text.text()
    dlg.close()


def test_windows_recommended_names_are_ready(qapp, monkeypatch):
    monkeypatch.setattr(wizard_module.sys, "platform", "win32")
    _patch_ports(monkeypatch, midi_in=["LF+ IN PORT"], midi_out=["LF+ OUT PORT"])
    dlg = MidiBridgeSetupWizard(_window())
    assert "detected" in dlg.row_endpoints.text.text()
    assert "LF+ IN PORT" in dlg.ports_lbl.text()
    dlg.close()


def test_refresh_reruns_discovery(qapp, monkeypatch):
    monkeypatch.setattr(wizard_module.sys, "platform", "win32")
    _patch_ports(monkeypatch)
    dlg = MidiBridgeSetupWizard(_window())
    assert "No usable loopback ports" in dlg.row_endpoints.text.text()

    _patch_ports(monkeypatch, midi_in=["LF+ IN PORT"], midi_out=["LF+ OUT PORT"])
    dlg.refresh()
    assert "detected" in dlg.row_endpoints.text.text()
    dlg.close()


def test_device_row_reflects_serial_ports(qapp, monkeypatch):
    _patch_ports(monkeypatch, serial=["/dev/fake"])
    dlg = MidiBridgeSetupWizard(_window())
    assert "/dev/fake" in dlg.row_device.text.text()
    dlg.close()

    _patch_ports(monkeypatch)
    dlg2 = MidiBridgeSetupWizard(_window())
    assert "not detected" in dlg2.row_device.text.text()
    dlg2.close()


def test_open_bridge_button_invokes_window_and_closes(qapp, monkeypatch):
    _patch_ports(monkeypatch)
    window = _window()
    opened = []
    window.open_midi_bridge = lambda: opened.append(True)
    dlg = MidiBridgeSetupWizard(window)
    dlg.show()
    dlg._open_bridge()
    assert opened
    assert not dlg.isVisible()


# ---- allow_midi_in_state via the dialog's row ----

def test_allow_in_row_unknown_without_dump(qapp, monkeypatch):
    _patch_ports(monkeypatch)
    dlg = MidiBridgeSetupWizard(_window())
    assert "no data loaded" in dlg.row_allow_in.text.text()
    dlg.close()


def test_allow_in_row_reflects_dump_state(qapp, monkeypatch):
    _patch_ports(monkeypatch)
    window = _window()
    frame = SimpleNamespace(type=4, rec_num=0, values=[0] * 48)
    window.dump = SimpleNamespace(frames=[frame])
    dlg = MidiBridgeSetupWizard(window)
    assert "OFF" in dlg.row_allow_in.text.text()

    frame.values[47] = 1
    dlg.refresh()
    assert "YES" in dlg.row_allow_in.text.text()
    dlg.close()
