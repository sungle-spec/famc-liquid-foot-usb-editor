"""Shared themed widgets that reproduce the LF+ Editor v6.31 building blocks.

These are composed by the per-tab layouts (ui/tabs/). They keep the existing binding model:
edits write straight into a record's decoded `values` list, so re-encoding stays lossless.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QGroupBox,
    QGridLayout, QSizePolicy,
)

from .theme import GREEN, RED, PANEL_LIGHT, TEXT_DIM, BORDER
from ..text import decode_ascii, encode_ascii

NAME_LEN, NICK_OFF, NICK_LEN = 16, 16, 8


def section(title: str, body: QWidget, note: str = "") -> QGroupBox:
    """A titled section panel (the original's bordered, captioned boxes)."""
    box = QGroupBox(title)
    box.setObjectName("section")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(8, 6, 8, 8)
    lay.setSpacing(5)
    if note:
        lab = QLabel(note)
        lab.setObjectName("sectionNote")
        lab.setWordWrap(True)
        lay.addWidget(lab)
    lay.addWidget(body)
    return box


class ToggleSwitch(QPushButton):
    """A red/green rocker-style toggle, mirroring the original's LED switches.

    Bound to one bit (`mask`) of `values[offset]`. Red = off, green = on (matching the
    editor, whose rockers glow). Emits `changed()` when toggled by the user."""

    changed = Signal()

    def __init__(self, offset: int, mask: int, label: str = "", invert: bool = False):
        super().__init__()
        self.offset, self.mask, self.invert = offset, mask, invert
        self.setCheckable(True)
        self.setFixedSize(34, 20)
        self.setCursor(Qt.PointingHandCursor)
        # no name-as-tooltip: the curated hover help (set by the tab) should win, and where there
        # is none the control stays blank — matching the original (which shows nothing there).
        self._values: list[int] | None = None
        self.toggled.connect(self._on_toggle)

    def bind(self, values: list[int]):
        self._values = values
        on = bool(values[self.offset] & self.mask)
        if self.invert:
            on = not on
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self.update()

    def _on_toggle(self, checked: bool):
        if self._values is None:
            return
        bit_on = (not checked) if self.invert else checked
        cur = self._values[self.offset]
        new = (cur | self.mask) if bit_on else (cur & ~self.mask & 0xFF)
        if new != cur:
            self._values[self.offset] = new
            self.changed.emit()
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        track = QColor(GREEN if on else RED)
        track.setAlpha(80)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 9, 9)
        knob = QColor(GREEN if on else RED)
        x = self.width() - 17 if on else 3
        p.setBrush(knob)
        p.drawEllipse(x, 3, 14, 14)
        p.end()


