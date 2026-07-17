"""
Declarative field specs for record editors.

Each spec knows how to build a Qt widget and bind it two-way to a record's decoded
`values` list. All edits write straight back into `values`, so re-encoding stays lossless
and only-changed-records-change. Tabs are then assembled from a list of specs (see specs.py),
which keeps every bespoke editor DRY and faithful to the verified field map.
"""
from __future__ import annotations

# Qt is optional at import time: the desktop UI needs it to build widgets, but the web/schema build
# (lfeditor/schema.py, run under Pyodide) only introspects the field-spec *data* below — no Qt. The
# `build()`/`load()` methods reference these names and run only when Qt is present.
try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QWidget, QLineEdit, QSpinBox, QCheckBox, QComboBox, QGridLayout, QLabel, QHBoxLayout,
    )
    from .dnd import RecordDropTarget
    _HAVE_QT = True
except Exception:  # noqa: BLE001
    _HAVE_QT = False

from ..text import decode_ascii, encode_ascii

NAME_LEN = 16


if _HAVE_QT:
    class _DropCombo(RecordDropTarget, QComboBox):
        """A slot-picker combo that accepts a dragged record reference whose type matches
        `target_type` and calls `on_drop(number)` (assign a Find/Q-LIST result by drag-drop)."""

        def __init__(self, target_type: int, on_drop):
            super().__init__()
            self._target_type = target_type
            self._on_drop = on_drop
            self.setAcceptDrops(True)

        def _accepts(self, type_, number):
            return type_ == self._target_type

        def _handle_drop(self, type_, number, event):
            self._on_drop(number)

    class _CmdDropTable(RecordDropTarget):
        """Mixin for the command table's QTableWidget: accept a dragged IA-Slot (type 3) and build
        an 'IA ON Trig' command from it. `_on_drop(type_, number, row)` is supplied by the field."""

        def _accepts(self, type_, number):
            return type_ == 3

        def _handle_drop(self, type_, number, event):
            try:
                row = self.rowAt(int(event.position().y()))
            except AttributeError:
                row = self.rowAt(event.pos().y())
            self._on_drop(type_, number, row)


def _grid_host(spacing: int = 2):
    """A bare QWidget with a zero-margin QGridLayout — the common host for the grid fields.
    Returns (widget, grid)."""
    host = QWidget()
    grid = QGridLayout(host)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(spacing)
    return host, grid


class Field:
    label = ""

    def build(self) -> QWidget: ...
    def load(self, values: list[int]) -> None: ...
    def set_context(self, dump) -> None:
        """Optional: receive the whole dump so a field can resolve cross-record references
        (e.g. a slot picker that lists presets/songs by name). Default: ignore."""

    def _emit_dirty(self):
        if self._on_change:
            self._on_change()

    def __init__(self):
        self._on_change = None

    def set_on_change(self, cb):
        self._on_change = cb


class StringField(Field):
    """An editable ASCII string of `length` bytes at `start` (space-padded, lossless)."""

    def __init__(self, start: int, length: int, label: str):
        super().__init__()
        self.start, self.length, self.label = start, length, label

    def build(self):
        self.w = QLineEdit()
        self.w.setMaxLength(self.length)
        self.w.editingFinished.connect(self._write)
        return self.w

    def load(self, values):
        self._values = values
        self.w.blockSignals(True)
        self.w.setText(decode_ascii(values, self.start, self.length))
        self.w.blockSignals(False)

    def _write(self):
        new = encode_ascii(self.w.text(), self.length)
        seg = slice(self.start, self.start + self.length)
        if new != self._values[seg]:
            self._values[seg] = new
            self._emit_dirty()


class NameField(StringField):
    """16-char ASCII name at values[0:16]."""

    def __init__(self, label="Name"):
        super().__init__(0, NAME_LEN, label)


class NickField(StringField):
    """8-char ASCII nick name at values[16:24]."""

    def __init__(self, label="Nick name"):
        super().__init__(16, 8, label)


class IntField(Field):
    """A single byte value at `offset`, as a spin box."""

    def __init__(self, offset: int, label: str, lo=0, hi=255, plus_one=False, invert=None,
                 low_nibble=False):
        super().__init__()
        self.offset, self.label, self.lo, self.hi, self.plus_one = offset, label, lo, hi, plus_one
        # When `invert` is set, the device stores (invert - displayed); e.g. exp-pedal Max CC
        # sweep stores 127 - shown value. Mutually exclusive with plus_one.
        self.invert = invert
        # When `low_nibble`, only the low 4 bits of the byte are this field; the high nibble is a
        # separate field (e.g. exp-pedal Chan shares its byte with the expression command).
        self.low_nibble = low_nibble

    def build(self):
        self.w = QSpinBox()
        # `lo`/`hi` describe stored values. A plus-one field must expose the correspondingly
        # shifted display range or QSpinBox clamps raw 15 + 1 back to 15 (the Global MIDI-channel
        # bug) and can write the wrong byte back.
        display_offset = 1 if self.plus_one else 0
        self.w.setRange(self.lo + display_offset, self.hi + display_offset)
        self.w.valueChanged.connect(self._write)
        return self.w

    def _to_display(self, raw):
        if self.invert is not None:
            return self.invert - raw
        return raw + (1 if self.plus_one else 0)

    def _to_raw(self, val):
        if self.invert is not None:
            return self.invert - val
        return val - (1 if self.plus_one else 0)

    def load(self, values):
        self._values = values
        stored = values[self.offset] & 0x0F if self.low_nibble else values[self.offset]
        self.w.blockSignals(True)
        self.w.setValue(self._to_display(stored))
        self.w.blockSignals(False)

    def _write(self, val):
        if not (0 <= self.offset < len(self._values)):
            return
        raw = self._to_raw(val)
        if self.low_nibble:
            raw = (self._values[self.offset] & 0xF0) | (raw & 0x0F)
        if self._values[self.offset] != raw:
            self._values[self.offset] = raw & 0xFF
            self._emit_dirty()


