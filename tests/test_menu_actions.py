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


@pytest.fixture(autouse=True)
def isolated_qsettings(monkeypatch, tmp_path):
    """Every MainWindow() in this file must use a throwaway settings file, not the real
    per-user QSettings store — otherwise running the suite writes real geometry/recent-files
    into the developer's/CI's actual OS-level preferences."""
    from PySide6.QtCore import QSettings
    import lfeditor.ui.app as app_module
    ini = str(tmp_path / "settings.ini")
    monkeypatch.setattr(app_module, "QSettings", lambda *a, **k: QSettings(ini, QSettings.IniFormat))


@pytest.fixture()
def win(qapp, isolated_qsettings):
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


# ---- quit guard / geometry persistence / recent files / auto-backup ----

def test_close_event_blocked_when_dirty_and_cancelled(win, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    win._dirty = True
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Cancel))
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert not ev.isAccepted()


def test_close_event_proceeds_and_saves_geometry_when_confirmed(win, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    win._dirty = True
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert ev.isAccepted()
    assert win._settings.value("geometry") is not None


def test_close_event_proceeds_without_prompt_when_not_dirty(win):
    from PySide6.QtGui import QCloseEvent
    win._dirty = False
    ev = QCloseEvent()
    win.closeEvent(ev)  # no QMessageBox stub installed — would raise if it tried to show one
    assert ev.isAccepted()


def test_open_file_adds_to_recent_menu(win, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (RJM, "")))
    win.open_file()
    labels = [a.text() for a in win.recent_menu.actions()]
    assert os.path.basename(RJM) in labels


def test_recent_files_prunes_missing_path(win, tmp_path):
    ghost = str(tmp_path / "does_not_exist.syx")
    win._settings.setValue("recentFiles", [ghost])
    win._rebuild_recent_menu()
    labels = [a.text() for a in win.recent_menu.actions()]
    assert os.path.basename(ghost) not in labels
    assert "(no recent files)" in labels


def test_save_file_in_place_creates_backup_copy(win, tmp_path):
    target = tmp_path / "backup_target.syx"
    win.dump.to_file(str(target))
    original = target.read_bytes()
    win.path = str(target)

    backup_dir = tmp_path / "Syx_Backups"
    win._backup_before_overwrite(str(target), backup_dir=str(backup_dir))

    copies = list(backup_dir.glob(f"{target.name}.*.bak"))
    assert len(copies) == 1
    assert copies[0].read_bytes() == original


def test_save_file_calls_backup_before_overwrite(win, tmp_path, monkeypatch):
    target = tmp_path / "save_target.syx"
    win.dump.to_file(str(target))
    win.path = str(target)

    calls = []
    monkeypatch.setattr(win, "_backup_before_overwrite", lambda path, backup_dir=None: calls.append(path))
    win.save_file()
    assert calls == [str(target)]
