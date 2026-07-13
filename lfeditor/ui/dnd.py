"""
Drag-and-drop glue: dragging a record reference (from the Find / Q-LIST results) onto a slot
picker or a command-table row. The payload is just "type:number" under a private MIME type, so
nothing leaks into the OS clipboard.
"""
from __future__ import annotations

from PySide6.QtCore import QMimeData

MIME = "application/x-lf-record"


def encode(type_: int, number: int) -> QMimeData:
    md = QMimeData()
    md.setData(MIME, f"{type_}:{number}".encode("ascii"))
    return md


def decode(md: QMimeData):
    """Return (type_, number) from a drag payload, or None if it isn't a record reference."""
    if not md.hasFormat(MIME):
        return None
    try:
        t, n = bytes(md.data(MIME)).decode("ascii").split(":")
        return int(t), int(n)
    except (ValueError, UnicodeDecodeError):
        return None


class RecordDropTarget:
    """Mixin for a QWidget that accepts a dragged record reference. It centralises the
    accept-or-defer drag/drop boilerplate; subclasses only say *which* references they accept
    (`_accepts`) and *what to do* with one (`_handle_drop`). `_ref(event)` returns the decoded
    (type, number) when acceptable (else None) and is handy to unit-test the gating directly."""

    def _ref(self, event):
        d = decode(event.mimeData())
        return d if (d and self._accepts(d[0], d[1])) else None

    def dragEnterEvent(self, e):
        if self._ref(e):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self._ref(e):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        ref = self._ref(e)
        if ref is None:
            return super().dropEvent(e)
        self._handle_drop(ref[0], ref[1], e)
        e.acceptProposedAction()

    # --- subclass hooks ---
    def _accepts(self, type_: int, number: int) -> bool:
        raise NotImplementedError

    def _handle_drop(self, type_: int, number: int, event) -> None:
        raise NotImplementedError
