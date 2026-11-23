"""The Q-LIST must show a rename immediately (tester report: Name edited on the Pages tab, Q-LIST kept
the old name even after Edit > Refresh Names)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from lfeditor.ui.components import NAME_LEN


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_qsettings(monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    import lfeditor.ui.app as app_module
    ini = str(tmp_path / "settings.ini")
    monkeypatch.setattr(app_module, "QSettings", lambda *a, **k: QSettings(ini, QSettings.IniFormat))


@pytest.fixture()
def win(qapp, isolated_qsettings):
    from lfeditor.ui.app import MainWindow, TAB_ORDER
    w = MainWindow()
    w.load_factory("Factory_DefaultsPro.syx", "Pro+")
    w._tab = lambda title: w.tab_widgets[TAB_ORDER.index(title)]
    w._go = lambda title: w.tabs.setCurrentIndex(TAB_ORDER.index(title))
    return w


def _texts(win):
    return [win.qlist.list.item(i).text() for i in range(win.qlist.list.count())]


def _rename_via_header(tab, idx, text):
    tab._goto(idx)
    tab.header.name.setText(text)
    tab.header._write_name(0, NAME_LEN, tab.header.name)


@pytest.mark.parametrize("title", ["IA-Slot", "Pages", "Presets", "Songs"])
def test_renaming_a_record_updates_the_qlist_at_once_in_every_mode(win, title):
    tab = win._tab(title)
    win._go(title)
    for mode in ("original", "auto", "manual"):          # independent of the Name-updates setting
        win.set_name_sync_mode(mode)
        new = f"Z{title[:4]}{mode[:4]}"        # fits the 16-char name field
        _rename_via_header(tab, 2, new)
        assert any(t.endswith(new) for t in _texts(win)), (title, mode)


def test_qlist_keeps_selection_and_scroll_when_it_refreshes(win):
    win._go("IA-Slot")
    tab = win._tab("IA-Slot")
    lst = win.qlist.list
    lst.setCurrentRow(40)
    lst.verticalScrollBar().setValue(lst.verticalScrollBar().maximum() // 2)
    before_scroll = lst.verticalScrollBar().value()
    _rename_via_header(tab, 10, "RENAMED")
    assert lst.currentRow() == 40
    assert lst.verticalScrollBar().value() == before_scroll
    assert lst.item(10).text().endswith("RENAMED")


def test_refresh_does_not_jump_to_the_highlighted_record(win):
    win._go("IA-Slot")
    win.qlist.list.setCurrentRow(5)
    jumps = []
    win.qlist._on_select = lambda t, n: jumps.append((t, n))
    win.qlist.refresh()
    assert jumps == []


def test_edits_that_do_not_rename_do_not_redraw_the_list(win):
    win._go("IA-Slot")
    first = win.qlist.list.item(0)
    win.mark_dirty()                                     # e.g. a toggle changed, no name did
    assert win.qlist.list.item(0) is first               # same widget item: not rebuilt
    assert win.qlist.refresh_if_changed() is False


def test_refresh_names_menu_action_also_refreshes_the_qlist(win):
    win._go("IA-Slot")
    win.dump.records(3)[7].values[0:16] = [ord(c) for c in "VIA DUMP".ljust(16)]   # no edit signal fired
    assert not any(t.endswith("VIA DUMP") for t in _texts(win))
    win._manual_refresh_names()
    assert any(t.endswith("VIA DUMP") for t in _texts(win))
