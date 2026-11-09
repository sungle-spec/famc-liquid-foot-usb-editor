"""Long-transfer progress (status-bar bar + ETA) and the Complete Transfers menu contents."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib

import pytest

from lfeditor.progress import eta_seconds, format_duration, percent, progress_text

ROOT = pathlib.Path(__file__).resolve().parent.parent
FACTORY = str(ROOT / "lfeditor" / "resources" / "factory" / "Factory_Defaults12.syx")


# ---- pure formatting (runs everywhere) ----

def test_format_duration():
    assert format_duration(0) == "0:00"
    assert format_duration(5.4) == "0:05"
    assert format_duration(83) == "1:23"
    assert format_duration(3600) == "1:00:00"
    assert format_duration(3725) == "1:02:05"
    assert format_duration(-4) == "0:00"


def test_eta_needs_enough_data_then_extrapolates():
    assert eta_seconds(0, 100, 0.0) is None
    assert eta_seconds(1, 100, 10.0) is None              # too few records to extrapolate
    assert eta_seconds(5, 100, 1.0) is None               # too little elapsed time
    assert eta_seconds(10, 110, 20.0) == pytest.approx(200.0)   # 2 s/record * 100 left
    assert eta_seconds(100, 100, 50.0) == 0.0


def test_percent_clamps():
    assert (percent(0, 0), percent(50, 100), percent(120, 100)) == (0, 50, 100)


def test_progress_text_shape():
    t = progress_text("Sending", 123, 2346, 83.0, "Song #5")
    assert t.startswith("Sending 123 of 2,346 (5%)")
    assert "Song #5" in t and "1:23 elapsed" in t and "left" in t
    assert "estimating" in progress_text("Sending", 1, 2346, 0.5)
    assert "finishing" in progress_text("Sending", 10, 10, 5.0)


# ---- window wiring (offscreen Qt) ----

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from lfeditor.codec import Dump
from lfeditor.comms.protocol import WRITE_ACK


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class AckTransport:
    def __init__(self):
        self.sent = []

    def send(self, data):
        self.sent.append(bytes(data))

    def read_raw(self, idle_timeout=1.0, overall_timeout=10.0):
        return [WRITE_ACK]

    def read_frames(self, idle_timeout=1.0, overall_timeout=10.0):
        return self.read_raw()

    def flush_input(self):
        pass

    def close(self):
        pass


@pytest.fixture()
def win(qapp):
    from lfeditor.ui.app import MainWindow
    w = MainWindow()
    w.load(FACTORY)
    return w


def _menu_labels(w, title):
    """Action labels of the menu-bar menu `title`. Read while the QAction wrapper is alive:
    PySide deletes the menu if the temporary wrapper is dropped first."""
    for a in w.menuBar().actions():
        if a.text().replace("&", "") == title:
            return [x.text() for x in a.menu().actions()]
    raise AssertionError(f"no {title} menu")


def test_complete_transfers_has_get_edits_and_all(win):
    assert _menu_labels(win, "Complete Transfers") == [
        "Get All from LF+", "Send Edits to LF+", "Send All to LF+"]
    hw = _menu_labels(win, "Hardware")
    assert "Send Edits to LF+" in hw and "Send All to LF+" in hw       # still in Hardware too


def test_send_all_reports_each_record_then_completes(win):
    win.transport = AckTransport()
    frames = [f for f in win.dump.frames if f.type == 1][:6]            # Presets: ACK-only path
    calls = []

    class Emit:
        def __call__(self, msg):
            calls.append(("msg", msg))

        def steps(self, verb, done, total, current=""):
            calls.append((verb, done, total, current))

    written, failed = win._send_all(frames, Emit())
    assert len(written) == 6 and not failed
    steps = [c for c in calls if c[0] == "Sending"]
    assert [c[1] for c in steps] == [0, 1, 2, 3, 4, 5, 6]               # before each record + final
    assert all(c[2] == 6 for c in steps)
    assert steps[0][3].startswith("Preset #") and steps[-1][3] == ""


def test_send_all_tolerates_an_emitter_without_steps(win):
    win.transport = AckTransport()
    frames = [f for f in win.dump.frames if f.type == 1][:2]
    written, failed = win._send_all(frames, lambda msg: None)          # the test-harness stub shape
    assert len(written) == 2 and not failed
    win._send_all(frames)                                              # and no emitter at all


def test_status_bar_shows_progress_and_is_restored(win):
    win.status.setText("RJM.syx")
    win._set_busy(True, "writing 3 record(s)…")
    assert not win.progress_bar.isHidden()
    win._on_transfer_steps("Sending", 40, 100, "Song #9")
    assert win.progress_bar.maximum() == 100 and win.progress_bar.value() == 40
    assert win.status.text().startswith("Sending 40 of 100 (40%)")
    win._set_busy(False)
    assert win.progress_bar.isHidden() and win.status.text() == "RJM.syx"


def test_menu_paths_explain_when_not_connected(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: seen.append(a[2]) or QMessageBox.Ok))
    win.transport = None
    win.push_to_device()
    win.pull_from_device()
    win.push_all_to_device()
    assert len(seen) == 3 and all("Connect" in s for s in seen)
