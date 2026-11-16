"""Command Programming tables: the original editor's full function names, and hover help for each
function — on every entry of the open list and on the row's selected function."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from lfeditor.model.cmd_help import func_help
from lfeditor.model.preset import CMD_FUNCS


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
    return w


def _cmd_fields(tab):
    return [f for f in tab._all_fields if hasattr(f, "funcs_c")]


@pytest.mark.parametrize("title,tables", [("Presets", 1), ("IA-Slot", 2), ("Songs", 1)])
def test_every_command_table_loads_and_offers_the_full_labels(win, title, tables):
    fields = _cmd_fields(win._tab(title))
    assert len(fields) == tables
    for f in fields:
        fc = f.funcs_c[0]
        texts = [fc.itemText(i) for i in range(fc.count())]
        assert "Page Button Display Start" in texts and "Set Status#1 LED CLR" in texts
        assert "Page Button Display" not in texts


def test_function_list_entries_and_selected_row_have_hover_help(win):
    tab = win._tab("IA-Slot")
    f = _cmd_fields(tab)[0]
    fc = f.funcs_c[0]
    i48 = fc.findData(48)
    assert "start index" in fc.itemData(i48, Qt.ToolTipRole)
    fc.setCurrentIndex(i48)                       # the user picks the function on row 1
    assert tab._rec.values[f.start] == 48
    assert fc.toolTip().startswith("Page Button Display Start — ")
    assert "not an on/off switch" in fc.toolTip()
    fc.setCurrentIndex(fc.findData(17))           # a function with no help text: no stale tip
    assert fc.toolTip() == "" and func_help(17) == ""


def test_schema_carries_function_help_for_the_web_editor():
    from lfeditor.schema import schema_json
    import json
    blob = json.loads(schema_json())

    def walk(o):
        if isinstance(o, dict):
            if "funcs" in o:
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)

    tables = list(walk(blob))
    assert tables
    for t in tables:
        assert t["funcs"]["48"] == CMD_FUNCS[48] == "Page Button Display Start"
        assert "start index" in t["func_help"]["48"]
        assert set(t["func_help"]) <= set(t["funcs"])