class Int16Field(Field):
    """A 2-byte little-endian value at `offset` (low) / `offset+1` (high), as a spin box.
    The device stores (displayed - plus_one); e.g. per-channel Max Pre shows (low + high*256)+1.
    """

    def __init__(self, offset: int, label: str, lo=0, hi=65535, plus_one=0):
        super().__init__()
        self.offset, self.label, self.lo, self.hi, self.plus_one = offset, label, lo, hi, plus_one

    def build(self):
        self.w = QSpinBox()
        self.w.setRange(self.lo, self.hi)
        self.w.valueChanged.connect(self._write)
        return self.w

    def load(self, values):
        self._values = values
        stored = values[self.offset] | (values[self.offset + 1] << 8)
        self.w.blockSignals(True)
        self.w.setValue(stored + self.plus_one)
        self.w.blockSignals(False)

    def _write(self, val):
        if not (0 <= self.offset + 1 < len(self._values)):
            return
        raw = val - self.plus_one
        lo, hi = raw & 0xFF, (raw >> 8) & 0xFF
        if self._values[self.offset] != lo or self._values[self.offset + 1] != hi:
            self._values[self.offset] = lo
            self._values[self.offset + 1] = hi
            self._emit_dirty()


class FlagField(Field):
    """A single bit (`bitmask`) of the byte at `offset`, as a checkbox."""

    def __init__(self, offset: int, bitmask: int, label: str):
        super().__init__()
        self.offset, self.bitmask, self.label = offset, bitmask, label

    def build(self):
        self.w = QCheckBox()
        self.w.toggled.connect(self._write)
        return self.w

    def load(self, values):
        self._values = values
        self.w.blockSignals(True)
        self.w.setChecked(bool(values[self.offset] & self.bitmask))
        self.w.blockSignals(False)

    def _write(self, on):
        cur = self._values[self.offset]
        new = (cur | self.bitmask) if on else (cur & ~self.bitmask & 0xFF)
        if new != cur:
            self._values[self.offset] = new
            self._emit_dirty()


class EnumField(Field):
    """The byte at `offset` constrained to a {value: label} mapping, as a combo box.

    `nibble` optionally restricts editing to one 4-bit half of the byte ("low" or "high"),
    preserving the other nibble — used for the page preset-button colours, which pack the
    selected colour in the low nibble and the not-selected colour in the high nibble."""

    def __init__(self, offset: int, label: str, options: dict[int, str], nibble: str | None = None):
        super().__init__()
        self.offset, self.label, self.options = offset, label, options
        assert nibble in (None, "low", "high")
        self.nibble = nibble

    def _get(self, raw):
        if self.nibble == "low":
            return raw & 0x0F
        if self.nibble == "high":
            return (raw >> 4) & 0x0F
        return raw

    def _put(self, raw, val):
        if self.nibble == "low":
            return (raw & 0xF0) | (val & 0x0F)
        if self.nibble == "high":
            return (raw & 0x0F) | ((val & 0x0F) << 4)
        return val & 0xFF

    def build(self):
        self.w = QComboBox()
        for val, name in self.options.items():
            self.w.addItem(name, val)
        self.w.currentIndexChanged.connect(self._write)
        return self.w

    def load(self, values):
        self._values = values
        v = self._get(values[self.offset])
        idx = self.w.findData(v)
        self.w.blockSignals(True)
        self.w.setCurrentIndex(idx if idx >= 0 else -1)
        self.w.blockSignals(False)

    def _write(self, _idx):
        val = self.w.currentData()
        if val is None:
            return
        new = self._put(self._values[self.offset], val)
        if self._values[self.offset] != new:
            self._values[self.offset] = new
            self._emit_dirty()


class MidiTableField(Field):
    """An editable table of `count` MIDI messages starting at byte `start` (3 bytes each:
    status, data1, data2). Columns: Cmd, Ch, Data1, Data2. Empty rows have status 0."""

    def __init__(self, start: int, count: int, label: str):
        super().__init__()
        self.start, self.count, self.label = start, count, label

    def build(self):
        from PySide6.QtWidgets import QTableWidget, QComboBox, QSpinBox, QHeaderView
        from ..model.midi import MIDI_CMDS
        self._MIDI_CMDS = MIDI_CMDS
        self.w = QTableWidget(self.count, 4)
        self.w.setHorizontalHeaderLabels(["Cmd", "Ch", "Data1", "Data2"])
        self.w.verticalHeader().setDefaultSectionSize(22)
        self.w.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.combos, self.chans, self.d1s, self.d2s = [], [], [], []
        for r in range(self.count):
            combo = QComboBox()
            for code, name in MIDI_CMDS.items():
                combo.addItem(name, code)
            combo.currentIndexChanged.connect(lambda _i, row=r: self._write_status(row))
            ch = QSpinBox(); ch.setRange(1, 16)
            ch.valueChanged.connect(lambda _v, row=r: self._write_status(row))
            d1 = QSpinBox(); d1.setRange(0, 127)
            d1.valueChanged.connect(lambda v, row=r: self._write_data(row, 1, v))
            d2 = QSpinBox(); d2.setRange(0, 127)
            d2.valueChanged.connect(lambda v, row=r: self._write_data(row, 2, v))
            self.w.setCellWidget(r, 0, combo)
            self.w.setCellWidget(r, 1, ch)
            self.w.setCellWidget(r, 2, d1)
            self.w.setCellWidget(r, 3, d2)
            self.combos.append(combo); self.chans.append(ch)
            self.d1s.append(d1); self.d2s.append(d2)
        return self.w

    def load(self, values):
        self._values = values
        self._loading = True
        for r in range(self.count):
            off = self.start + r * 3
            status, d1, d2 = values[off], values[off + 1], values[off + 2]
            code = status & 0xF0
            idx = self.combos[r].findData(code)
            self.combos[r].setCurrentIndex(idx if idx >= 0 else 0)
            self.chans[r].setValue((status & 0x0F) + 1)
            self.d1s[r].setValue(d1)
            self.d2s[r].setValue(d2)
        self._loading = False

    def _write_status(self, row):
        if getattr(self, "_loading", False):
            return
        off = self.start + row * 3
        code = self.combos[row].currentData() or 0
        ch = self.chans[row].value() - 1
        new = (code | ch) if code else 0
        if new != self._values[off]:
            self._values[off] = new
            self._emit_dirty()

    def _write_data(self, row, which, val):
        if getattr(self, "_loading", False):
            return
        off = self.start + row * 3 + which
        if val != self._values[off]:
            self._values[off] = val & 0xFF
            self._emit_dirty()


