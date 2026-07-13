"""
Drag-drop from Find/Q-LIST, right-click multi-record toggle edit, and the MIDI monitor.
All head-less (offscreen Qt).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from lfeditor.ui import dnd
from lfeditor.ui.fields import SlotPickerField, CommandTableField, ToggleField, _DropCombo

ROOT = pathlib.Path(__file__).resolve().parent.parent
RJM = str(ROOT / "reference" / "sysex_dumps" / "RJM.syx")

from conftest import requires_rjm
pytestmark = requires_rjm


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    from lfeditor.ui.app import MainWindow
    w = MainWindow()
    w.load(RJM)
    return w


def _tab(win, type_):
    return next(t for t in win.tab_widgets if getattr(t, "type_", None) == type_)


# ---- drag-drop ----

def test_mime_round_trip():
    md = dnd.encode(3, 42)
    assert dnd.decode(md) == (3, 42)
    from PySide6.QtCore import QMimeData
    assert dnd.decode(QMimeData()) is None


def test_slotpicker_assign_by_drop(win):
    songs = _tab(win, 2)
    songs.rail.list.setCurrentRow(0)
    sp = next(f for f in songs._all_fields if isinstance(f, SlotPickerField))
    assert isinstance(sp.combos[0], _DropCombo) and sp.target_type == 1
    sp._assign(2, 300)   # slot 3 <- preset 300
    from lfeditor.model.song import SLOT_OFF
    off = SLOT_OFF + 2 * 2
    raw = songs.current_record().values[off] | (songs.current_record().values[off + 1] << 8)
    assert raw + 1 == 300


class _FakeDrop:
    """A minimal stand-in for a drop event (constructing a real QDropEvent and dispatching it
    directly is unsupported and crashes under pytest; the type-gating logic is what matters)."""
    def __init__(self, md):
        self._md = md

    def mimeData(self):
        return self._md


def test_dropcombo_type_gating(win):
    songs = _tab(win, 2)
    songs.rail.list.setCurrentRow(0)
    sp = next(f for f in songs._all_fields if isinstance(f, SlotPickerField))
    combo = sp.combos[0]
    assert combo._ref(_FakeDrop(dnd.encode(1, 5))) == (1, 5)   # preset accepted
    assert combo._ref(_FakeDrop(dnd.encode(3, 5))) is None     # IA-slot rejected


def test_command_table_drop_gating(win):
    ia = _tab(win, 3)
    ia.rail.list.setCurrentRow(0)
    ct = next(f for f in ia._all_fields if isinstance(f, CommandTableField))
    assert ct.w._ref(_FakeDrop(dnd.encode(3, 7))) == (3, 7)    # IA-slot accepted
    assert ct.w._ref(_FakeDrop(dnd.encode(1, 7))) is None      # preset rejected


def test_command_table_ia_drop(win):
    ia = _tab(win, 3)
    ia.rail.list.setCurrentRow(0)
    ct = next(f for f in ia._all_fields if isinstance(f, CommandTableField))
    ct.set_ia_command(0, 7)
    from lfeditor.model.iaswitch import ON_CMDS_OFF
    vals = ia.current_record().values
    assert vals[ON_CMDS_OFF] == 10 and vals[ON_CMDS_OFF + 1] == 7   # IA ON Trig, slot 7


# ---- right-click multi-record toggle edit ----

def test_multi_apply_toggle_all_and_range(win):
    presets = win.tab_widgets[0]
    presets.rail.list.setCurrentRow(0)
    tf = next(f for f in presets._all_fields if isinstance(f, ToggleField))
    assert tf._apply_fn is not None
    off, mask = tf.offset, tf.bitmask

    tf._apply_fn(off, mask, True, 1, 384)
    assert all(r.values[off] & mask for r in win.dump.records(1))

    tf._apply_fn(off, mask, False, 10, 20)
    assert all(not (r.values[off] & mask) for r in win.dump.records(1) if 10 <= r.number <= 20)
    assert win.dump.records(1)[0].values[off] & mask     # preset 1 (outside range) untouched


def test_multi_apply_keeps_round_trip(win, tmp_path):
    from lfeditor.codec import Dump
    presets = win.tab_widgets[0]
    presets.rail.list.setCurrentRow(0)
    tf = next(f for f in presets._all_fields if isinstance(f, ToggleField))
    tf._apply_fn(tf.offset, tf.bitmask, True, 1, 50)
    p = str(tmp_path / "x.syx")
    win.dump.to_file(p)
    assert Dump.from_file(p).to_bytes() == pathlib.Path(p).read_bytes()


# ---- MIDI monitor ----

def test_midi_monitor_builds_and_logs(qapp):
    import time
    import mido
    from lfeditor.ui.midi_monitor import MidiMonitorDialog
    mm = MidiMonitorDialog()
    mm._t0 = time.monotonic()
    mm._log(mido.Message("control_change", channel=1, control=19, value=12))
    mm._log(mido.Message("program_change", channel=2, program=20))
    assert mm.table.rowCount() == 2
    assert mm.table.item(0, 1).text() == "B1 13 0C"
    assert "control_change" in mm.table.item(0, 2).text()
    mm.clear_log()
    assert mm.table.rowCount() == 0


def test_qlist_dock_follows_tab(qapp):
    from lfeditor.ui.app import MainWindow
    from lfeditor.ui import dnd
    TAB = ["Presets", "Set-List", "IA-Slot", "IA-Maps", "Midi/Groups", "Global",
           "Songs", "Pages", "Sysex Msgs", "Exp Pedals", "Colors"]
    w = MainWindow(); w.load(RJM)
    ql = w.qlist

    # the per-tab record rails are hidden (Q-LIST replaces them)
    assert not w.tab_widgets[0].rail.isVisibleTo(w.tab_widgets[0])

    # Q-LIST follows the current tab; record tabs list their type, others are empty
    expect = {"Presets": (1, 384), "Songs": (2, 254), "IA-Slot": (3, 180), "IA-Maps": (8, 60),
              "Pages": (7, 50), "Sysex Msgs": (6, 255), "Set-List": (5, 128)}
    for name, (type_, count) in expect.items():
        w.tabs.setCurrentIndex(TAB.index(name))
        assert ql._type == type_ and ql.list.count() == count
    for name in ("Global", "Midi/Groups", "Exp Pedals", "Colors"):
        w.tabs.setCurrentIndex(TAB.index(name))
        assert ql._type is None and ql.list.count() == 0

    # a type button switches tabs
    w._qlist_pick_type(2)
    assert w.tabs.tabText(w.tabs.currentIndex()) == "Songs"

    # single-click an item navigates to that record
    w.tabs.setCurrentIndex(0)
    ql.filter.setText("MOTP"); assert ql.list.count() == 4
    ql.filter.setText("")
    ql._jump(ql.list.item(4))
    assert w.tabs.tabText(w.tabs.currentIndex()) == "Presets"
    assert w.tab_widgets[0].current_record().number == 5

    # rows remain draggable with the record reference
    assert dnd.decode(ql.list.mimeData([ql.list.item(0)])) == (1, 1)
    w.act_qlist.setChecked(False); w.act_qlist.setChecked(True)


def test_midi_monitor_save_log(qapp, tmp_path, monkeypatch):
    import time
    import mido
    from PySide6.QtWidgets import QFileDialog
    from lfeditor.ui.midi_monitor import MidiMonitorDialog
    mm = MidiMonitorDialog()
    mm._t0 = time.monotonic()
    mm._log(mido.Message("note_on", channel=0, note=60, velocity=64))
    out = str(tmp_path / "log.csv")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (out, "")))
    mm.save_log()
    text = pathlib.Path(out).read_text()
    assert "Bytes (hex)" in text and "90 3C 40" in text
