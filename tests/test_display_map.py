"""Pages tab: "IA Map to use for display" — a Page button's IA Slot choice N is position N of the
IA-Map live when the page runs, so the 60 choices are labelled through a chosen map (display-only;
the original editor has a dropdown of the same name that writes no bytes)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from lfeditor import name_sync as ns
from lfeditor.model.iamap import MAP_OFF
from lfeditor.model.page import FORCE_IA_MAP_OFF, FUNC1_OFF
from lfeditor.resources import factory_path, FACTORY_DEFAULTS
from lfeditor.text import encode_ascii


def _dump():
    from lfeditor.codec import Dump
    return Dump.from_file(factory_path(FACTORY_DEFAULTS[0][1]))


def _name_slot(d, n, text):
    d.records(3)[n].values[0:16] = encode_ascii(text, 16)


# ---- pure resolver ----
def test_default_map_is_identity_so_old_labels_are_unchanged():
    d = _dump()
    assert ns.display_names(d, ns.DISPLAY_MAP_AUTO, 0) == ns.ia_names(d)[:60]
    assert ns.display_names(d, ns.DISPLAY_MAP_NONE, 0) == ns.ia_names(d)[:60]


def test_a_remapped_position_shows_the_slot_that_map_assigns():
    d = _dump()
    _name_slot(d, 4, "FUZZ")
    m = d.records(8)[1]
    m.values[MAP_OFF + 0] = 4                          # map 2: position 1 -> IA-Slot 5
    labels = ns.display_names(d, 1, 0)                 # choose map 2 explicitly
    assert labels[0] == "FUZZ" and labels[1] == ns.ia_names(d)[1]
    assert ns.display_names(d, ns.DISPLAY_MAP_NONE, 0)[0] == ns.ia_names(d)[0]   # no map: unchanged


def test_auto_follows_the_pages_force_ia_map_else_map_one():
    d = _dump()
    n = len(d.records(8))
    assert ns.display_map_index(ns.DISPLAY_MAP_AUTO, 0, n) == 0           # no force -> Map 1
    assert ns.display_map_index(ns.DISPLAY_MAP_AUTO, 2, n) == 1           # force map 2 -> record 1
    assert ns.display_map_index(ns.DISPLAY_MAP_AUTO, 99, n) == 0          # out of range -> Map 1
    assert ns.display_map_index(ns.DISPLAY_MAP_NONE, 2, n) is None
    assert ns.display_map_index(5, 0, n) == 5 and ns.display_map_index(999, 0, n) == 0
    assert ns.display_map_index(ns.DISPLAY_MAP_AUTO, 0, 0) is None        # no maps in the file


def test_unassigned_or_out_of_range_cells_are_blank_not_a_crash():
    assert ns.labels_for_map(["A", "B"], [0, 1, 7, 1]) [:4] == ["A", "B", "", "B"]
    assert len(ns.labels_for_map(["A"], [0])) == 60


def test_picker_options_list_auto_none_and_every_map():
    d = _dump()
    opts = ns.display_map_options(d)
    assert [c for c, _ in opts[:2]] == [ns.DISPLAY_MAP_AUTO, ns.DISPLAY_MAP_NONE]
    assert len(opts) == 2 + len(d.records(8))
    assert opts[2][1].startswith("Map 001")


# ---- web API ----
def test_web_session_exposes_the_same_labels():
    from lfeditor.webapi import Session
    s = Session()
    s.load(open(factory_path(FACTORY_DEFAULTS[0][1]), "rb").read())
    s.set_str(3, 4, 0, 16, "FUZZ")
    s.set(8, 1, MAP_OFF, 4)
    assert s.display_names("1", 0)[0] == "FUZZ"
    assert s.display_names("auto", 2)[0] == "FUZZ"        # force map 2 -> map record 1
    assert s.display_names("none", 0)[0] == s.raw_names(3)[0]
    assert s.display_names("garbage", 0) == s.display_names("auto", 0)
    opts = s.display_map_options()
    assert opts[0][0] == "auto" and opts[1][0] == "none" and opts[2][0] == "0"


# ---- desktop Pages tab ----
@pytest.fixture(scope="session")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_qsettings(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QSettings
    import lfeditor.ui.app as app_module
    ini = str(tmp_path / "settings.ini")
    monkeypatch.setattr(app_module, "QSettings", lambda *a, **k: QSettings(ini, QSettings.IniFormat))


@pytest.fixture()
def win(qapp, isolated_qsettings):
    from lfeditor.ui.app import MainWindow, TAB_ORDER
    w = MainWindow()
    w.load_factory("Factory_DefaultsPro.syx", "Pro+")
    w.pages = w.tab_widgets[TAB_ORDER.index("Pages")]
    return w


def _ia_choice_texts(pages, fi=0):
    """Open button's Function-fi value list after switching it to 'IA Slot'."""
    tc = pages.f_types[fi]
    tc.setCurrentIndex(tc.findData("ia"))
    vc = pages.f_values[fi]
    return [vc.itemText(i) for i in range(vc.count())]