class PresetCmdTableField(Field):
    """Preset 'Command Programming' table: `count` entries × 4 bytes [func, b1, b2, b3].

    The Function column is a combo of known command codes (unknown codes shown as 'Fn N').
    For a MIDI Command row, b1/b2/b3 are the raw MIDI status/data1/data2; for IA-trigger
    rows, b1 is the trigger value. All three bytes are exposed as editable spin boxes
    (lossless), labelled generically since their meaning depends on the function."""

    def __init__(self, start: int, count: int, label: str, funcs: dict[int, str]):
        super().__init__()
        self.start, self.count, self.label, self.funcs = start, count, label, funcs

    def build(self):
        from PySide6.QtWidgets import (
            QTableWidget, QTableWidgetItem, QComboBox, QSpinBox, QHeaderView,
        )
        from PySide6.QtCore import Qt
        self.w = QTableWidget(self.count, 5)
        self.w.setHorizontalHeaderLabels(["Function", "B1", "B2", "B3", "Decoded"])
        self.w.verticalHeader().setDefaultSectionSize(22)
        self.w.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.w.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.combos, self.b1s, self.b2s, self.b3s, self.decoded = [], [], [], [], []
        for r in range(self.count):
            combo = QComboBox()
            for code, name in self.funcs.items():
                combo.addItem(name, code)
            combo.currentIndexChanged.connect(lambda _i, row=r: self._write_func(row))
            for col, store in ((1, self.b1s), (2, self.b2s), (3, self.b3s)):
                sp = QSpinBox(); sp.setRange(0, 255)
                sp.valueChanged.connect(lambda v, row=r, c=col: self._write_byte(row, c, v))
                self.w.setCellWidget(r, col, sp)
                store.append(sp)
            self.w.setCellWidget(r, 0, combo)
            self.combos.append(combo)
            item = QTableWidgetItem("")
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # read-only interpretation
            self.w.setItem(r, 4, item)
            self.decoded.append(item)
        return self.w

    def _refresh_decoded(self, row):
        from ..model.preset import decode_command
        off = self.start + row * 4
        v = self._values
        self.decoded[row].setText(decode_command(v[off], v[off + 1], v[off + 2], v[off + 3]))

    def _ensure_code(self, combo, code):
        if combo.findData(code) < 0:
            combo.addItem(f"Fn {code}", code)

    def load(self, values):
        self._values = values
        self._loading = True
        for r in range(self.count):
            off = self.start + r * 4
            func, b1, b2, b3 = values[off], values[off + 1], values[off + 2], values[off + 3]
            self._ensure_code(self.combos[r], func)
            self.combos[r].setCurrentIndex(self.combos[r].findData(func))
            self.b1s[r].setValue(b1)
            self.b2s[r].setValue(b2)
            self.b3s[r].setValue(b3)
            self._refresh_decoded(r)
        self._loading = False

    def _write_func(self, row):
        if getattr(self, "_loading", False):
            return
        off = self.start + row * 4
        code = self.combos[row].currentData()
        if code is not None and code != self._values[off]:
            self._values[off] = code & 0xFF
            self._refresh_decoded(row)
            self._emit_dirty()

    def _write_byte(self, row, col, val):
        if getattr(self, "_loading", False):
            return
        off = self.start + row * 4 + col
        if val != self._values[off]:
            self._values[off] = val & 0xFF
            self._refresh_decoded(row)
            self._emit_dirty()


class BitGridField(Field):
    """A bitfield starting at byte `start` spanning `count` bits, shown as a grid of
    checkable slot cells (1-based labels). Used for a preset's initial IA-slot ON states."""

    def __init__(self, start: int, count: int, label: str, cols=10):
        super().__init__()
        self.start, self.count, self.label, self.cols = start, count, label, cols

    def build(self):
        from PySide6.QtWidgets import QCheckBox
        self.w, grid = _grid_host()
        self.boxes: list[QCheckBox] = []
        for i in range(self.count):
            cb = QCheckBox(str(i + 1))
            cb.toggled.connect(lambda on, idx=i: self._write(idx, on))
            r, c = divmod(i, self.cols)
            grid.addWidget(cb, r, c)
            self.boxes.append(cb)
        return self.w

    def load(self, values):
        self._values = values
        for i, cb in enumerate(self.boxes):
            byte, bit = divmod(i, 8)
            cb.blockSignals(True)
            cb.setChecked(bool(values[self.start + byte] & (1 << bit)))
            cb.blockSignals(False)

    def _write(self, idx, on):
        byte, bit = divmod(idx, 8)
        off = self.start + byte
        cur = self._values[off]
        new = (cur | (1 << bit)) if on else (cur & ~(1 << bit) & 0xFF)
        if new != cur:
            self._values[off] = new
            self._emit_dirty()


