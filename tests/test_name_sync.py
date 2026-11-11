"""IA-Slot / Page rename propagation: Original (default) / Automatic / Manual (lfeditor/name_sync.py)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from lfeditor import name_sync

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication


# ---- pure helpers -----------------------------------------------------------------------------
def test_default_is_original_and_unknown_values_fall_back():
    assert name_sync.DEFAULT_MODE == name_sync.MODE_ORIGINAL
    assert name_sync.normalize_mode(None) == "original"
    assert name_sync.normalize_mode("bogus") == "original"
    assert [name_sync.normalize_mode(m) for m in name_sync.MODES] == list(name_sync.MODES)


# ---- window behaviour -------------------------------------------------------------------------
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
    from lfeditor.ui.app import MainWindow
    w = MainWindow()
    w.load_factory("Factory_DefaultsPro.syx", "Pro+")
    return w


from lfeditor.ui.app import TAB_ORDER


def _tab(win, title):
    return win.tab_widgets[TAB_ORDER.index(title)]


def _ia_map_combo_texts(win, slot=0):
    tab = _tab(win, "IA-Maps")
    pick = next(f for f in tab._all_fields if hasattr(f, "combos"))
    return pick, pick.combos[slot]


def _rename_ia(win, n, text):
    """Rename IA-Slot record n (0-based) through the real header edit path."""
    tab = _tab(win, "IA-Slot")
    tab._show(n)
    tab.header.name.setText(text)
    from lfeditor.ui.components import NAME_LEN
    tab.header._write_name(0, NAME_LEN, tab.header.name)


def _slot_label(win, n):
    pick, cb = _ia_map_combo_texts(win)
    return cb.itemText(n)


def test_default_mode_is_original_and_menu_reflects_it(win):
    assert win.name_sync_mode() == "original"
    assert win._name_mode_actions["original"].isChecked()
    assert not win._name_mode_actions["auto"].isChecked()


def test_original_mode_does_not_propagate_until_reload(win):
    before = _slot_label(win, 0)
    _rename_ia(win, 0, "ZZ TEST")
    win._name_timer.timeout.emit()          # even if something poked the timer
    assert _slot_label(win, 0) == before    # unchanged — the original behaviour
    assert not win._name_timer.isActive()


def test_manual_refresh_works_in_every_mode_and_keeps_selection(win):
    pick, cb = _ia_map_combo_texts(win)
    sel_before = cb.currentIndex()
    _rename_ia(win, 0, "ZZ TEST")
    assert "ZZ TEST" not in _slot_label(win, 0)
    win._manual_refresh_names()
    assert "ZZ TEST" in _slot_label(win, 0)
    _pick, cb2 = _ia_map_combo_texts(win)
    # the IA-Map record shown on the IA-Maps tab keeps its selected slot after the rebuild
    tab = _tab(win, "IA-Maps")
    if tab._rec is not None:
        expect = tab._rec.values[pick.start]
        assert cb2.currentIndex() == next(p for p, (i, _t) in enumerate(pick._items) if i == expect)


def test_manual_mode_only_refreshes_on_button(win):
    win.set_name_sync_mode("manual")
    _rename_ia(win, 0, "ZZ TEST")
    win._name_timer.timeout.emit()
    win._on_tab_changed_names()
    assert "ZZ TEST" not in _slot_label(win, 0)
    win._manual_refresh_names()
    assert "ZZ TEST" in _slot_label(win, 0)


def test_auto_mode_starts_debounce_and_refreshes(win):
    win.set_name_sync_mode("auto")
    _rename_ia(win, 0, "ZZ TEST")
    assert win._name_timer.isActive()
    assert "ZZ TEST" not in _slot_label(win, 0)   # not yet — debounced
    win._name_timer.timeout.emit()                # quiet period elapsed
    assert "ZZ TEST" in _slot_label(win, 0)


def test_auto_mode_refreshes_on_tab_switch_and_updates_other_consumers(win):
    win.set_name_sync_mode("auto")
    _rename_ia(win, 4, "ZZ TEST")
    win.tabs.setCurrentIndex(TAB_ORDER.index("Pages"))   # switching tabs flushes immediately
    assert not win._name_timer.isActive()
    assert "ZZ TEST" in _slot_label(win, 4)
    assert _tab(win, "Pages")._ia[4] == "ZZ TEST"
    presets = _tab(win, "Presets")
    grid = next(f for f in presets._all_fields if hasattr(f, "_items") and hasattr(f, "_toggles"))
    assert "ZZ TEST" in grid._items[4].text()


def test_switching_mode_to_auto_catches_up_on_pending_edits(win):
    _rename_ia(win, 0, "ZZ TEST")          # made in Original mode: not propagated
    assert "ZZ TEST" not in _slot_label(win, 0)
    win.set_name_sync_mode("auto")
    assert "ZZ TEST" in _slot_label(win, 0)


def test_pages_tab_names_and_selected_function_survive_refresh(win):
    pages = _tab(win, "Pages")
    # find a button whose Function 1 is an IA Slot so we can watch its dropdown text
    rec = pages._rec
    from lfeditor.model.page import FUNC1_OFF
    btn = next((b for b in range(pages._records[0].values.__len__())
                if 128 <= rec.values[FUNC1_OFF + b] <= 187), None)
    if btn is None:
        pytest.skip("factory page has no IA-Slot button")
    ia_no = rec.values[FUNC1_OFF + btn] - 127
    pages._select(btn)
    _rename_ia(win, ia_no - 1, "ZZ TEST")
    win._manual_refresh_names()
    pages._select(btn)
    vc = pages.f_values[0]
    assert "ZZ TEST" in vc.currentText()
    assert vc.currentData() == ia_no
    assert rec.values[FUNC1_OFF + btn] == 127 + ia_no     # bytes untouched by the refresh


def test_setting_persists_across_windows(win):
    win.set_name_sync_mode("manual")
    from lfeditor.ui.app import MainWindow
    assert MainWindow().name_sync_mode() == "manual"


def test_refresh_without_a_file_is_a_noop(qapp, isolated_qsettings):
    from lfeditor.ui.app import MainWindow
    w = MainWindow()
    assert w.refresh_record_names() is False
    w._manual_refresh_names()   # must not raise
