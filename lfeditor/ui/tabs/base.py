"""Sectioned tab framework — the faithful LF+ Editor layout.

A tab is a left record rail + a right detail pane. The detail pane has a `RecordHeader`
(name/nick LCD fields + transfer buttons) on top, then one or more columns of titled
`Section` panels, and an optional raw-byte table hidden behind a View toggle.

Each `Section` carries a list of `Field` specs (from ui/fields.py) which keep the existing
build/load/set_on_change binding contract, so all existing field editors are reused.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QSplitter, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel,
)

from ..widgets import RecordRail
from ..components import RecordHeader, section as section_panel
from ..fields import Field
from ..help_text import tooltip_for, section_tooltip
from ..tabspec import Section, TabSpec   # Qt-free spec dataclasses (shared with the web schema)


def _field_help(tab: str, f) -> str:
    """Curated hover text for a field on `tab`, keyed by its label or (for toggles, whose label
    renders inside the widget) its caption."""
    return tooltip_for(tab, getattr(f, "label", "") or getattr(f, "_caption", ""))


def apply_tooltip(widget, text: str) -> None:
    """Set `text` as the hover tooltip on `widget` AND every descendant widget, so hovering any
    part of a composite control (a rocker switch + its caption, a picker + its dropdown) shows the
    same help. Without this, an inner widget with no/own tooltip would shadow the container's.
    No-op for empty text."""
    if not text:
        return
    widget.setToolTip(text)
    for child in widget.findChildren(QWidget):
        child.setToolTip(text)


class SectionedTab(QWidget):
    """Renders a TabSpec: rail | (header + section columns + raw table)."""

    def __init__(self, spec: TabSpec, on_transfer: Callable[[str, int, int], None] | None = None):
        super().__init__()
        self.spec = spec
        self.type_ = spec.type
        self._on_transfer = on_transfer
        self._rec = None
        self._records: list = []
        self._raw_visible = False

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(0)
        QHBoxLayout(self).addWidget(split)

        # The per-tab record rail is superseded by the Q-LIST dock; keep it built (navigation +
        # name refresh still flow through it) but hidden so the editor uses the full width.
        self.rail = RecordRail(spec.title)
        self.rail.selected.connect(self._show)
        split.addWidget(self.rail)
        self.rail.hide()

        detail = QWidget()
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(10, 8, 8, 8)
        dl.setSpacing(8)

        self.header = RecordHeader(spec.title, has_name=spec.has_name)
        self.header.record_changed.connect(self._goto)
        self.header.edited.connect(self._on_edit)
        self.header.transfer.connect(self._do_transfer)
        dl.addWidget(self.header)

        # columns of sections
        cols_host = QWidget()
        cols = QHBoxLayout(cols_host)
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(8)
        self._all_fields: list[Field] = []
        for column in spec.columns:
            colw = QWidget()
            cv = QVBoxLayout(colw)
            cv.setContentsMargins(0, 0, 0, 0)
            cv.setSpacing(8)
            for sec in column:
                cv.addWidget(self._build_section(sec))
            cv.addStretch(1)
            cols.addWidget(colw, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(cols_host)
        dl.addWidget(scroll, 1)

        # raw table (hidden by default)
        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["idx", "value"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setMaximumHeight(150)
        self.tbl.setVisible(False)
        dl.addWidget(self.tbl)

        split.addWidget(detail)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 1040])

    def _build_section(self, sec: Section) -> QWidget:
        body = QWidget()
        sec_tip = section_tooltip(self.spec.title, sec.title)   # help for label-less grids/tables + the panel title
        if sec.labeled:
            form = QFormLayout(body)
            form.setContentsMargins(2, 2, 2, 2)
            form.setSpacing(5)
            form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for f in sec.fields:
                f.set_on_change(self._on_edit)
                w = f.build()
                self._enable_multi_apply(f)
                self._all_fields.append(f)
                tip = _field_help(self.spec.title, f)
                apply_tooltip(w, tip)
                if getattr(f, "label", ""):
                    lab = QLabel(f.label)            # explicit label so the hover help covers it too
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
                self._enable_multi_apply(f)
                self._all_fields.append(f)
                tip = _field_help(self.spec.title, f) or sec_tip      # label-less grids fall back to section help
                apply_tooltip(w, tip)
                if getattr(f, "label", ""):
                    lab = QLabel(f.label)
                    lab.setObjectName("sectionNote")
                    if tip:
                        lab.setToolTip(tip)
                    v.addWidget(lab)
                v.addWidget(w)
        panel = section_panel(sec.title, body, sec.note)
        if sec_tip:
            panel.setToolTip(sec_tip)
        return panel

    def _enable_multi_apply(self, f) -> None:
        """Give a toggle field the right-click 'apply across many records' action."""
        if hasattr(f, "set_multi_apply"):
            from ..record_ops import TYPE_SINGULAR
            label = TYPE_SINGULAR.get(self.type_, "record")
            f.set_multi_apply(self._multi_apply_bit, lambda: len(self._records), label)

    def _multi_apply_bit(self, offset: int, bitmask: int, on: bool, lo: int, hi: int) -> None:
        """Set/clear one flag bit across every record whose number is in [lo, hi]."""
        changed = 0
        for rec in self._records:
            if lo <= rec.number <= hi and offset < len(rec.values):
                v = rec.values[offset]
                nv = (v | bitmask) if on else (v & ~bitmask & 0xFF)
                if nv != v:
                    rec.values[offset] = nv
                    changed += 1
        if changed:
            self.reload_current()
            self.window().mark_dirty()
            self.window().statusBar().showMessage(
                f"Applied toggle to {changed} record(s)", 4000)

    # --- data ---
    def set_dump(self, dump) -> None:
        for f in self._all_fields:
            f.set_context(dump)
        self._records = dump.records(self.type_)
        self.rail.set_records(self._records)
        self.header.set_count(len(self._records))
        row = self.spec.default_row if self.spec.default_row < len(self._records) else 0
        if self._records:
            self.rail.list.setCurrentRow(row)

    def _goto(self, idx: int):
        # spinner-driven navigation -> select the rail row that maps to record idx
        if 0 <= idx < len(self._records):
            for r in range(self.rail.list.count()):
                if self.rail.list.item(r).data(Qt.UserRole) == idx:
                    self.rail.list.setCurrentRow(r)
                    return

    def _show(self, idx: int) -> None:
        if not (0 <= idx < len(self._records)):
            return
        self._rec = self._records[idx]
        vals = self._rec.values
        self.header.set_index(idx)
        self.header.bind(vals)
        for f in self._all_fields:
            f.load(vals)
            if hasattr(f, "bind_record"):   # fields that edit a linked sibling record (ext labels)
                f.bind_record(self._rec)
        self._fill_raw(vals)

    def _fill_raw(self, vals):
        if not self._raw_visible:
            return
        start = self.spec.raw_from
        self.tbl.setRowCount(max(0, len(vals) - start))
        for row, i in enumerate(range(start, len(vals))):
            v = vals[i]
            a = QTableWidgetItem(str(i)); a.setTextAlignment(Qt.AlignCenter)
            b = QTableWidgetItem(f"{v}  (0x{v:02X})"); b.setTextAlignment(Qt.AlignCenter)
            self.tbl.setItem(row, 0, a)
            self.tbl.setItem(row, 1, b)

    def set_raw_visible(self, on: bool):
        self._raw_visible = on
        self.tbl.setVisible(on)
        if on and self._rec is not None:
            self._fill_raw(self._rec.values)

    def _on_edit(self):
        self.window().mark_dirty()
        self.rail.set_records(self._records)  # refresh name labels

    def _do_transfer(self, kind: str):
        if self._on_transfer and self._rec is not None:
            self._on_transfer(kind, self.type_, self._records.index(self._rec))

    # --- whole-record copy/paste/clear interface (used by the toolbar) ---
    def current_record(self):
        return self._rec

    def current_type(self) -> int:
        return self.type_

    def reload_current(self) -> None:
        """Re-bind the current record after its bytes were changed externally (paste/clear)."""
        if self._rec is not None and self._rec in self._records:
            idx = self._records.index(self._rec)
            self.rail.set_records(self._records)  # refresh labels (selection preserved)
            self._show(idx)