class ByteGridField(Field):
    """A grid of `count` byte values starting at `start`, each an editable spin box.
    Used for the IA-Map's 60 button→slot cells (display 1-based, store 0-based)."""

    def __init__(self, start: int, count: int, label: str, lo=0, hi=255, plus_one=True, cols=10):
        super().__init__()
        self.start, self.count, self.label = start, count, label
        self.lo, self.hi, self.plus_one, self.cols = lo, hi, plus_one, cols

    def build(self):
        self.w, grid = _grid_host()
        self.spins = []
        off = 1 if self.plus_one else 0
        for i in range(self.count):
            sp = QSpinBox(); sp.setRange(self.lo + off, self.hi + off)
            sp.setPrefix(f"{i + 1}: ")
            sp.valueChanged.connect(lambda v, idx=i: self._write(idx, v))
            r, c = divmod(i, self.cols)
            grid.addWidget(sp, r, c)
            self.spins.append(sp)
        return self.w

    def load(self, values):
        self._values = values
        off = 1 if self.plus_one else 0
        for i, sp in enumerate(self.spins):
            sp.blockSignals(True)
            sp.setValue(values[self.start + i] + off)
            sp.blockSignals(False)

    def _write(self, idx, val):
        off = 1 if self.plus_one else 0
        raw = val - off
        if self._values[self.start + idx] != raw:
            self._values[self.start + idx] = raw & 0xFF
            self._emit_dirty()


class Int16GridField(Field):
    """A grid of `count` little-endian 2-byte values from `start` (stride 2), each a spin box.

    Display = stored + `plus_one`. A stored value of `unused_raw` (e.g. 0xFFFF) shows and writes
    back as `unused_display` (e.g. 0) — used for a Song's 24 preset slots, where 0xFFFF == unused
    and a real slot holds (preset-1)."""

    def __init__(self, start: int, count: int, label: str, lo=0, hi=65535, plus_one=0,
                 unused_raw=None, unused_display=0, cols=6):
        super().__init__()
        self.start, self.count, self.label = start, count, label
        self.lo, self.hi, self.plus_one = lo, hi, plus_one
        self.unused_raw, self.unused_display, self.cols = unused_raw, unused_display, cols

    def build(self):
        self.w, grid = _grid_host()
        self.spins = []
        for i in range(self.count):
            sp = QSpinBox(); sp.setRange(self.lo, self.hi)
            sp.setPrefix(f"{i + 1}: ")
            sp.valueChanged.connect(lambda v, idx=i: self._write(idx, v))
            r, c = divmod(i, self.cols)
            grid.addWidget(sp, r, c)
            self.spins.append(sp)
        return self.w

    def load(self, values):
        self._values = values
        for i, sp in enumerate(self.spins):
            off = self.start + 2 * i
            stored = values[off] | (values[off + 1] << 8)
            disp = self.unused_display if stored == self.unused_raw else stored + self.plus_one
            sp.blockSignals(True); sp.setValue(disp); sp.blockSignals(False)

    def _write(self, idx, val):
        off = self.start + 2 * idx
        if self.unused_raw is not None and val == self.unused_display:
            raw = self.unused_raw
        else:
            raw = val - self.plus_one
        lo, hi = raw & 0xFF, (raw >> 8) & 0xFF
        if self._values[off] != lo or self._values[off + 1] != hi:
            self._values[off] = lo
            self._values[off + 1] = hi
            self._emit_dirty()


