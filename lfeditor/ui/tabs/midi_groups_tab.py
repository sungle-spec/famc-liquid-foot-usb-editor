"""Midi/Groups tab — the original's "Global Group Settings / MIDI Device Settings".

Unlike other tabs this spans BOTH Config records: the 16 channel *names* live in Config #1,
while the per-channel BANK ±1 / send / msb bitfields and 16-bit Max Pre live in Config #0. The
original merges them into one 16-row grid, so we bind directly to both records here.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QSpinBox, QPushButton,
    QScrollArea,
)

from ..components import section as section_panel, RockerSwitch
from ..fields import IntField
from ..theme import GREEN
from ...text import decode_ascii, encode_ascii
from ...model.config import (
    CHAN_BANK_PLUS1_OFF, CHAN_BANK_SEND_OFF, CHAN_BANK_MSB_OFF, CHAN_MAX_PRE_OFF,
    CHAN_MAX_PRE_STRIDE, CHAN_MAX_PRE_PLUS_ONE, NUM_MIDI_CHANNELS, GROUPED_IA_CONFIG_OFF,
    EXCLUSIVE_GROUP_OFF, NUM_EXCLUSIVE_GROUPS,
)

NAME_STRIDE = 8  # channel names: 8 ASCII chars each, at Config#1 value[i*8 : i*8+8]


class MidiGroupsTab(QWidget):
    def __init__(self, on_transfer: Callable[[str, int, int], None] | None = None):
        super().__init__()
        self.type_ = 4
        self._on_transfer = on_transfer
        self._cfg0 = None  # numeric config record
        self._cfg1 = None  # channel-names record
        self._name_edits: list[QLineEdit] = []
        self._maxpre: list[QSpinBox] = []
        self._tg_plus1: list[RockerSwitch] = []
        self._tg_send: list[RockerSwitch] = []
        self._tg_msb: list[RockerSwitch] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 8, 8)
        root.setSpacing(8)

        top = QHBoxLayout()
        ttl = QLabel("Global Group Settings / MIDI Device Settings")
        ttl.setObjectName("tabTitle")
        top.addWidget(ttl)
        top.addStretch(1)
        for text, kind in (("Send Global Settings To LF+", "all_to"),
                           ("Get Settings from LF+", "all_from")):
            b = QPushButton(text)
            b.setObjectName("xfer")
            b.clicked.connect(lambda _c, k=kind: self._transfer(k))
            top.addWidget(b)
        root.addLayout(top)

        cols = QHBoxLayout()
        cols.setSpacing(8)
        cols.setAlignment(Qt.AlignTop)
        cols.addWidget(self._exclusive_panel(), 0)
        cols.addWidget(self._grouped_panel(), 0)
        cols.addWidget(self._channels_panel(), 1)
        host = QWidget(); hv = QVBoxLayout(host); hv.setContentsMargins(0, 0, 0, 0)
        hv.addLayout(cols); hv.addStretch(1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame); scroll.setWidget(host)
        root.addWidget(scroll, 1)

    # --- panels (Exclusive | Grouped | Channels, three columns like the original) ---
    def _exclusive_panel(self) -> QWidget:
        self._excl = [IntField(EXCLUSIVE_GROUP_OFF + i, f"#{i+1}", 0, 180)
                      for i in range(NUM_EXCLUSIVE_GROUPS)]
        eb = QWidget(); ev = QVBoxLayout(eb); ev.setContentsMargins(2, 2, 2, 2)
        for f in self._excl:
            w = f.build(); w.setFixedWidth(150)
            row = QHBoxLayout(); row.addWidget(QLabel(f.label)); row.addWidget(w, 1)
            holder = QWidget(); holder.setLayout(row); ev.addWidget(holder)
        ev.addStretch(1)
        from ..help_text import section_tooltip
        panel = section_panel("Exclusive Group Trigger IA's", eb)
        tip = section_tooltip("Midi/Groups", "Exclusive Group Trigger IA's")
        if tip:
            panel.setToolTip(tip)
        return panel

    def _grouped_panel(self) -> QWidget:
        opts = {0: "Make, then Break", 1: "Break, then Make"}
        gb = QWidget(); gv = QVBoxLayout(gb); gv.setContentsMargins(2, 2, 2, 2)
        self._grp_combos = []
        for i in range(NUM_EXCLUSIVE_GROUPS):
            from PySide6.QtWidgets import QComboBox
            cb = QComboBox()
            for v, name in opts.items():
                cb.addItem(name, v)
            cb.currentIndexChanged.connect(lambda _i, idx=i: self._write_grouped(idx))
            row = QHBoxLayout(); row.addWidget(QLabel(f"#{i+1}")); row.addWidget(cb, 1)
            holder = QWidget(); holder.setLayout(row); gv.addWidget(holder)
            self._grp_combos.append(cb)
        gv.addStretch(1)
        from ..help_text import section_tooltip
        panel = section_panel("Grouped IA config", gb)
        tip = section_tooltip("Midi/Groups", "Grouped IA config")
        if tip:
            panel.setToolTip(tip)
        return panel

    def _channels_panel(self) -> QWidget:
        # Two columns of 8 channels each (1-8 | 9-16), exactly as the original packs them.
        body = QWidget()
        outer = QHBoxLayout(body)
        outer.setContentsMargins(4, 2, 4, 2)
        outer.setSpacing(26)
        outer.addLayout(self._chan_grid(0, 8))
        outer.addLayout(self._chan_grid(8, 16))
        outer.addStretch(1)
        return section_panel("MIDI Channel Device Configuration", body)

    def _chan_grid(self, lo: int, hi: int) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(4)
        # two-line header: "BANK" spans the send/msb columns
        bank = QLabel("BANK"); bank.setObjectName("sectionNote")
        grid.addWidget(bank, 0, 3, 1, 2, alignment=Qt.AlignCenter)
        from ..help_text import tooltip_for
        from .base import apply_tooltip
        for c, h in ((1, "Channel Name"), (2, "+1"), (3, "send"), (4, "msb"), (5, "Max Pre")):
            row = 0 if c in (1, 2, 5) else 1
            lab = QLabel(h); lab.setObjectName("sectionNote")
            tip = tooltip_for("Midi/Groups", h)
            if tip:
                lab.setToolTip(tip)
            grid.addWidget(lab, row, c, alignment=Qt.AlignCenter)
        for ch in range(lo, hi):
            r = ch - lo + 2
            num = QLabel(str(ch + 1)); num.setStyleSheet(f"color:{GREEN};")
            grid.addWidget(num, r, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
            name = QLineEdit(); name.setObjectName("lcd"); name.setFixedWidth(104)
            name.setMaxLength(NAME_STRIDE)
            name.editingFinished.connect(lambda c=ch: self._write_name(c))
            apply_tooltip(name, tooltip_for("Midi/Groups", "Channel Name"))
            grid.addWidget(name, r, 1)
            self._name_edits.append(name)
            t1 = self._bit_toggle(CHAN_BANK_PLUS1_OFF, ch); self._tg_plus1.append(t1)
            ts = self._bit_toggle(CHAN_BANK_SEND_OFF, ch); self._tg_send.append(ts)
            tm = self._bit_toggle(CHAN_BANK_MSB_OFF, ch); self._tg_msb.append(tm)
            apply_tooltip(ts, tooltip_for("Midi/Groups", "send"))
            grid.addWidget(t1, r, 2, alignment=Qt.AlignCenter)
            grid.addWidget(ts, r, 3, alignment=Qt.AlignCenter)
            grid.addWidget(tm, r, 4, alignment=Qt.AlignCenter)
            mp = QSpinBox(); mp.setRange(1, 4096); mp.setFixedWidth(60)
            mp.setButtonSymbols(QSpinBox.NoButtons)
            mp.valueChanged.connect(lambda _v, c=ch: self._write_maxpre(c))
            apply_tooltip(mp, tooltip_for("Midi/Groups", "Max Pre"))
            grid.addWidget(mp, r, 5)
            self._maxpre.append(mp)
        grid.setRowStretch(hi - lo + 2, 1)  # collect slack at the bottom so rows pack at top
        return grid

    def _bit_toggle(self, base_off: int, ch: int) -> RockerSwitch:
        byte, bit = divmod(ch, 8)  # value[base+0]=ch1-8, value[base+1]=ch9-16
        tg = RockerSwitch(base_off + byte, 1 << bit, f"channel {ch + 1}")
        tg.changed.connect(self._mark)
        return tg

    # --- data binding ---
    def set_dump(self, dump) -> None:
        recs = dump.records(self.type_)
        if len(recs) < 2:
            return
        self._cfg0, self._cfg1 = recs[0], recs[1]
        v0, v1 = self._cfg0.values, self._cfg1.values
        for f in self._excl:
            f.set_on_change(self._mark); f.load(v0)
        for i, cb in enumerate(self._grp_combos):
            on = bool(v0[GROUPED_IA_CONFIG_OFF] & (1 << (i + 1)))
            cb.blockSignals(True); cb.setCurrentIndex(1 if on else 0); cb.blockSignals(False)
        for ch in range(NUM_MIDI_CHANNELS):
            nm = decode_ascii(v1, ch * NAME_STRIDE, NAME_STRIDE)
            e = self._name_edits[ch]
            e.blockSignals(True); e.setText(nm); e.blockSignals(False)
            for tg in (self._tg_plus1[ch], self._tg_send[ch], self._tg_msb[ch]):
                tg.bind(v0)
            stored = v0[CHAN_MAX_PRE_OFF + CHAN_MAX_PRE_STRIDE * ch] | \
                (v0[CHAN_MAX_PRE_OFF + CHAN_MAX_PRE_STRIDE * ch + 1] << 8)
            sp = self._maxpre[ch]
            sp.blockSignals(True); sp.setValue(stored + CHAN_MAX_PRE_PLUS_ONE); sp.blockSignals(False)

    def set_raw_visible(self, on: bool):
        pass

    def _write_name(self, ch: int):
        if self._cfg1 is None:
            return
        new = encode_ascii(self._name_edits[ch].text(), NAME_STRIDE)
        off = ch * NAME_STRIDE
        if new != self._cfg1.values[off:off + NAME_STRIDE]:
            self._cfg1.values[off:off + NAME_STRIDE] = new
            self._mark()

    def _write_maxpre(self, ch: int):
        if self._cfg0 is None:
            return
        raw = self._maxpre[ch].value() - CHAN_MAX_PRE_PLUS_ONE
        off = CHAN_MAX_PRE_OFF + CHAN_MAX_PRE_STRIDE * ch
        if self._cfg0.values[off] != (raw & 0xFF) or self._cfg0.values[off + 1] != ((raw >> 8) & 0xFF):
            self._cfg0.values[off] = raw & 0xFF
            self._cfg0.values[off + 1] = (raw >> 8) & 0xFF
            self._mark()

    def _write_grouped(self, idx: int):
        if self._cfg0 is None:
            return
        on = self._grp_combos[idx].currentIndex() == 1
        mask = 1 << (idx + 1)
        cur = self._cfg0.values[GROUPED_IA_CONFIG_OFF]
        new = (cur | mask) if on else (cur & ~mask & 0xFF)
        if new != cur:
            self._cfg0.values[GROUPED_IA_CONFIG_OFF] = new
            self._mark()

    def _mark(self):
        self.window().mark_dirty()

    def _transfer(self, kind: str):
        if self._on_transfer:
            self._on_transfer(kind, self.type_, 0)
