"""Quick Repeated Command Programmer + Re-order (Save/Sync) — engines and dialog wiring."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib

import pytest

from lfeditor.codec import Dump
from lfeditor import quickprog, reorder
from lfeditor.model.preset import CMDS_OFF as PRESET_CMDS_OFF, FUNC_MIDI
from lfeditor.model.song import SLOT_OFF as SONG_SLOT_OFF

ROOT = pathlib.Path(__file__).resolve().parent.parent
RJM = str(ROOT / "reference" / "sysex_dumps" / "RJM.syx")

from conftest import requires_rjm
pytestmark = requires_rjm


@pytest.fixture()
def dump():
    return Dump.from_file(RJM)


# ---- quick programmer ----

def test_quickprog_writes_row_across_range(dump):
    cmd = quickprog.midi_command(0xC, 1, 10, 0)        # PC ch1 prog 10
    n = quickprog.apply_command(dump, "preset_cmd", 5, 1, 4, cmd, pc_increment=True)
    assert n == 4
    for i, p in enumerate(dump.records(1)[:4]):
        o = PRESET_CMDS_OFF + 4 * 4                     # row 5
        assert p.values[o] == FUNC_MIDI
        assert p.values[o + 1] == 0xC0                 # PC, channel 1
        assert ((p.values[o + 2] << 8) | p.values[o + 3]) == 10 + i   # auto-increment


def test_quickprog_no_increment(dump):
    cmd = quickprog.midi_command(0xB, 2, 19, 64)       # CC ch2 #19 = 64
    quickprog.apply_command(dump, "song_cmd", 1, 1, 5, cmd, pc_increment=False)
    from lfeditor.model.song import CMDS_OFF as SCMD
    for s in dump.records(2)[:5]:
        assert s.values[SCMD] == FUNC_MIDI and s.values[SCMD + 1] == 0xB1
        assert s.values[SCMD + 2] == 19 and s.values[SCMD + 3] == 64


def test_quickprog_ia_areas_and_row_bounds(dump):
    quickprog.apply_command(dump, "ia_bypass", 20, 1, 2, quickprog.ia_command(10, 7))
    from lfeditor.model.iaswitch import BYPASS_CMDS_OFF
    o = BYPASS_CMDS_OFF + 19 * 4
    assert dump.records(3)[0].values[o] == 10 and dump.records(3)[0].values[o + 1] == 7
    with pytest.raises(ValueError):
        quickprog.apply_command(dump, "preset_cmd", 99, 1, 1, quickprog.empty_command())


def test_quickprog_round_trips(dump, tmp_path):
    quickprog.apply_command(dump, "preset_cmd", 1, 1, 384,
                            quickprog.midi_command(0xC, 1, 0, 0), pc_increment=True)
    p = str(tmp_path / "x.syx")
    dump.to_file(p)
    assert Dump.from_file(p).to_bytes() == pathlib.Path(p).read_bytes()


# ---- re-order + reference sync ----

def test_move_shifts_content(dump):
    p5 = dump.records(1)[4].name
    perm = reorder.move_record(dump, 1, 5, 2)
    assert perm[5] == 2
    assert dump.records(1)[1].name == p5           # content moved to slot 2
    assert dump.records(1)[2].name != p5           # others shifted down


def test_move_rewrites_song_references(dump):
    s1 = dump.records(2)[0]
    s1.values[SONG_SLOT_OFF] = 4                    # song1 slot1 -> preset 5 (raw 4)
    s1.values[SONG_SLOT_OFF + 1] = 0
    perm = reorder.move_record(dump, 1, 5, 2, sync_refs=True)
    raw = s1.values[SONG_SLOT_OFF] | (s1.values[SONG_SLOT_OFF + 1] << 8)
    assert raw + 1 == perm[5]                       # reference followed the content


def test_move_without_sync_leaves_references(dump):
    s1 = dump.records(2)[0]
    s1.values[SONG_SLOT_OFF] = 4
    s1.values[SONG_SLOT_OFF + 1] = 0
    reorder.move_record(dump, 1, 5, 2, sync_refs=False)
    raw = s1.values[SONG_SLOT_OFF] | (s1.values[SONG_SLOT_OFF + 1] << 8)
    assert raw + 1 == 5                             # unchanged


def test_song_move_rewrites_setlist_refs(dump):
    from lfeditor.model.setlist import SONG_SLOT_OFF as SL_OFF
    sl = dump.records(5)[0]
    sl.values[SL_OFF] = 9                           # set-list slot1 -> song 10
    perm = reorder.move_record(dump, 2, 10, 3, sync_refs=True)
    assert sl.values[SL_OFF] + 1 == perm[10]


def test_move_round_trips(dump, tmp_path):
    reorder.move_record(dump, 1, 50, 5)
    p = str(tmp_path / "x.syx")
    dump.to_file(p)
    assert Dump.from_file(p).to_bytes() == pathlib.Path(p).read_bytes()


# ---- dialog wiring ----

@pytest.fixture(scope="session")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_quickprog_dialog_applies(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    from lfeditor.ui.app import MainWindow
    from lfeditor.ui.quickprog_dialog import QuickProgDialog
    import lfeditor.model.preset as mp
    w = MainWindow(); w.load(RJM)
    qp = QuickProgDialog(w, lambda: w.dump, w._refresh_after_bulk_edit)
    qp.func.setCurrentIndex(1)                      # MIDI
    qp.mtype.setCurrentIndex(list(mp.MIDI_MSG_TYPES).index(0xC))
    qp.row.setValue(7); qp.lo.setValue(1); qp.hi.setValue(2); qp.d1.setValue(40)
    qp.apply()
    o = mp.CMDS_OFF + 6 * 4
    assert ((w.dump.records(1)[0].values[o + 2] << 8) | w.dump.records(1)[0].values[o + 3]) == 40
    assert w._dirty


def test_reorder_dialog_moves(qapp):
    from lfeditor.ui.app import MainWindow
    from lfeditor.ui.reorder_dialog import ReorderDialog
    w = MainWindow(); w.load(RJM)
    rd = ReorderDialog(w, lambda: w.dump, w._refresh_after_bulk_edit)
    assert rd.list.count() == 384
    p1 = w.dump.records(1)[0].name
    rd.list.setCurrentRow(0)
    rd._move(1, 3)
    assert w.dump.records(1)[2].name == p1 and w._dirty