class SlotPickerField(Field):
    """A grid of `count` slots, each a combo box that picks a target record (preset or song)
    *by name*. The stored value is the 0-based record index; the combo lists every record in
    the dump as "NNN: Name" plus an optional "(unused)" entry.

    Storage is `width` bytes little-endian (1 = song slot, 2 = song's preset slot). When
    `unused_raw` is set, that stored value (e.g. 0xFFFF) maps to the "(unused)" entry. The
    names come from the dump via set_context, so the picker always reflects the live rig."""

    def __init__(self, start: int, count: int, label: str, target_type: int, *, width=1,
                 unused_raw=None, unused_label="(unused)", cols=4):
        super().__init__()
        self.start, self.count, self.label = start, count, label
        self.target_type, self.width = target_type, width
        self.unused_raw, self.unused_label, self.cols = unused_raw, unused_label, cols
        self._items: list[tuple[int | None, str]] = []  # (stored_index_or_None, display)

    def build(self):
        self.w, grid = _grid_host()
        self.combos: list[QComboBox] = []
        for i in range(self.count):
            cb = _DropCombo(self.target_type, lambda num, idx=i: self._assign(idx, num))
            cb.setMinimumContentsLength(18)
            cb.currentIndexChanged.connect(lambda _ix, idx=i: self._write(idx))
            r, c = divmod(i, self.cols)
            grid.addWidget(QLabel(f"{i + 1}:"), r, c * 2)
            grid.addWidget(cb, r, c * 2 + 1)
            self.combos.append(cb)
        return self.w

    def set_context(self, dump) -> None:
        # Build the option list once: every target record by name, plus optional "(unused)".
        items: list[tuple[int | None, str]] = []
        if self.unused_raw is not None:
            items.append((None, self.unused_label))
        for n, rec in enumerate(dump.records(self.target_type)):
            name = (getattr(rec, "name", "") or "").strip() or "(no name)"
            items.append((n, f"{n + 1:03d}: {name}"))
        self._items = items
        texts = [text for _idx, text in items]
        for cb in getattr(self, "combos", []):
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(texts)   # one batched call — per-item addItem is pathologically slow on Win
            cb.blockSignals(False)

    def _stored(self, values, off):
        if self.width == 2:
            return values[off] | (values[off + 1] << 8)
        return values[off]

    def _put(self, values, off, raw):
        values[off] = raw & 0xFF
        if self.width == 2:
            values[off + 1] = (raw >> 8) & 0xFF

    def load(self, values):
        self._values = values
        for i, cb in enumerate(self.combos):
            stored = self._stored(values, self.start + self.width * i)
            target = None if stored == self.unused_raw else stored
            pos = next((p for p, (idx, _t) in enumerate(self._items) if idx == target), 0)
            cb.blockSignals(True)
            cb.setCurrentIndex(pos)
            cb.blockSignals(False)

    def _write(self, idx):
        if not self._items:
            return
        pos = self.combos[idx].currentIndex()
        if not (0 <= pos < len(self._items)):
            return
        target = self._items[pos][0]
        raw = self.unused_raw if target is None else target
        off = self.start + self.width * idx
        if self._stored(self._values, off) != raw:
            self._put(self._values, off, raw)
            self._emit_dirty()

    def _assign(self, slot_idx: int, number: int) -> None:
        """Drag-drop: assign record `number` (1-based) to slot `slot_idx` by selecting its combo
        entry (the index write path keeps everything lossless)."""
        raw = number - 1
        pos = next((p for p, (idx, _t) in enumerate(self._items) if idx == raw), None)
        if pos is not None:
            self.combos[slot_idx].setCurrentIndex(pos)


class HexBytesField(Field):
    """The original's Sysex "Message Data" grid: `count` bytes from `start` shown as one row of
    `cols` cells, each a `&hNN` hex entry with read-only HEX and DEC value labels (blue) below."""

    def __init__(self, start: int, count: int, label: str, cols=16):
        super().__init__()
        self.start, self.count, self.label, self.cols = start, count, label, cols

    def build(self):
        self.w = QWidget()
        grid = QGridLayout(self.w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(2)
        self.spins: list[QSpinBox] = []
        self.hexes: list[QLabel] = []
        self.decs: list[QLabel] = []
        blue = "color:#5aa9e6; font-family:Menlo,monospace;"
        for i in range(self.count):
            sp = QSpinBox()
            sp.setRange(0, 255)
            sp.setDisplayIntegerBase(16)
            sp.setPrefix("&h")
            sp.setButtonSymbols(QSpinBox.NoButtons)
            sp.setFixedWidth(52)
            sp.valueChanged.connect(lambda v, idx=i: self._write(idx, v))
            r, c = divmod(i, self.cols)
            num = QLabel(str(i + 1)); num.setObjectName("sectionNote")
            grid.addWidget(num, r * 4, c, alignment=Qt.AlignCenter)
            grid.addWidget(sp, r * 4 + 1, c)
            hx = QLabel("0"); hx.setStyleSheet(blue); hx.setAlignment(Qt.AlignCenter)
            dc = QLabel("0"); dc.setStyleSheet(blue); dc.setAlignment(Qt.AlignCenter)
            grid.addWidget(hx, r * 4 + 2, c, alignment=Qt.AlignCenter)
            grid.addWidget(dc, r * 4 + 3, c, alignment=Qt.AlignCenter)
            self.spins.append(sp); self.hexes.append(hx); self.decs.append(dc)
        return self.w

    def load(self, values):
        self._values = values
        for i, sp in enumerate(self.spins):
            v = values[self.start + i]
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)
            self._refresh(i, v)

    def _refresh(self, idx, v):
        self.hexes[idx].setText(f"{v:02X}")
        self.decs[idx].setText(str(v))

    def _write(self, idx, val):
        off = self.start + idx
        if self._values[off] != val:
            self._values[off] = val & 0xFF
            self._refresh(idx, val)
            self._emit_dirty()


class ToggleField(Field):
    """A single bit (`bitmask`) of `values[offset]` as a red/green rocker switch with caption
    (the original's LED toggles). `invert` flips the on-sense. The caption is the field label,
    so place it bare (no form label) in a section."""

    def __init__(self, offset: int, bitmask: int, label: str, invert: bool = False):
        super().__init__()
        self.offset, self.bitmask, self.label, self.invert = offset, bitmask, label, invert
        self._caption = label
        self.label = ""  # rendered inside the widget, not as a form label
        self._apply_fn = None

    def build(self):
        from .components import LabeledToggle
        self.w = LabeledToggle(self.offset, self.bitmask, self._caption, self.invert)
        self.w.changed.connect(self._emit_dirty)
        self.w.setContextMenuPolicy(Qt.CustomContextMenu)
        self.w.customContextMenuRequested.connect(self._context_menu)
        return self.w

    def load(self, values):
        self._values = values
        self.w.bind(values)

    def set_multi_apply(self, apply_fn, count_fn, label: str) -> None:
        """Enable right-click 'apply this toggle across many records' (the original's multi-preset
        quick programming). `apply_fn(offset, bitmask, on, lo, hi)`; `count_fn()` -> record count."""
        self._apply_fn, self._count_fn, self._multi_label = apply_fn, count_fn, label

    def _context_menu(self, pos):
        if self._apply_fn is None or not hasattr(self, "_values"):
            return
        from PySide6.QtWidgets import QMenu, QInputDialog
        on = bool(self._values[self.offset] & self.bitmask)
        state = "ON" if on else "OFF"
        n = self._count_fn()
        label = self._multi_label
        menu = QMenu(self.w)
        a_all = menu.addAction(f"Set this {state} for all {n} {label}s")
        a_rng = menu.addAction(f"Set this {state} for a range of {label}s…")
        chosen = menu.exec(self.w.mapToGlobal(pos))
        if chosen is a_all:
            self._apply_fn(self.offset, self.bitmask, on, 1, n)
        elif chosen is a_rng:
            lo, ok = QInputDialog.getInt(self.w, "Apply to range", f"From {label} #", 1, 1, n)
            if not ok:
                return
            hi, ok = QInputDialog.getInt(self.w, "Apply to range", f"To {label} #", n, lo, n)
            if ok:
                self._apply_fn(self.offset, self.bitmask, on, lo, hi)


