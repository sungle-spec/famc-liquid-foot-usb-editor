"""Device workers must retain their document and exact outgoing payloads."""
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox


@pytest.fixture
def win(monkeypatch, tmp_path):
    import lfeditor.ui.app as module
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, "QSettings", lambda *a: QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    window = module.MainWindow()
    window.load_factory("Factory_Defaults12.syx", "12")
    window._test_app = app
    return window


def test_busy_document_rejects_replacement_and_edits(win, monkeypatch):
    original = win.dump
    baseline = dict(win._baseline)
    before = win.dump.to_bytes() if hasattr(win.dump, "to_bytes") else [f.to_bytes() for f in win.dump.frames]
    win._set_busy(True, "working")
    try:
        assert not win.tabs.isEnabled()
        assert not win.qlist.isEnabled()
        assert not win.act_clear.isEnabled()
        assert all(not a.isEnabled() for a in win.menuBar().actions())
        # A nonexistent filename also verifies the guard precedes parsing/dialogs.
        win.load("/does/not/exist.syx")
        win.load_factory("Factory_DefaultsPro.syx", "Pro")
        win.paste_record()
        win.clear_record()
        win.clear_labels(9, "labels")
        win.import_records("presets", "Presets")
        win.open_quick_prog()
        win.open_reorder()
        assert win.dump is original
        assert win._baseline == baseline
        after = win.dump.to_bytes() if hasattr(win.dump, "to_bytes") else [f.to_bytes() for f in win.dump.frames]
        assert after == before
    finally:
        win._set_busy(False)
    assert win.tabs.isEnabled()
    assert win.qlist.isEnabled()
    assert win.act_clear.isEnabled()
    assert not win.act_paste.isEnabled()  # retain pre-existing disabled state


@pytest.mark.parametrize("path", ["edits", "all", "record"])
def test_write_dispatch_snapshots_frames_and_baselines_exact_payload(win, monkeypatch, path):
    win.transport = object()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    frame = next(f for f in win.dump.frames if f.type == 1)
    frame.values[0] ^= 1
    expected = frame.to_bytes()
    queued = []
    monkeypatch.setattr(win, "_run_device", lambda fn, ok, *a, **k: queued.append((fn, ok)))
    monkeypatch.setattr(win, "_send_all", lambda frames, emit: (frames, []))
    try:
        if path == "edits":
            win.push_to_device()
        elif path == "all":
            win.push_all_to_device()
        else:
            win.transfer("to", 1, 0)
        assert len(queued) == 1
        # Simulate a mutation after dispatch, before the worker serializes frames.
        frame.values[0] ^= 2
        fn, ok = queued[0]
        result = fn(None)
        sent = next(f for f in result[0] if f.type == 1 and f.rec_num == frame.rec_num)
        assert sent is not frame
        assert sent.to_bytes() == expected
        ok(result)
        assert win._baseline[(frame.type, frame.rec_num)] == expected
        assert frame in win._changed_writable()
    finally:
        win.transport = None


@pytest.mark.parametrize("worker_fails", [False, True])
def test_worker_callback_failure_restores_controls_and_reports_error(win, monkeypatch, worker_fails):
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda _w, title, message: errors.append((title, message)))
    def work():
        if worker_fails:
            raise ValueError("worker failed")
        return 1
    def on_ok(_result):
        assert win._device_busy
        assert not win.tabs.isEnabled()
        raise ValueError("callback failed")
    win._run_device(work, on_ok, "working", "Transfer failed")
    assert win._task.wait(3000)
    win._test_app.processEvents()
    assert errors == [("Transfer failed", "worker failed" if worker_fails else "callback failed")]
    assert not win._device_busy
    assert win.tabs.isEnabled()
    assert win.progress_bar.isHidden()
    assert win.act_connect.isEnabled()
