"""
Whole-record copy / paste / clear (the toolbar's clear/copy/paste buttons) + the rail
selection-preservation fix. Mirrors the behaviour observed in the original LF+ Editor v6.31.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import tempfile

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox

ROOT = pathlib.Path(__file__).resolve().parent.parent
RJM = str(ROOT / "reference" / "sysex_dumps" / "RJM.syx")

from conftest import requires_rjm
pytestmark = requires_rjm


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    from lfeditor.ui.app import MainWindow
    w = MainWindow()
    w.load(RJM)
    return w


# ---- icons build ----

def test_toolbar_icons_build(qapp):
    from lfeditor.ui.icons import icon, _BUILDERS
    for name in ("open", "save", "backup", "clear", "copy", "paste"):
        assert name in _BUILDERS
        ic = icon(name)
        assert not ic.isNull()
        assert not ic.pixmap(40, 40).isNull()


# ---- the rail selection bug fix: editing must NOT jump the selection ----

def test_edit_keeps_rail_selection(win):
    presets = win.tab_widgets[0]
    presets.rail.list.setCurrentRow(4)            # preset 5
    assert presets.current_record().number == 5
    presets._on_edit()                            # what every field edit triggers
    assert presets.rail.list.currentRow() == 4
    assert presets.current_record().number == 5   # stayed put, not bounced to record 1


# ---- copy / paste whole record ----

def test_copy_paste_whole_preset(win):
    presets = win.tab_widgets[0]
    win.tabs.setCurrentIndex(0)
    presets.rail.list.setCurrentRow(0)
    src_vals = list(presets.current_record().values)
    src_name = presets.current_record().name
    win.copy_record()
    assert win._record_clip is not None and win.act_paste.isEnabled()

    presets.rail.list.setCurrentRow(4)
    assert presets.current_record().name != src_name  # different record to start
    win.paste_record()
    tgt = presets.current_record()
    assert tgt.number == 5                # slot/number preserved
    assert tgt.values == src_vals         # content fully overwritten
    assert tgt.name == src_name


def test_paste_round_trips_byte_exact(win):
    presets = win.tab_widgets[0]
    presets.rail.list.setCurrentRow(0); win.copy_record()
    presets.rail.list.setCurrentRow(7); win.paste_record()
    with tempfile.NamedTemporaryFile(suffix=".syx", delete=False) as tf:
        tmp = tf.name
    try:
        win.dump.to_file(tmp)
        from lfeditor.codec import Dump
        assert Dump.from_file(tmp).to_bytes() == pathlib.Path(tmp).read_bytes()
    finally:
        os.unlink(tmp)


def test_paste_rejects_wrong_type(win):
    # copy a preset, switch to the Songs tab, paste must be refused (no mutation)
    presets = win.tab_widgets[0]
    presets.rail.list.setCurrentRow(0); win.copy_record()
    songs = next(t for t in win.tab_widgets if t.__class__.__name__ == "SectionedTab"
                 and getattr(t, "type_", None) == 2)
    win.tabs.setCurrentWidget(songs)
    songs.rail.list.setCurrentRow(0)
    before = songs.current_record().values[:]
    win.paste_record()
    assert songs.current_record().values == before  # unchanged — wrong type rejected


# ---- clear resets to default ----

def test_clear_resets_preset_to_default(win):
    presets = win.tab_widgets[0]
    win.tabs.setCurrentIndex(0)
    presets.rail.list.setCurrentRow(4)            # preset 5
    win.clear_record()
    rec = presets.current_record()
    assert rec.number == 5
    assert rec.name == "Preset #005"
    assert rec.nick == "Pre #005"
    assert rec.values[158] == 1                   # IA-Slot Map defaults to 1
    assert all(v == 0 for v in rec.values[76:140])  # command table emptied


def test_clear_blanks_linked_labels(win):
    # plant an IA-Slot Defined Label (ext9) on preset 1, clear, confirm it's blanked
    presets = win.tab_widgets[0]
    win.tabs.setCurrentIndex(0)
    presets.rail.list.setCurrentRow(0)
    ext9 = [r for r in win.dump.records(9)
            if r.frame.rec_num == presets.current_record().frame.rec_num][0]
    ext9.set_label(0, "KEEPME")
    assert ext9.label(0) == "KEEPME"
    win.clear_record()
    ext9b = [r for r in win.dump.records(9)
             if r.frame.rec_num == presets.current_record().frame.rec_num][0]
    assert not any(ext9b.labels())