class IAStateGridField(Field):
    """Preset 'MAP Label / Initial IA-Slot States' — a scrollable list of all 60 IA slots,
    each showing `NN- [###]Name` (name resolved from the dump's IA-switch records) and a green
    On / red Off toggle bound to the preset's initial-IA bitfield at `start` (bit per slot)."""

    def __init__(self, start: int, count: int, label: str):
        super().__init__()
        self.start, self.count, self.label = start, count, label
        self._names: list[str] = []

    def build(self):
        from PySide6.QtWidgets import QTableWidget, QHeaderView, QTableWidgetItem
        from .components import ToggleSwitch
        self.w = QTableWidget(self.count, 2)
        self.w.setHorizontalHeaderLabels(["IA [#] Name", "State"])
        self.w.verticalHeader().setDefaultSectionSize(20)
        self.w.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.w.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.w.setColumnWidth(1, 56)
        self.w.setEditTriggers(QTableWidget.NoEditTriggers)
        self.w.setMinimumHeight(420)   # show ~20 rows of the 60-slot map (rest scroll)
        self._items, self._toggles = [], []
        for i in range(self.count):
            item = QTableWidgetItem(f"{i + 1:02d}- [{i + 1:03d}]")
            self.w.setItem(i, 0, item)
            byte, bit = divmod(i, 8)
            tg = ToggleSwitch(self.start + byte, 1 << bit, f"IA slot {i + 1}")
            tg.changed.connect(self._emit_dirty)
            holder = self._center(tg)
            self.w.setCellWidget(i, 1, holder)
            self._items.append(item)
            self._toggles.append(tg)
        return self.w

    @staticmethod
    def _center(w):
        from PySide6.QtWidgets import QWidget, QHBoxLayout
        host = QWidget(); lay = QHBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0); lay.addStretch(1); lay.addWidget(w); lay.addStretch(1)
        return host

    def set_context(self, dump) -> None:
        self._names = []
        for rec in dump.records(3):  # IA-switch records
            nm = (getattr(rec, "name", "") or "").strip()
            self._names.append(nm)
        for i, item in enumerate(getattr(self, "_items", [])):
            nm = self._names[i] if i < len(self._names) else ""
            item.setText(f"{i + 1:02d}- [{i + 1:03d}]{nm}")

    def load(self, values):
        self._values = values
        for tg in self._toggles:
            tg.bind(values)


