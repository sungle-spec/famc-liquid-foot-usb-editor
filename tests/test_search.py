"""Find / Q-LIST search engine + dialog wiring."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib

import pytest

from lfeditor.codec import Dump
from lfeditor import search

ROOT = pathlib.Path(__file__).resolve().parent.parent
RJM = str(ROOT / "reference" / "sysex_dumps" / "RJM.syx")

from conftest import requires_rjm
pytestmark = requires_rjm


@pytest.fixture(scope="module")
def dump():
    return Dump.from_file(RJM)


# ---- engine ----

def test_text_substring(dump):
    m = search.search(dump, text="MOTP")
    assert m and all("motp" in r.name.lower() for r in m)
    assert all(r.where == "name" for r in m)


def test_text_wildcard(dump):
    star = search.search(dump, text="MOTP*")
    assert {r.name for r in star} >= {"MOTP 1", "MOTP 2"}
    # a pattern that matches nothing
    assert search.search(dump, text="zzz_nope_*") == []


def test_type_and_range_filter(dump):
    m = search.search(dump, types={1}, num_min=1, num_max=5)
    assert [r.number for r in m] == [1, 2, 3, 4, 5]
    assert all(r.type_ == 1 for r in m)


def test_command_search_channel_and_type(dump):
    m = search.search(dump, types={1}, channel=2, msgtype=0xC)
    assert m, "expected some PC-on-ch2 commands in RJM presets"
    for r in m:
        assert r.type_ == 1 and r.detail.startswith("PC ch2")


def test_command_search_cc_number(dump):
    m = search.search(dump, msgtype=0xB, number=19)
    assert m and all("#19" in r.detail for r in m)


def test_text_and_command_are_anded(dump):
    # a name that exists but (almost certainly) has no PC on channel 16
    only_text = search.search(dump, text="MOTP 1")
    combo = search.search(dump, text="MOTP 1", channel=16, msgtype=0xC)
    assert only_text and len(combo) <= len(only_text)


def test_first_only_collapses_rows(dump):
    many = search.search(dump, types={1}, channel=2, msgtype=0xC)
    once = search.search(dump, types={1}, channel=2, msgtype=0xC, first_only=True)
    # one row per record when collapsed
    assert len(once) == len({(r.type_, r.number) for r in many})
    assert len(once) <= len(many)


def test_results_csv_shape(dump):
    m = search.search(dump, types={1}, num_min=1, num_max=3)
    lines = search.results_csv(m).splitlines()
    assert lines[0] == '"Type","#","Name","Where","Data"'
    assert len(lines) == len(m) + 1


# ---- dialog + reveal wiring ----

@pytest.fixture(scope="session")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_find_dialog_search_and_reveal(qapp):
    from lfeditor.ui.app import MainWindow
    w = MainWindow()
    w.load(RJM)
    w.open_find()
    fd = w._find_dialog
    fd.text.setText("MOTP*")
    fd.run_search()
    assert fd.table.rowCount() >= 2
    # double-clicking a row reveals that record in the right tab
    m0 = fd._matches[0]
    fd._jump(0, 0)
    assert w.tabs.tabText(w.tabs.currentIndex()) == "Presets"
    assert w.tab_widgets[0].current_record().number == m0.number


def test_reveal_each_type(qapp):
    from lfeditor.ui.app import MainWindow
    w = MainWindow()
    w.load(RJM)
    for type_, tabname in MainWindow.TYPE_TO_TAB.items():
        recs = w.dump.records(type_)
        if not recs:
            continue
        target = recs[min(2, len(recs) - 1)].number
        w.reveal(type_, target)
        assert w.tabs.tabText(w.tabs.currentIndex()) == tabname
        cur = w.tabs.currentWidget()
        if hasattr(cur, "current_record") and cur.current_record() is not None:
            assert cur.current_record().number == target
