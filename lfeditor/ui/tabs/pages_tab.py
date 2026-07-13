"""Pages tab — a faithful clone of the original's graphical pedalboard editor.

A page (record type 7) assigns each of 60 physical buttons two functions. The original shows the
board the way the hardware is laid out: a 4×3 grid of **stomp-switch tiles** (each = its number on
both sides + a footswitch graphic + the two assigned function names), viewed 12 buttons at a time
via a **page-group navigator** (start values 1/13/25/37/49). Two panels below edit the selected
page's parameters and the selected button's definition. All bound to the mapped Page bytes
(model/page.py) — edits write straight into the record's `values`, so re-encoding stays lossless.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QFont
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QFrame, QSplitter,
    QSpinBox, QComboBox,
)

from ..widgets import RecordRail
from ..components import RecordHeader, section as section_panel, LabeledToggle
from ..fields import EnumField, IntField, ToggleField
from ..theme import GREEN, AMBER, ACCENT, PANEL, BORDER, TEXT_DIM
from ...model.page import (
    FUNC1_OFF, FUNC2_OFF, NUM_BUTTONS, BUTTON_PARAM_OFF, BTN_TRIGGER_TYPE_MASK,
    BTN_TRIGGER_TYPES, BTN_FUNC1_SCROLLS_BIT, BTN_FUNC2_SCROLLS_BIT, BTN_DOUBLE_TAP_BIT,
    BTN_WAIT_RELEASE_BIT, STATUS1_LED_OFF, FORCE_MODE_OFF, ALL_BTN_DBL_BIT, MENU_TRIGGER_OFF,
    FORCE_IA_MAP_OFF, IA_SLOT_TRIG_NUM_OFF, PRESET_BTN_COLORS_OFF, PRESET_BTN_COLOR_NAMES,
    decode_button_function, PAGE_SYSTEM_FUNCTIONS,
)
from ...model.config import COLOR_NAMES

GROUP_SIZE = 12          # one page-group = 12 physical buttons (4 cols × 3 rows)
NUM_GROUPS = NUM_BUTTONS // GROUP_SIZE  # 5 groups, start values 1/13/25/37/49


def _slot_to_offset(slot: int) -> int:
    """Map a visual slot (0=top-left .. 11=bottom-right, row-major) to the button offset within a
    group. The hardware/editor stacks low numbers at the BOTTOM, so rows run bottom-up."""
    row, col = divmod(slot, 4)
    return (2 - row) * 4 + col


class SwitchGlyph(QWidget):
    """A small painted footswitch (metallic cap on a base), echoing the original's switch art."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(34, 30)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # base
        base = QLinearGradient(0, h * 0.55, 0, h)
        base.setColorAt(0, QColor("#8a8f95")); base.setColorAt(1, QColor("#3c4147"))
        p.setPen(QPen(QColor("#202428"), 1)); p.setBrush(base)
        p.drawRoundedRect(QRectF(w * 0.28, h * 0.55, w * 0.44, h * 0.4), 3, 3)
        # cap
        cap = QLinearGradient(0, 0, w, h * 0.6)
        cap.setColorAt(0, QColor("#e9edf1")); cap.setColorAt(0.5, QColor("#aab0b6"))
        cap.setColorAt(1, QColor("#6c7177"))
        p.setBrush(cap); p.setPen(QPen(QColor("#202428"), 1))
        p.drawEllipse(QRectF(w * 0.18, h * 0.04, w * 0.64, h * 0.5))
        p.end()