class LabelGridField(Field):
    """A grid of fixed-width text labels stored in a *sibling extension record* linked to the
    parent record by `rec_num`: PresetExt9 = IA-Slot Defined Labels (1-10); SongExt11 = Song LCD
    Button Labels (1-12). The parent tab binds to the parent record; this field finds the matching
    extension record in the dump and edits it directly (lossless). Populated via `bind_record`."""

    LABEL_WIDTH = 8

    def __init__(self, ext_type: int, count: int, label: str = "", cols: int = 2):
        super().__init__()
        self.ext_type, self.count, self.label, self.cols = ext_type, count, label, cols
        self._dump = None
        self._ext = None

    def set_context(self, dump) -> None:
        self._dump = dump

    def build(self):
        self.w = QWidget()
        grid = QGridLayout(self.w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        self.edits: list[QLineEdit] = []
        for i in range(self.count):
            e = QLineEdit()
            e.setObjectName("lcd")
            e.setMaxLength(self.LABEL_WIDTH)
            e.setFixedWidth(88)
            e.editingFinished.connect(lambda idx=i: self._write(idx))
            r, c = divmod(i, self.cols)
            lab = QLabel(f"{i + 1}")
            lab.setObjectName("sectionNote")
            grid.addWidget(lab, r, c * 2, Qt.AlignRight)
            grid.addWidget(e, r, c * 2 + 1)
            self.edits.append(e)
        return self.w

    def load(self, values) -> None:
        pass  # this field binds to the sibling record, not the parent values (see bind_record)

    def bind_record(self, rec) -> None:
        self._ext = None
        if self._dump is not None and rec is not None:
            num = rec.frame.rec_num
            self._ext = next((r for r in self._dump.records(self.ext_type)
                              if r.frame.rec_num == num), None)
        for i, e in enumerate(self.edits):
            e.blockSignals(True)
            e.setText(self._ext.label(i) if self._ext else "")
            e.setEnabled(self._ext is not None)
            e.blockSignals(False)

    def _write(self, idx: int) -> None:
        if self._ext is None:
            return
        new = self.edits[idx].text()
        if self._ext.label(idx) != new:
            self._ext.set_label(idx, new)
            self._emit_dirty()


class CommandTableField(Field):
    """The original editor's Command-Programming table — shared by Presets, Songs and the IA-Slot
    On/Bypass panels. Each entry is 4 bytes [func, b1, b2, b3]; columns are
    `Function | MIDI | Cmd | Data 1 | Data 2`. For a MIDI Command row b1 = (type<<4)|channel and
    the MIDI column resolves the channel to its Config#1 device name (e.g. "MR10"); the Cmd column
    is the MIDI message type. For non-MIDI rows (IA triggers etc.) b1 is shown in Data 1. All edits
    write the raw bytes, so re-encoding stays lossless."""

    def __init__(self, start: int, count: int, label: str, funcs: dict[int, str]):
        super().__init__()
        self.start, self.count, self.label, self.funcs = start, count, label, funcs
        self._chan_names = [str(i + 1) for i in range(16)]

    def build(self):
        from PySide6.QtWidgets import QTableWidget, QComboBox, QSpinBox, QHeaderView
        from ..model.preset import FUNC_MIDI, MIDI_MSG_TYPES
        self._FUNC_MIDI = FUNC_MIDI
        DropTable = type("_CmdTableW", (_CmdDropTable, QTableWidget), {})
        self.w = DropTable(self.count, 5)
        self.w._on_drop = self._drop_record
        self.w.setAcceptDrops(True)
        self.w.setHorizontalHeaderLabels(["Function", "MIDI", "Cmd", "CC# / PC#", "Data"])
        self.w.verticalHeader().setVisible(False)
        self.w.verticalHeader().setDefaultSectionSize(24)
        hh = self.w.horizontalHeader()
        hh.setMinimumSectionSize(44)
        hh.setSectionResizeMode(0, QHeaderView.Interactive)   # Function
        hh.setSectionResizeMode(1, QHeaderView.Interactive)   # MIDI device
        hh.setSectionResizeMode(2, QHeaderView.Stretch)       # Cmd (fills wide tables)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.w.setColumnWidth(0, 120)
        self.w.setColumnWidth(1, 78)
        self.w.setMinimumHeight(min(self.count, 12) * 24 + 28)
        self.funcs_c, self.midis, self.cmds, self.d1s, self.d2s = [], [], [], [], []
        for r in range(self.count):
            fc = QComboBox()
            for code, name in self.funcs.items():
                fc.addItem(name, code)
            fc.currentIndexChanged.connect(lambda _i, row=r: self._write_func(row))
            mc = QComboBox()
            for i, nm in enumerate(self._chan_names):
                mc.addItem(nm, i)
            mc.currentIndexChanged.connect(lambda _i, row=r: self._write_status(row))
            cc = QComboBox()
            for code, name in MIDI_MSG_TYPES.items():
                cc.addItem(name, code)
            cc.currentIndexChanged.connect(lambda _i, row=r: self._write_status(row))
            d1 = QSpinBox(); d1.setRange(0, 255)
            d1.valueChanged.connect(lambda v, row=r: self._write_data(row, 1, v))
            d2 = QSpinBox(); d2.setRange(0, 255)
            d2.valueChanged.connect(lambda v, row=r: self._write_data(row, 2, v))
            for col, wdg in ((0, fc), (1, mc), (2, cc), (3, d1), (4, d2)):
                self.w.setCellWidget(r, col, wdg)
            self.funcs_c.append(fc); self.midis.append(mc); self.cmds.append(cc)
            self.d1s.append(d1); self.d2s.append(d2)
        return self.w

    def set_context(self, dump) -> None:
        from ..model.config import channel_names
        names = [f"{ch + 1}: {nm}" if nm else str(ch + 1)
                 for ch, nm in enumerate(channel_names(dump))]
        self._chan_names = names
        for mc in getattr(self, "midis", []):
            mc.blockSignals(True)
            for i, nm in enumerate(names):
                mc.setItemText(i, nm)
            mc.blockSignals(False)

    def _ensure_code(self, combo, code):
        if combo.findData(code) < 0:
            combo.addItem(f"Fn {code}", code)

    def load(self, values):
        self._values = values
        self._loading = True
        for r in range(self.count):
            off = self.start + r * 4
            func, b1, b2, b3 = values[off], values[off + 1], values[off + 2], values[off + 3]
            self._ensure_code(self.funcs_c[r], func)
            self.funcs_c[r].setCurrentIndex(self.funcs_c[r].findData(func))
            is_midi = func == self._FUNC_MIDI
            self.midis[r].setEnabled(is_midi)
            self.cmds[r].setEnabled(is_midi)
            if is_midi:
                mtype, chan = b1 >> 4, b1 & 0x0F
                self.midis[r].setCurrentIndex(chan if chan < self.midis[r].count() else 0)
                ci = self.cmds[r].findData(mtype)
                self.cmds[r].setCurrentIndex(ci if ci >= 0 else 0)
                self.d1s[r].setValue(b2)
                self.d2s[r].setValue(b3)
            else:
                self.midis[r].setCurrentIndex(-1)   # blank channel/cmd for non-MIDI rows
                self.cmds[r].setCurrentIndex(-1)     # (don't show a stray "Note Off")
                self.d1s[r].setValue(b1)   # non-MIDI: Data 1 holds b1 (e.g. IA-slot number)
                self.d2s[r].setValue(b2)
        self._loading = False

    def _write_func(self, row):
        if getattr(self, "_loading", False):
            return
        off = self.start + row * 4
        code = self.funcs_c[row].currentData()
        if code is not None and code != self._values[off]:
            self._values[off] = code & 0xFF
            self._loading = True
            self.load(self._values)   # remap columns for the new function type
            self._loading = False
            self._emit_dirty()

    def _write_status(self, row):
        if getattr(self, "_loading", False):
            return
        off = self.start + row * 4
        mtype = self.cmds[row].currentData()
        chan = self.midis[row].currentData() or 0
        b1 = ((mtype & 0xF) << 4) | (chan & 0xF)
        if b1 != self._values[off + 1]:
            self._values[off + 1] = b1 & 0xFF
            self._emit_dirty()

    def _write_data(self, row, which, val):
        if getattr(self, "_loading", False):
            return
        off = self.start + row * 4
        is_midi = self._values[off] == self._FUNC_MIDI
        target = off + (which + 1) if is_midi else off + which  # MIDI: Data1->b2/Data2->b3; else b1/b2
        if val != self._values[target]:
            self._values[target] = val & 0xFF
            self._emit_dirty()

    # --- drag-drop: an IA-Slot dropped here becomes an "IA ON Trig" command ---
    def _drop_record(self, type_, number, row):
        if type_ != 3:        # only IA-Slots map onto a command
            return
        if not (0 <= row < self.count):
            row = self._first_empty_row()
        self.set_ia_command(row, number)

    def _first_empty_row(self):
        from ..model.preset import FUNC_EMPTY
        for r in range(self.count):
            if self._values[self.start + r * 4] == FUNC_EMPTY:
                return r
        return self.count - 1

    def set_ia_command(self, row: int, slot_number: int) -> None:
        """Set `row` to 'IA ON Trig (map)' for IA-Slot `slot_number` (drag-drop helper)."""
        IA_ON_TRIG = 10
        fc = self.funcs_c[row]
        idx = fc.findData(IA_ON_TRIG)
        if idx < 0:
            return
        fc.setCurrentIndex(idx)             # writes func + reloads (Data1 now holds b1)
        self.d1s[row].setValue(slot_number)  # b1 = IA-slot number


class MMCField(Field):
    """The Sysex tab's "Auto-Create MMC Messages" helper: HR/MN/SEC/FR/FF inputs plus buttons
    that fill the 16 Sysex data bytes with a standard MIDI Machine Control message
    (F0 7F 7F 06 <cmd> F7, or a Locate F0 7F 7F 06 44 06 hr mn sc fr ff F7). `data_field` is the
    HexBytesField over the same bytes, refreshed after a fill."""

    MMC = {"Play": 0x02, "Pause": 0x09, "Stop": 0x01, "Continue": 0x03}

    def __init__(self, data_start: int, data_count: int, data_field=None):
        super().__init__()
        self.data_start, self.data_count, self.data_field = data_start, data_count, data_field
        self.label = ""

    def build(self):
        from PySide6.QtWidgets import QPushButton, QHBoxLayout, QVBoxLayout
        self.w = QWidget()
        v = QVBoxLayout(self.w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(6)
        tc = QHBoxLayout(); self.tc = {}
        for name in ("HR", "MN", "SEC", "FR", "FF"):
            col = QVBoxLayout()
            sp = QSpinBox(); sp.setRange(0, 255); sp.setFixedWidth(56)
            cap = QLabel(name); cap.setObjectName("sectionNote"); cap.setAlignment(Qt.AlignCenter)
            col.addWidget(sp); col.addWidget(cap)
            tc.addLayout(col); self.tc[name] = sp
        loc = QPushButton("Create MMC Locate Message")
        loc.clicked.connect(self._locate)
        tc.addWidget(loc); tc.addStretch(1)
        v.addLayout(tc)
        row = QHBoxLayout()
        for name in ("Play", "Pause", "Stop", "Continue"):
            b = QPushButton(f"Create {name} Msg")
            b.clicked.connect(lambda _c, n=name: self._simple(n))
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        return self.w

    def load(self, values):
        self._values = values

    def _fill(self, msg):
        for i in range(self.data_count):
            self._values[self.data_start + i] = msg[i] if i < len(msg) else 0
        if self.data_field is not None:
            self.data_field.load(self._values)
        self._emit_dirty()

    def _simple(self, name):
        self._fill([0xF0, 0x7F, 0x7F, 0x06, self.MMC[name], 0xF7])

    def _locate(self):
        t = [self.tc[k].value() & 0xFF for k in ("HR", "MN", "SEC", "FR", "FF")]
        self._fill([0xF0, 0x7F, 0x7F, 0x06, 0x44, 0x06, *t, 0xF7])


class ChannelNameField(Field):
    """A MIDI-channel selector that shows each channel's Config#1 device name (e.g. "Whammy1")
    instead of a bare number — the original's exp-pedal "Type Chan" column. Stored in the LOW
    nibble of values[offset]; the high nibble (the expression command) is preserved."""

    def __init__(self, offset: int, label: str):
        super().__init__()
        self.offset, self.label = offset, label
        self._names = [str(i + 1) for i in range(16)]

    def build(self):
        self.w = QComboBox()
        for i, nm in enumerate(self._names):
            self.w.addItem(nm, i)
        self.w.currentIndexChanged.connect(self._write)
        return self.w

    def set_context(self, dump) -> None:
        from ..model.config import channel_names
        self._names = [nm if nm else str(ch + 1)
                       for ch, nm in enumerate(channel_names(dump))]
        if hasattr(self, "w"):
            self.w.blockSignals(True)
            for i, nm in enumerate(self._names):
                self.w.setItemText(i, nm)
            self.w.blockSignals(False)

    def load(self, values):
        self._values = values
        ch = values[self.offset] & 0x0F
        self.w.blockSignals(True)
        self.w.setCurrentIndex(ch)
        self.w.blockSignals(False)

    def _write(self):
        ch = self.w.currentData() or 0
        cur = self._values[self.offset]
        new = (cur & 0xF0) | (ch & 0x0F)
        if new != cur:
            self._values[self.offset] = new
            self._emit_dirty()
