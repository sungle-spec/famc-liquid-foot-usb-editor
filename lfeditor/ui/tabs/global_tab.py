"""Global settings tab — for the Config (type 4) records, which the original presents as
single global screens with no record selector, just "Send Global Settings / Get Settings"
buttons. Sections bind to a specific Config record (the device names live in record #1, the
numeric/global settings in record #0)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QScrollArea, QLabel, QPushButton,
)

from ..components import section as section_panel
from ..tabspec import Section, GlobalSpec   # Qt-free spec dataclasses (shared with the web schema)


class GlobalTab(QWidget):
    """No rail. A title row with Send/Get buttons, then columns of section panels whose fields
    bind to the Config record named by each Section.record."""

    def __init__(self, spec: GlobalSpec, on_transfer: Callable[[str, int, int], None] | None = None):
        super().__init__()
        self.spec = spec
        self.type_ = spec.type
        self._on_transfer = on_transfer
        self._records: list = []
        self._sections: list[tuple[Section, list]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 8, 8)
        root.setSpacing(8)

        top = QHBoxLayout()
        ttl = QLabel(spec.title)
        ttl.setObjectName("tabTitle")
        top.addWidget(ttl)
        top.addStretch(1)
        send = QPushButton("Send Global Settings To LF+")
        send.setObjectName("xfer")
        send.clicked.connect(lambda: self._transfer("all_to"))
        get = QPushButton("Get Settings from LF+")
        get.setObjectName("xfer")
        get.clicked.connect(lambda: self._transfer("all_from"))
        top.addWidget(send)
        top.addWidget(get)
        if spec.live_calibrate:
            cal = QPushButton("Live Calibrate…")
            cal.setObjectName("xfer")
            cal.clicked.connect(lambda: self.window().open_live_calibration())
            top.addWidget(cal)
        root.addLayout(top)

        cols_host = QWidget()
        cols = QHBoxLayout(cols_host)
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(8)
        self._all_fields = []
        for column in spec.columns:
            colw = QWidget()
            colw.setMaximumWidth(252)
            cv = QVBoxLayout(colw)
            cv.setContentsMargins(0, 0, 0, 0)
            cv.setSpacing(8)
            for sec in column:
                cv.addWidget(self._build_section(sec))
            cv.addStretch(1)
            cols.addWidget(colw, 0, Qt.AlignTop)
        cols.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(cols_host)
        root.addWidget(scroll, 1)

    def _build_section(self, sec: Section) -> QWidget:
        from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QLineEdit, QLabel
        from .base import _field_help, apply_tooltip
        from ..help_text import section_tooltip
        body = QWidget()
        sec_tip = section_tooltip(self.spec.title, sec.title)
        if sec.labeled:
            form = QFormLayout(body)
            form.setContentsMargins(2, 2, 2, 2)
            form.setSpacing(5)
            form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            form.setRowWrapPolicy(QFormLayout.DontWrapRows)
            for f in sec.fields:
                f.set_on_change(self._on_edit)
                w = f.build()
                if isinstance(w, (QAbstractSpinBox, QComboBox, QLineEdit)):
                    w.setMaximumWidth(110)
                tip = _field_help(self.spec.title, f) or sec_tip
                apply_tooltip(w, tip)
                if getattr(f, "label", ""):
                    lab = QLabel(f.label)
                    if tip:
                        lab.setToolTip(tip)
                    form.addRow(lab, w)
                else:
                    form.addRow(w)
        else:
            v = QVBoxLayout(body)
            v.setContentsMargins(2, 2, 2, 2)
            v.setSpacing(5)
            for f in sec.fields:
                f.set_on_change(self._on_edit)
                w = f.build()
                tip = _field_help(self.spec.title, f) or sec_tip
                apply_tooltip(w, tip)
                v.addWidget(w)
        self._sections.append((sec, sec.fields))
        self._all_fields.extend(sec.fields)
        panel = section_panel(sec.title, body, sec.note)
        if sec_tip:
            panel.setToolTip(sec_tip)
        return panel

    def refresh_context(self, dump) -> None:
        """See SectionedTab.refresh_context — same channel-name-cache-refresh need applies here
        (the Exp Pedals tab's "Chan" picker is a ChannelNameField)."""
        for f in self._all_fields:
            f.set_context(dump)

    def set_dump(self, dump) -> None:
        self._records = dump.records(self.type_)
        self.refresh_context(dump)
        for sec, fields in self._sections:
            idx = sec.record if sec.record < len(self._records) else 0
            if idx < len(self._records):
                vals = self._records[idx].values
                for f in fields:
                    f.load(vals)

    def set_raw_visible(self, on: bool):  # parity with SectionedTab; global tabs have no raw view
        pass

    def _on_edit(self):
        self.window().mark_dirty()

    def _transfer(self, kind: str):
        if self._on_transfer:
            self._on_transfer(kind, self.type_, 0)
