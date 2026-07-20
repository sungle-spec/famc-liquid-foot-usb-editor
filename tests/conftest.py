"""Shared pytest fixtures.

Qt keeps a parentless top-level widget (and its whole child tree) alive until it's explicitly
deleted, so across a long suite the windows built by each test accumulate into the hundreds of
thousands of live widgets. Any *global* Qt operation then walks them all and crawls — on a slow CI
runner that pushed individual tests past the timeout. This autouse fixture tears down leaked
top-level widgets after every test, keeping each test's Qt work proportional to what it created.
"""
import os
import pathlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

# The 384-preset reference-rig dump is a private fixture (not redistributed). Tests that
# verify against it skip cleanly in public checkouts — same pattern as the round-trip
# corpus skip in test_roundtrip.py.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RJM_PATH = REPO_ROOT / "reference" / "sysex_dumps" / "RJM.syx"
requires_rjm = pytest.mark.skipif(
    not RJM_PATH.exists(),
    reason="private reference-rig dump not present in this checkout",
)

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # noqa: BLE001 — non-Qt test runs still work without PySide6
    QApplication = None


@pytest.fixture(autouse=True)
def _destroy_leaked_widgets():
    yield
    if QApplication is None:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in list(app.topLevelWidgets()):
        # Forced test-cleanup close, not a real user quit — never let it block on the
        # unsaved-changes confirm dialog MainWindow.closeEvent() shows for a dirty document.
        if hasattr(w, "_dirty"):
            w._dirty = False
        w.close()
        w.deleteLater()
    app.processEvents()   # run the deferred-delete queue so the widgets are actually freed