class SwitchTile(QFrame):
    """One physical button: a beveled label box (Function-1/2 names) above a footswitch graphic,
    flanked by the button number. Click selects; drag onto another swaps (Shift = copy)."""

    clicked = Signal(int)
    swap = Signal(int, int, bool)  # src abs index, dst abs index, copy

    def __init__(self):
        super().__init__()
        self.abs_index = 0
        self.setObjectName("switchtile")
        v = QVBoxLayout(self)
        v.setContentsMargins(3, 3, 3, 2)
        v.setSpacing(2)

        self.box = QFrame(); self.box.setObjectName("tilebox")
        self.box.setFixedHeight(40)
        bl = QVBoxLayout(self.box); bl.setContentsMargins(6, 4, 6, 4); bl.setSpacing(0)
        self.f1 = QLabel("—"); self.f2 = QLabel("—")
        for w in (self.f1, self.f2):
            w.setObjectName("tilefn"); w.setAlignment(Qt.AlignCenter)
        bl.addWidget(self.f1); bl.addWidget(self.f2)
        v.addWidget(self.box)

        row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(2)
        self.n_left = QLabel("1"); self.n_right = QLabel("1")
        for n in (self.n_left, self.n_right):
            n.setObjectName("tilenum")
        self.n_left.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.n_right.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        row.addWidget(self.n_left, 1)
        row.addWidget(SwitchGlyph(), 0)
        row.addWidget(self.n_right, 1)
        v.addLayout(row)

        self.setFixedSize(150, 84)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)
        self._drag_start = None
        self.set_selected(False)

    def set_button(self, abs_index: int, f1: str, f2: str):
        self.abs_index = abs_index
        self.n_left.setText(str(abs_index + 1))
        self.n_right.setText(str(abs_index + 1))
        self.f1.setText(f1 or "—")
        self.f2.setText(f2 or "—")

    def set_selected(self, on: bool):
        self.setProperty("sel", on)
        self.style().unpolish(self); self.style().polish(self)

    def mousePressEvent(self, e):
        self._drag_start = e.position().toPoint()
        self.clicked.emit(self.abs_index)

    def mouseMoveEvent(self, e):
        if self._drag_start is None:
            return
        if (e.position().toPoint() - self._drag_start).manhattanLength() > 8:
            from PySide6.QtGui import QDrag
            from PySide6.QtCore import QMimeData
            drag = QDrag(self); mime = QMimeData(); mime.setText(str(self.abs_index))
            drag.setMimeData(mime); drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, e):
        if e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        src = int(e.mimeData().text())
        copy = bool(e.modifiers() & Qt.ShiftModifier)
        if src != self.abs_index:
            self.swap.emit(src, self.abs_index, copy)
        e.acceptProposedAction()


class GroupBox(QFrame):
    """One navigator cell: the 12 button numbers of a page-group, click to view that group."""

    picked = Signal(int)

    def __init__(self, group: int):
        super().__init__()
        self.group = group
        self.setObjectName("groupbox")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(168, 74)
        v = QVBoxLayout(self); v.setContentsMargins(8, 6, 8, 6); v.setSpacing(2)
        for vr in range(3):
            row = QHBoxLayout(); row.setSpacing(2)
            for col in range(4):
                slot = vr * 4 + col
                btn = group * GROUP_SIZE + _slot_to_offset(slot)
                lab = QLabel(str(btn + 1)); lab.setObjectName("grpnum")
                lab.setAlignment(Qt.AlignCenter)
                lab.setFixedSize(34, 18)
                row.addWidget(lab)
            v.addLayout(row)

    def set_selected(self, on: bool):
        self.setProperty("sel", on)
        self.style().unpolish(self); self.style().polish(self)

    def mousePressEvent(self, _e):
        self.picked.emit(self.group)


