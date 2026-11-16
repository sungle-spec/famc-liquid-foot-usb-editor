"""Offline audit regressions: no device discovery, ports, or hardware commands."""
import hashlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lffirmware import codec
from lffirmware.images import ImageReport
from lffirmware.send import send_firmware
from lfeditor.comms.protocol import pull_records
from lfeditor.comms.transport import MidiTransport, SerialTransport


def _report(image):
    return ImageReport(path="synthetic.syx", size=len(image),
                       sha256=hashlib.sha256(image).hexdigest(), frame_ok=True,
                       data_bytes_ok=True, nibble_fraction=1.0, structure_ok=True,
                       header_model="12+")


@pytest.mark.parametrize("replacement", [b"invalid", codec.encode(bytes(1024), 6, 32, "H")])
def test_changed_firmware_rejected_before_midi_io(monkeypatch, replacement):
    image = codec.encode(bytes(1024), 6, 32, "K")
    midi = Mock()
    monkeypatch.setitem(sys.modules, "mido", midi)
    with pytest.raises(ValueError, match="changed since validation"):
        send_firmware("fake", replacement, _report(image), Mock())
    assert midi.mock_calls == []


def test_invalid_report_rejected_before_midi_io(monkeypatch):
    midi = Mock()
    monkeypatch.setitem(sys.modules, "mido", midi)
    with pytest.raises(ValueError, match="report is not valid"):
        send_firmware("fake", b"", ImageReport(path="bad"), Mock())
    assert midi.mock_calls == []


def test_firmware_output_open_failure_closes_input(monkeypatch):
    image = codec.encode(bytes(1024), 6, 32, "K")
    inp = Mock()
    midi = SimpleNamespace(Message=Mock(), get_input_names=lambda: ["fake"],
                           open_input=Mock(return_value=inp),
                           open_output=Mock(side_effect=OSError("open failed")))
    monkeypatch.setitem(sys.modules, "mido", midi)
    with pytest.raises(OSError, match="open failed"):
        send_firmware("fake", image, _report(image), Mock())
    inp.close.assert_called_once_with()


def test_midi_input_open_failure_closes_output(monkeypatch):
    out = Mock()
    monkeypatch.setitem(sys.modules, "mido", SimpleNamespace(
        open_output=Mock(return_value=out), open_input=Mock(side_effect=OSError("input failed"))))
    with pytest.raises(OSError, match="input failed"):
        MidiTransport("fake out", "fake in")
    out.close.assert_called_once_with()


class BufferedSerial:
    def __init__(self, data):
        self.data = data

    @property
    def in_waiting(self):
        return len(self.data)

    def read(self, n):
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk

    def reset_input_buffer(self):
        self.data = b""


def _serial(data):
    transport = SerialTransport.__new__(SerialTransport)
    transport.ser = BufferedSerial(data)
    return transport


def test_serial_coalesced_frames_survive_two_reads():
    first, second = b"\xf0\x01\xf7", b"\xf0\x02\xf7"
    transport = _serial(first + second)
    assert transport.read_one_frame(0.01) == first
    assert transport.read_one_frame(0.01) == second


def test_serial_frame_tail_available_to_raw_reader():
    transport = _serial(b"\xf0\x01\xf7tail")
    assert transport.read_one_frame(0.01) == b"\xf0\x01\xf7"
    assert transport.read_raw(idle_timeout=0, overall_timeout=0.01) == [b"tail"]


def test_serial_flush_clears_saved_tail():
    transport = _serial(b"\xf0\x01\xf7\xf0\x02\xf7")
    transport.read_one_frame(0.01)
    transport.flush_input()
    assert transport.read_one_frame(0.001) == b""


@pytest.mark.parametrize("size", [169, 172, 339])
def test_bulk_misaligned_reply_is_not_imported(size):
    transport = SimpleNamespace(send=Mock(), read_raw=Mock(return_value=[bytes(size)]))
    with pytest.raises(ValueError, match="Malformed bulk reply"):
        pull_records(transport, cmds=[0x05])


def test_odd_decoded_memory_reports_length_mismatch_without_crashing():
    frame = codec.encode(bytes(1024), 6, 32, "K")
    # Remove one decoded byte, retaining even nibble count and a parseable trailer.
    truncated = frame[:-7] + frame[-5:]
    decoded = codec.decode(truncated)
    assert len(decoded.memory) == 1023
    assert not decoded.length_ok


def test_loader_busy_window_refuses_close(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from lffirmware import gui
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui, "list_ports", lambda: [])
    win = gui.LoaderWindow()
    event = Mock()
    win._busy = True
    win.closeEvent(event)
    event.ignore.assert_called_once_with()
    win._busy = False
    win.close()
    win.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("failure", ["image", "log"])
def test_loader_preparation_failure_clears_busy(monkeypatch, failure):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from lffirmware import gui
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui, "list_ports", lambda: [])
    monkeypatch.setattr(gui.QMessageBox, "warning", lambda *args: QMessageBox.Yes)
    win = gui.LoaderWindow()
    win.rep = _report(b"synthetic")
    from unittest.mock import mock_open
    reader = Mock(side_effect=OSError("image unavailable")) if failure == "image" else mock_open(read_data=b"synthetic")
    monkeypatch.setattr("builtins.open", reader)
    monkeypatch.setattr(gui, "SessionLog", Mock(side_effect=OSError("log unavailable")))
    win.do_flash()
    assert not win._busy
    assert "Cannot prepare firmware send" in win.status.text()
    win.close()
    win.deleteLater()
    app.processEvents()
