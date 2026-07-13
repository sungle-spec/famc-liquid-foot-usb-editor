"""Tests for the menu actions: bundled factory defaults + clear-labels (offline, no hardware)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pathlib
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox

from lfeditor.codec import Dump
from lfeditor.resources import FACTORY_DEFAULTS, FACTORY_SPECIAL, factory_path

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


def test_factory_files_bundled_and_decode():
    for _label, fname in FACTORY_DEFAULTS + FACTORY_SPECIAL:
        path = factory_path(fname)
        assert os.path.exists(path), f"missing bundled factory file: {fname}"
        d = Dump.from_file(path)
        assert d.counts().get("Preset", 0) == 384


def test_clear_labels_blanks_extension_records(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Yes))
    # plant a label, then clear
    ext9 = win.dump.records(9)
    ext9[0].set_label(0, "KEEPME")
    assert ext9[0].label(0) == "KEEPME"
    win.clear_labels(9, "Preset Labels")
    assert all(not any(r.labels()) for r in win.dump.records(9))
    assert win._dirty


def test_load_factory_sets_untitled_and_dirty(win, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    win.load_factory("Factory_DefaultsPro.syx", "Pro+")
    assert win.path is None and win._dirty
    assert win.dump.counts()["Preset"] == 384


def test_about_dialog_builds_with_license_and_version(qapp):
    from PySide6.QtWidgets import QTabWidget
    from lfeditor.ui.about_dialog import AboutDialog, version_string, _license_text
    from lfeditor import __version__

    # the license shown must be the real MIT text, and version_string must carry the version
    lic = _license_text()
    assert "MIT License" in lic and "WITHOUT WARRANTY" in lic
    assert __version__ in version_string()

    d = AboutDialog()
    tabs = d.findChild(QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["About", "License", "Legal & Safety"]


def test_app_about_action_opens_dialog(win, monkeypatch):
    # _about must construct and exec the dialog without raising (exec stubbed head-less)
    import lfeditor.ui.about_dialog as ad
    opened = {}
    monkeypatch.setattr(ad.AboutDialog, "exec", lambda self: opened.setdefault("ok", True))
    win._about()
    assert opened.get("ok")


def test_csv_export_import_report_via_menus(win, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    exp = str(tmp_path / "presets.csv")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (exp, "")))
    win.export_records("presets", "Presets")
    assert os.path.exists(exp)

    # edit the CSV and re-import through the window
    import csv
    rows = list(csv.reader(open(exp)))
    rows[3][1] = "MENU IMPORT"
    with open(exp, "w", newline="") as fh:
        csv.writer(fh, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (exp, "")))
    win.import_records("presets", "Presets")
    assert win.dump.records(1)[2].name == "MENU IMPORT" and win._dirty

    rep = str(tmp_path / "report.csv")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (rep, "")))
    win.save_report("songs", "Song")
    assert os.path.exists(rep) and "Assigned" in open(rep).readline()