class PagesTab(QWidget):
    def __init__(self, on_transfer: Callable[[str, int, int], None] | None = None):
        super().__init__()
        self.type_ = 7
        self._on_transfer = on_transfer
        self._records: list = []
        self._rec = None
        self._sel = 0           # absolute selected button index
        self._group = 0         # current page-group shown on the board
        self._ia: list[str] = []
        self._page_names: list[str] = []

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(0)
        QHBoxLayout(self).setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(split)
        self.rail = RecordRail("Page")  # hidden: navigation now via the Q-LIST dock + header spinner
        self.rail.selected.connect(self._show)
        split.addWidget(self.rail)
        self.rail.hide()

        detail = QWidget()
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(10, 8, 8, 8)
        dl.setSpacing(8)
        self.header = RecordHeader("Page")
        self.header.record_changed.connect(self._goto)
        self.header.edited.connect(self._mark)
        self.header.transfer.connect(lambda k: self._transfer(k))
        dl.addWidget(self.header)

        # --- board + navigator ---
        mid = QHBoxLayout(); mid.setSpacing(12)
        mid.addWidget(self._board_panel(), 1)
        mid.addWidget(self._navigator_panel(), 0)
        dl.addLayout(mid, 2)

        # --- parameter panels ---
        panels = QHBoxLayout(); panels.setSpacing(8)
        panels.addWidget(self._params_panel(), 1)
        panels.addWidget(self._button_panel(), 1)
        dl.addLayout(panels, 1)

        split.addWidget(detail)
        split.setStretchFactor(1, 1)
        split.setSizes([210, 1070])

    # --- panels ---
    def _board_panel(self) -> QWidget:
        board = QWidget()
        grid = QGridLayout(board)
        grid.setSpacing(8)
        grid.setContentsMargins(6, 6, 6, 6)
        self.tiles: list[SwitchTile] = []
        for slot in range(GROUP_SIZE):
            t = SwitchTile()
            t.clicked.connect(self._select)
            t.swap.connect(self._swap)
            r, c = divmod(slot, 4)
            grid.addWidget(t, r, c)
            self.tiles.append(t)
        grid.setRowStretch(3, 1)
        return section_panel("Click a button to edit it below — drag onto another to swap "
                             "(Shift-drag to copy)", board)

    def _navigator_panel(self) -> QWidget:
        inner = QWidget()
        v = QVBoxLayout(inner); v.setContentsMargins(4, 4, 4, 4); v.setSpacing(5)
        hint = QLabel("Click a page box to\ndisplay it as a group")
        hint.setObjectName("sectionNote")
        v.addWidget(hint)
        self.group_boxes: list[GroupBox] = []
        for g in range(NUM_GROUPS):
            gb = GroupBox(g)
            gb.picked.connect(self._set_group)
            self.group_boxes.append(gb)
            cell = QVBoxLayout(); cell.setSpacing(1)
            cell.addWidget(gb, alignment=Qt.AlignHCenter)
            cap = QLabel(f"Start {g * GROUP_SIZE + 1}")
            cap.setObjectName("sectionNote"); cap.setAlignment(Qt.AlignHCenter)
            cell.addWidget(cap)
            v.addLayout(cell)
        v.addStretch(1)
        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame); scroll.setWidget(inner)
        scroll.setMinimumWidth(190); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget(); bl = QVBoxLayout(body); bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(scroll)
        return section_panel("Page Groups", body)

    def _params_panel(self) -> QWidget:
        self._param_fields = [
            EnumField(STATUS1_LED_OFF, "Status #1 LED colour", COLOR_NAMES),
            IntField(MENU_TRIGGER_OFF, "Menu button trigger (0=B2+B3)", 0, 60),
            EnumField(PRESET_BTN_COLORS_OFF, "Preset btn — selected", PRESET_BTN_COLOR_NAMES,
                      nibble="low"),
            EnumField(PRESET_BTN_COLORS_OFF, "Preset btn — not selected", PRESET_BTN_COLOR_NAMES,
                      nibble="high"),
            IntField(FORCE_IA_MAP_OFF, "Force IA map (0=none)", 0, 60),
            IntField(IA_SLOT_TRIG_NUM_OFF, "IA-slot to trigger (0=none)", 0, 60),
            ToggleField(FORCE_MODE_OFF, ALL_BTN_DBL_BIT, "All buttons double-tap"),
        ]
        from PySide6.QtWidgets import QAbstractSpinBox, QFormLayout
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(6, 4, 6, 4)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        from ..help_text import tooltip_for
        from .base import apply_tooltip
        for f in self._param_fields:
            f.set_on_change(self._mark)
            w = f.build()
            if isinstance(w, (QAbstractSpinBox, QComboBox)):
                w.setMaximumWidth(170)
            tip = tooltip_for("Pages", getattr(f, "label", "") or getattr(f, "_caption", ""))
            apply_tooltip(w, tip)
            if getattr(f, "label", ""):
                lab = QLabel(f.label)
                if tip:
                    lab.setToolTip(tip)
                form.addRow(lab, w)
            else:
                form.addRow(w)
        return section_panel("Page Parameters", body)

    def _button_panel(self) -> QWidget:
        from PySide6.QtWidgets import QFormLayout
        body = QWidget(); v = QVBoxLayout(body); v.setContentsMargins(2, 2, 2, 2); v.setSpacing(7)
        self.sel_label = QLabel("Button #1")
        self.sel_label.setStyleSheet(f"color:{AMBER};font-weight:700;")
        v.addWidget(self.sel_label)
        # Each function = a Type dropdown (Empty/Preset/Function/IA Slot/Page Select) + a Value
        # dropdown listing that type's items by name, like the original's button editor.
        form = QFormLayout()
        form.setContentsMargins(0, 2, 0, 2)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._func_bases = [FUNC1_OFF, FUNC2_OFF]
        self.f_types: list[QComboBox] = []
        self.f_values: list[QComboBox] = []
        for fi, cap in ((0, "Function 1"), (1, "Function 2")):
            tc = QComboBox()
            for lbl, key in (("Empty", "empty"), ("Preset", "preset"), ("Function", "func"),
                             ("IA Slot", "ia"), ("Page Select", "page")):
                tc.addItem(lbl, key)
            tc.setFixedWidth(110)
            tc.currentIndexChanged.connect(lambda _i, fi=fi: self._on_type_change(fi))
            vc = QComboBox()
            vc.setMinimumWidth(150)
            vc.currentIndexChanged.connect(lambda _i, fi=fi: self._on_value_change(fi))
            field = QHBoxLayout(); field.setContentsMargins(0, 0, 0, 0); field.setSpacing(6)
            field.addWidget(tc); field.addWidget(vc, 1)
            holder = QWidget(); holder.setLayout(field)
            lab = QLabel(cap); lab.setStyleSheet(f"color:{GREEN}; font-weight:700;")
            form.addRow(lab, holder)
            self.f_types.append(tc); self.f_values.append(vc)
        self.trig = QComboBox()
        for val, name in BTN_TRIGGER_TYPES.items():
            self.trig.addItem(name, val)
        self.trig.currentIndexChanged.connect(self._write_trigtype)
        form.addRow("Trigger type", self.trig)
        v.addLayout(form)
        self.tg_f1 = LabeledToggle(0, BTN_FUNC1_SCROLLS_BIT, "Function-1 Trigger Scrolls")
        self.tg_f2 = LabeledToggle(0, BTN_FUNC2_SCROLLS_BIT, "Function-2 Trigger Scrolls")
        self.tg_dbl = LabeledToggle(0, BTN_DOUBLE_TAP_BIT, "Enable Double-Tap")
        self.tg_wait = LabeledToggle(0, BTN_WAIT_RELEASE_BIT, "Press = Wait for Release")
        from ..help_text import tooltip_for
        from .base import apply_tooltip
        for t, cap in ((self.tg_f1, "Function-1 Trigger Scrolls"),
                       (self.tg_f2, "Function-2 Trigger Scrolls"),
                       (self.tg_dbl, "Enable Double-Tap"),
                       (self.tg_wait, "Press = Wait for Release")):
            t.changed.connect(self._mark)
            tip = tooltip_for("Pages", cap)
            apply_tooltip(t, tip)
            v.addWidget(t)
        v.addStretch(1)
        return section_panel("Page Button Definition", body)

    # --- data ---
    def set_dump(self, dump) -> None:
        self._records = dump.records(self.type_)
        self._presets = [(getattr(r, "name", "") or "").strip() for r in dump.presets]
        self._ia = [(getattr(r, "name", "") or "").strip() for r in dump.records(3)]
        self._page_names = [((getattr(r, "nick", "") or getattr(r, "name", "") or "").strip())
                            for r in self._records]
        self.rail.set_records(self._records)
        self.header.set_count(len(self._records))
        if self._records:
            self.rail.list.setCurrentRow(0)

    def _goto(self, idx):
        if 0 <= idx < len(self._records):
            for r in range(self.rail.list.count()):
                if self.rail.list.item(r).data(Qt.UserRole) == idx:
                    self.rail.list.setCurrentRow(r)
                    return

    def _show(self, idx):
        if not (0 <= idx < len(self._records)):
            return
        self._rec = self._records[idx]
        self.header.set_index(idx)
        self.header.bind(self._rec.values)
        self._refresh_board()
        for f in self._param_fields:
            f.load(self._rec.values)
        self._select(self._sel)

    # --- whole-record copy/paste/clear interface (used by the toolbar) ---
    def current_record(self):
        return self._rec

    def current_type(self) -> int:
        return self.type_

    def reload_current(self) -> None:
        if self._rec is not None and self._rec in self._records:
            self._show(self._records.index(self._rec))
            self.rail.set_records(self._records)

    def _set_group(self, g: int):
        self._group = g
        for gb in self.group_boxes:
            gb.set_selected(gb.group == g)
        self._refresh_board()
        # keep selection on-board: if the selected button isn't in this group, select its first
        if not (g * GROUP_SIZE <= self._sel < (g + 1) * GROUP_SIZE):
            self._select(g * GROUP_SIZE)
        else:
            self._select(self._sel)

    def _refresh_board(self):
        for gb in self.group_boxes:
            gb.set_selected(gb.group == self._group)
        if self._rec is None:
            return
        vals = self._rec.values
        for slot, t in enumerate(self.tiles):
            btn = self._group * GROUP_SIZE + _slot_to_offset(slot)
            t.set_button(btn, self._fn_text(vals[FUNC1_OFF + btn]),
                         self._fn_text(vals[FUNC2_OFF + btn]))
            t.set_selected(btn == self._sel)

    def _fn_text(self, val: int) -> str:
        # Resolve the function byte to the original editor's label (NONE / PRESET B# / system
        # function / "(NNN) IA-slot name" / "(NNN) page name").
        return decode_button_function(val, self._ia, self._page_names) or "—"

    def _select(self, abs_index):
        self._sel = abs_index
        # make sure we're viewing the group that holds it
        self._group = abs_index // GROUP_SIZE
        for gb in self.group_boxes:
            gb.set_selected(gb.group == self._group)
        for t in self.tiles:
            t.set_selected(t.abs_index == abs_index)
        if self._rec is None:
            return
        vals = self._rec.values
        self.sel_label.setText(f"Button #{abs_index + 1}")
        self._loading = True
        for fi, base in enumerate(self._func_bases):
            typ, val = self._decode_type(vals[base + abs_index])
            tc = self.f_types[fi]
            tc.setCurrentIndex(max(0, tc.findData(typ)))
            self._populate_values(fi, typ)
            vc = self.f_values[fi]
            ix = vc.findData(val)
            vc.setCurrentIndex(ix if ix >= 0 else 0)
        self._loading = False
        flags = vals[BUTTON_PARAM_OFF + abs_index]
        self.trig.blockSignals(True)
        self.trig.setCurrentIndex(self.trig.findData(flags & BTN_TRIGGER_TYPE_MASK))
        self.trig.blockSignals(False)
        for tg in (self.tg_f1, self.tg_f2, self.tg_dbl, self.tg_wait):
            tg.toggle.offset = BUTTON_PARAM_OFF + abs_index
            tg.bind(vals)

    # --- Function 1/2 type+value editors (mirror the original's dropdowns) ---
    @staticmethod
    def _decode_type(byte: int):
        if byte == 0:
            return ("empty", 0)
        if 1 <= byte <= 60:
            return ("preset", byte)
        if 61 <= byte <= 127:
            return ("func", byte - 60)
        if 128 <= byte <= 187:
            return ("ia", byte - 127)
        if byte >= 200:
            return ("page", byte - 199)
        return ("preset", byte)

    @staticmethod
    def _compose(typ: str, val: int) -> int:
        return {"empty": 0, "preset": val, "func": 60 + val,
                "ia": 127 + val, "page": 199 + val}[typ]

    def _populate_values(self, fi: int, typ: str):
        vc = self.f_values[fi]
        vc.blockSignals(True)
        vc.clear()
        if typ == "empty":
            vc.addItem("—", 0); vc.setEnabled(False)
        else:
            vc.setEnabled(True)
            if typ == "preset":
                for n in range(1, 61):
                    vc.addItem(f"PRESET B#{n:02d}", n)
            elif typ == "func":
                for f in sorted(PAGE_SYSTEM_FUNCTIONS):
                    vc.addItem(PAGE_SYSTEM_FUNCTIONS[f], f)
            elif typ == "ia":
                for s in range(1, 61):
                    nm = self._ia[s - 1] if s - 1 < len(self._ia) else ""
                    vc.addItem(f"({s:03d}) {nm}".rstrip(), s)
            elif typ == "page":
                for p in range(1, 51):
                    nm = self._page_names[p - 1] if p - 1 < len(self._page_names) else ""
                    vc.addItem(f"({p:03d}) {nm}".rstrip(), p)
        vc.blockSignals(False)

    def _on_type_change(self, fi: int):
        if getattr(self, "_loading", False) or self._rec is None:
            return
        typ = self.f_types[fi].currentData()
        self._populate_values(fi, typ)
        val = self.f_values[fi].itemData(0) or 0
        self._set_func_byte(fi, 0 if typ == "empty" else self._compose(typ, val))

    def _on_value_change(self, fi: int):
        if getattr(self, "_loading", False) or self._rec is None:
            return
        typ = self.f_types[fi].currentData()
        val = self.f_values[fi].currentData() or 0
        self._set_func_byte(fi, self._compose(typ, val))

    def _set_func_byte(self, fi: int, byte: int):
        off = self._func_bases[fi] + self._sel
        if self._rec.values[off] != byte:
            self._rec.values[off] = byte & 0xFF
            self._refresh_board()
            self._mark()

    def _write_trigtype(self):
        if self._rec is None:
            return
        off = BUTTON_PARAM_OFF + self._sel
        cur = self._rec.values[off]
        new = (cur & ~BTN_TRIGGER_TYPE_MASK) | (self.trig.currentData() & BTN_TRIGGER_TYPE_MASK)
        if new != cur:
            self._rec.values[off] = new
            self._mark()

    def _swap(self, src, dst, copy):
        if self._rec is None:
            return
        v = self._rec.values
        for base in (FUNC1_OFF, FUNC2_OFF, BUTTON_PARAM_OFF):
            if copy:
                v[base + dst] = v[base + src]
            else:
                v[base + src], v[base + dst] = v[base + dst], v[base + src]
        self._refresh_board()
        self._select(dst)
        self._mark()

    def set_raw_visible(self, on: bool):
        pass

    def _mark(self):
        self.window().mark_dirty()
        self.rail.set_records(self._records)

    def _transfer(self, kind):
        if self._on_transfer and self._rec is not None:
            self._on_transfer(kind, self.type_, self._records.index(self._rec))
