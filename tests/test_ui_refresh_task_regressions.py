"""Selection and worker lifecycle regressions; no device access."""
import threading
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QSettings
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from lfeditor.ui.fields import SlotPickerField


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("width,unused,stored", [(1, None, 2), (2, 65535, 2), (2, 65535, 65535)])
def test_slot_context_refresh_preserves_bound_value(qapp, width, unused, stored):
    field = SlotPickerField(0, 1, "Slots", 1, width=width, unused_raw=unused)
    field.build()
    records = [SimpleNamespace(name=f"Name {i}") for i in range(4)]
    dump = SimpleNamespace(records=lambda _t: records)
    field.set_context(dump)
    values = [stored & 255] + ([stored >> 8] if width == 2 else [])
    field.load(values)
    changes = []
    field.set_on_change(lambda: changes.append(True))
    records[2].name = "Renamed"
    field.set_context(dump)
    selected = field._items[field.combos[0].currentIndex()][0]
    assert selected == (None if stored == unused else stored)
    assert values == [stored & 255] + ([stored >> 8] if width == 2 else [])
    assert not changes
    assert "Renamed" in field.combos[0].itemText(3 if unused is not None else 2)


def test_active_worker_rejects_second_task_disconnect_and_close(qapp, monkeypatch, tmp_path):
    import lfeditor.ui.app as module
    monkeypatch.setattr(module, "QSettings", lambda *a: QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    win = module.MainWindow()
    release = threading.Event()
    entered = threading.Event()
    results = []

    def work():
        entered.set()
        release.wait(5)
        return "first"

    win._run_device(work, results.append, "working", "failed")
    task = win._task
    try:
        assert entered.wait(2)
        win._run_device(lambda: "second", results.append, "second", "failed")
        assert win._task is task
        assert win._device_busy
        # A sentinel transport would fail if disconnect touched it.
        sentinel = object()
        win.transport = sentinel
        win.disconnect_device()
        assert win.transport is sentinel
        event = QCloseEvent()
        win.closeEvent(event)
        assert not event.isAccepted()
    finally:
        win.transport = None
        release.set()
        assert task.wait(3000)
        qapp.processEvents()
    assert results == ["first"]
    assert not win._device_busy
