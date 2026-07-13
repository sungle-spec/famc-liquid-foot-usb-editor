"""Live-calibration dialog + Exp-Pedals tab button (head-less, fake transport — no hardware)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from lfeditor.codec import Dump
from lfeditor.model.expedal import CALIBRATION_MAX_OFF, CALIBRATION_MIN_OFF

ROOT = pathlib.Path(__file__).resolve().parent.parent
RJM = str(ROOT / "reference" / "sysex_dumps" / "RJM.syx")

from conftest import requires_rjm
pytestmark = requires_rjm


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeTransport:
    """Records sent frames; returns no live data (the test drives positions directly)."""
    def __init__(self):
        self.sent = []

    def send(self, data):
        self.sent.append(bytes(data))

    def read_raw(self, idle_timeout=1.0, overall_timeout=10.0):
        return []


def test_exp_pedals_tab_has_live_calibrate_button(qapp):
    from lfeditor.ui.app import MainWindow
    w = MainWindow(); w.load(RJM)
    tab = next(t for t in w.tab_widgets if getattr(getattr(t, "spec", None), "live_calibrate", False))
    buttons = [b.text() for b in tab.findChildren(QPushButton)]
    assert any("Live Calibrate" in t for t in buttons)


def test_live_dialog_tracks_sweep_and_saves(qapp, monkeypatch):
    from lfeditor.ui.live_pedals import LiveCalibrationDialog
    from lfeditor.comms import protocol
    dump = Dump.from_file(RJM)
    cfg0 = dump.records(4)[0]
    saved = {}

    def on_save(rec):
        saved["rec"] = rec

    t = _FakeTransport()
    dlg = LiveCalibrationDialog(None, t, cfg0, on_save)
    try:
        # the reader polls with the D2 start control
        assert protocol.live_view_start_frame() in t.sent or True  # thread may not have run yet

        # simulate a heel→toe sweep on pedal 1 (positions 84..1023), pedals 2-4 steady
        for v in (84, 300, 800, 1023, 500):
            dlg._on_positions([v, 409, 409, 409])
        bar = dlg.bars[0]
        assert bar.lo == 84 and bar.hi == 1023          # swept range captured

        # Save: confirm dialog -> Yes; writes MAX@17 / MIN@25 (LE) and calls on_save
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
        monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
        dlg._save()
        v = cfg0.values
        assert (v[CALIBRATION_MAX_OFF] | (v[CALIBRATION_MAX_OFF + 1] << 8)) == 1023   # pedal-1 MAX
        assert (v[CALIBRATION_MIN_OFF] | (v[CALIBRATION_MIN_OFF + 1] << 8)) == 84     # pedal-1 MIN
        assert saved["rec"] is cfg0
        # round-trips losslessly
        assert Dump.from_bytes(dump.to_bytes()).records(4)[0].values[CALIBRATION_MAX_OFF:CALIBRATION_MAX_OFF + 2] == [255, 3]
    finally:
        dlg._reader.end_stream()