def test_desktop_picker_relabels_the_ia_slot_list_without_touching_bytes(win):
    pages = win.pages
    d = win.dump
    _name_slot(d, 4, "FUZZ")
    d.records(8)[1].values[MAP_OFF + 0] = 4
    win.refresh_record_names()
    cb = pages.display_map_combo
    assert cb.count() == 2 + len(d.records(8))
    before = list(pages._rec.values)
    cb.setCurrentIndex(cb.findData(1))                  # Map 002
    assert _ia_choice_texts(pages)[0] == "(001) FUZZ"
    cb.setCurrentIndex(cb.findData(ns.DISPLAY_MAP_NONE))
    assert _ia_choice_texts(pages)[0] != "(001) FUZZ"
    # nothing was written by the picker (the IA Slot type switch above only changed the editor's
    # own selection, which re-writes the function byte — compare everything else)
    after = list(pages._rec.values)
    assert [i for i, (a, b) in enumerate(zip(before, after)) if a != b][:1] in ([], [FUNC1_OFF + pages._sel])


def test_desktop_auto_follows_force_ia_map_and_a_map_edit_shows_on_return(win):
    pages = win.pages
    d = win.dump
    _name_slot(d, 4, "FUZZ")
    d.records(8)[1].values[MAP_OFF + 0] = 4
    pages._rec.values[FORCE_IA_MAP_OFF] = 2             # this page forces Map 2
    pages._apply_display_map()
    assert pages._ia[0] == "FUZZ"
    pages._rec.values[FORCE_IA_MAP_OFF] = 0             # back to Map 1 (identity)
    pages._apply_display_map()
    assert pages._ia[0] == ns.ia_names(d)[0]
    d.records(8)[0].values[MAP_OFF + 0] = 4             # edit Map 1 on the IA-Maps tab
    pages._apply_display_map()                          # what showEvent does on returning to Pages
    assert pages._ia[0] == "FUZZ"


def test_choice_survives_a_name_refresh_and_resets_if_the_map_vanishes(win):
    pages = win.pages
    cb = pages.display_map_combo
    cb.setCurrentIndex(cb.findData(3))
    win.refresh_record_names()
    assert cb.currentData() == 3
    pages._display_choice = 9999                        # a map that does not exist
    pages._populate_display_map_combo()
    assert cb.currentData() == ns.DISPLAY_MAP_AUTO


def test_stored_bytes_unchanged_by_picking_a_map(win):
    pages = win.pages
    snap = [list(r.values) for r in win.dump.records(7)]
    cb = pages.display_map_combo
    for i in range(min(cb.count(), 6)):
        cb.setCurrentIndex(i)
    assert [list(r.values) for r in win.dump.records(7)] == snap