class RockerSwitch(QPushButton):
    """A vertical red/green rocker switch, faithful to the original's hardware-style toggles
    (red body + white "I"/"O" markings when off, green-lit when on). Same binding model as
    ToggleSwitch — one bit (`mask`) of `values[offset]`."""

    changed = Signal()

    def __init__(self, offset: int, mask: int, label: str = "", invert: bool = False):
        super().__init__()
        self.offset, self.mask, self.invert = offset, mask, invert
        self.setCheckable(True)
        self.setFixedSize(22, 30)
        self.setCursor(Qt.PointingHandCursor)
        # no name-as-tooltip: the curated hover help (set by the tab) should win, and where there
        # is none the control stays blank — matching the original (which shows nothing there).
        self._values: list[int] | None = None
        self.toggled.connect(self._on_toggle)

    def bind(self, values: list[int]):
        self._values = values
        on = bool(values[self.offset] & self.mask)
        if self.invert:
            on = not on
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self.update()

    def _on_toggle(self, checked: bool):
        if self._values is None:
            return
        bit_on = (not checked) if self.invert else checked
        cur = self._values[self.offset]
        new = (cur | self.mask) if bit_on else (cur & ~self.mask & 0xFF)
        if new != cur:
            self._values[self.offset] = new
            self.changed.emit()
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        body = QColor(GREEN if on else RED)
        edge = QColor(body).darker(160)
        r = self.rect().adjusted(2, 1, -2, -1)
        p.setPen(edge)
        p.setBrush(body)
        p.drawRoundedRect(r, 3, 3)
        # the lit half (top = "I"/on when active, bottom = "O" when off) sits proud
        hi = QColor(255, 255, 255, 70)
        half = r.adjusted(1, 1, -1, -r.height() // 2)
        if not on:
            half = r.adjusted(1, r.height() // 2, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(hi)
        p.drawRoundedRect(half, 2, 2)
        # I / O glyphs
        p.setPen(QColor("white"))
        f = QFont(self.font()); f.setPointSize(8); f.setBold(True); p.setFont(f)
        p.drawText(r.adjusted(0, 1, 0, -r.height() // 2), Qt.AlignCenter, "I")
        p.drawText(r.adjusted(0, r.height() // 2, 0, -1), Qt.AlignCenter, "O")
        p.end()


class LabeledToggle(QWidget):
    """A ToggleSwitch with a caption to its right (the common row in the original)."""

    changed = Signal()

    def __init__(self, offset: int, mask: int, label: str, invert: bool = False):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        self.toggle = RockerSwitch(offset, mask, label, invert)
        self.toggle.changed.connect(self.changed)
        lay.addWidget(self.toggle, 0, Qt.AlignVCenter)
        cap = QLabel(label)
        cap.setWordWrap(True)
        lay.addWidget(cap, 1)

    def bind(self, values):
        self.toggle.bind(values)


class RecordHeader(QWidget):
    """The per-record header strip: record spinner + prev/next, Full Name + Nick LCD fields,
    and the four transfer buttons. Emits `record_changed(index)` and `edited()`; the transfer
    buttons emit `transfer(kind)` with kind in {to, from, all_to, all_from}."""

    record_changed = Signal(int)
    edited = Signal()
    transfer = Signal(str)

    def __init__(self, title: str, has_name: bool = True):
        super().__init__()
        self.has_name = has_name
        self._values: list[int] | None = None
        self._count = 0
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(8)

        ttl = QLabel(title)
        ttl.setObjectName("tabTitle")
        lay.addWidget(ttl)

        self.spin = QSpinBox()
        self.spin.setMinimum(1)
        self.spin.setMaximum(1)
        self.spin.setFixedWidth(72)
        self.spin.valueChanged.connect(lambda v: self.record_changed.emit(v - 1))
        lay.addWidget(self.spin)

        if has_name:
            self.name = QLineEdit()
            self.name.setObjectName("lcd")
            self.name.setMaxLength(NAME_LEN)
            self.name.setFixedWidth(180)
            self.name.editingFinished.connect(lambda: self._write_name(0, NAME_LEN, self.name))
            lay.addWidget(QLabel("Name"))
            lay.addWidget(self.name)

            self.nick = QLineEdit()
            self.nick.setObjectName("lcd")
            self.nick.setMaxLength(NICK_LEN)
            self.nick.setFixedWidth(110)
            self.nick.editingFinished.connect(
                lambda: self._write_name(NICK_OFF, NICK_LEN, self.nick))
            lay.addWidget(QLabel("Nick"))
            lay.addWidget(self.nick)

        lay.addStretch(1)
        for kind, text in (("to", "To LF+"), ("from", "From LF+"),
                           ("all_to", "All To LF+"), ("all_from", "All From LF+")):
            b = QPushButton(text)
            b.setObjectName("xfer")
            b.clicked.connect(lambda _c, k=kind: self.transfer.emit(k))
            lay.addWidget(b)

    def set_count(self, n: int):
        self._count = n
        self.spin.blockSignals(True)
        self.spin.setMaximum(max(1, n))
        self.spin.blockSignals(False)

    def set_index(self, idx: int):
        self.spin.blockSignals(True)
        self.spin.setValue(idx + 1)
        self.spin.blockSignals(False)

    def bind(self, values: list[int]):
        self._values = values
        if self.has_name:
            self.name.blockSignals(True)
            self.name.setText(_ascii(values[:NAME_LEN]))
            self.name.blockSignals(False)
            self.nick.blockSignals(True)
            self.nick.setText(_ascii(values[NICK_OFF:NICK_OFF + NICK_LEN]))
            self.nick.blockSignals(False)

    def _write_name(self, off, length, field):
        if self._values is None:
            return
        new = encode_ascii(field.text(), length)
        if new != self._values[off:off + length]:
            self._values[off:off + length] = new
            self.edited.emit()


def _ascii(byts) -> str:
    return decode_ascii(byts, 0, len(byts))
