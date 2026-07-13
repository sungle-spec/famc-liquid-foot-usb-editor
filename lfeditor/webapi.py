"""Thin, Qt-free API the web frontend drives under Pyodide.

Holds the open document and exposes byte-level get/set plus name resolution, so the JavaScript UI
never has to know the sysex format — it just reads the schema (`lfeditor.schema`) and calls these
helpers. All edits mutate a frame's decoded `values`, so `save()` re-encodes byte-exact, exactly
like the desktop editor.
"""
from __future__ import annotations

from .codec import Dump
from .text import decode_ascii, encode_ascii


class Session:
    """One open .syx document for the web editor."""

    def __init__(self):
        self.dump: Dump | None = None
        self.dirty = False

    # ---- document ----
    def load(self, data) -> dict:
        self.dump = Dump.from_bytes(bytes(data))
        self.dirty = False
        return self.counts()

    def save(self) -> bytes:
        return self.dump.to_bytes() if self.dump else b""

    def counts(self) -> dict:
        return dict(self.dump.counts()) if self.dump else {}

    # ---- frames of a record type, in file order ----
    def _frames(self, type_: int):
        return [f for f in self.dump.frames if f.type == type_]

    def count(self, type_: int) -> int:
        return len(self._frames(type_)) if self.dump else 0

    def _values(self, type_: int, idx: int):
        frames = self._frames(type_)
        if 0 <= idx < len(frames):
            return frames[idx].values
        return None

    # ---- scalar byte access (the generic field renderers use these) ----
    def get(self, type_: int, idx: int, off: int) -> int:
        v = self._values(type_, idx)
        return v[off] if v is not None and 0 <= off < len(v) else 0

    def set(self, type_: int, idx: int, off: int, val: int) -> None:
        v = self._values(type_, idx)
        if v is not None and 0 <= off < len(v) and v[off] != (val & 0xFF):
            v[off] = val & 0xFF
            self.dirty = True

    # ---- fixed-width ASCII strings (name/nick/labels) ----
    def get_str(self, type_: int, idx: int, off: int, length: int) -> str:
        v = self._values(type_, idx)
        return decode_ascii(v, off, length) if v is not None else ""

    def set_str(self, type_: int, idx: int, off: int, length: int, text: str) -> None:
        v = self._values(type_, idx)
        if v is None:
            return
        new = encode_ascii(text, length)
        if v[off:off + length] != new:
            v[off:off + length] = new
            self.dirty = True

    # ---- name lists for pickers / record rails (e.g. "012: Lead Tone") ----
    def names(self, type_: int, name_off: int = 0, name_len: int = 16) -> list:
        out = []
        for n, f in enumerate(self._frames(type_)):
            nm = decode_ascii(f.values, name_off, name_len).strip() or "(no name)"
            out.append(f"{n + 1:03d}: {nm}")
        return out

    def raw_names(self, type_: int, name_off: int = 0, name_len: int = 16) -> list:
        """Just the stripped names (no "NNN: " prefix) — for the IA-state grid's `NN- [###]Name`."""
        return [decode_ascii(f.values, name_off, name_len).strip() for f in self._frames(type_)]

    # ---- command table (mirrors ui/fields.py::CommandTableField, so the web table is 1:1) ----
    def channel_names(self) -> list:
        """The 16 MIDI channels as the command table's MIDI column shows them: "N: Device" (or "N")."""
        from .model.config import channel_names
        return [f"{ch + 1}: {nm}" if nm else str(ch + 1)
                for ch, nm in enumerate(channel_names(self.dump))]

    def midi_msg_types(self) -> dict:
        from .model.preset import MIDI_MSG_TYPES
        return {str(k): v for k, v in MIDI_MSG_TYPES.items()}

    def func_midi(self) -> int:
        from .model.preset import FUNC_MIDI
        return FUNC_MIDI

    def decode_command(self, func: int, b1: int, b2: int, b3: int) -> str:
        from .model.preset import decode_command
        return decode_command(func, b1, b2, b3)

    # ---- label grids stored in a sibling extension record (PresetExt9/10, SongExt11) ----
    def _frame(self, type_: int, idx: int):
        fr = self._frames(type_)
        return fr[idx] if 0 <= idx < len(fr) else None

    def _ext_frame(self, parent_type: int, parent_idx: int, ext_type: int):
        p = self._frame(parent_type, parent_idx)
        if p is None:
            return None
        return next((f for f in self._frames(ext_type) if f.rec_num == p.rec_num), None)

    def ext_label(self, parent_type: int, parent_idx: int, ext_type: int, i: int, width: int = 8) -> str:
        ext = self._ext_frame(parent_type, parent_idx, ext_type)
        return decode_ascii(ext.values, i * width, width) if ext is not None else ""

    def set_ext_label(self, parent_type: int, parent_idx: int, ext_type: int, i: int, text: str,
                      width: int = 8) -> bool:
        ext = self._ext_frame(parent_type, parent_idx, ext_type)
        if ext is None:
            return False
        new = encode_ascii(text, width)
        seg = slice(i * width, i * width + width)
        if ext.values[seg] != new:
            ext.values[seg] = new
            self.dirty = True
        return True

    # ---- Pages: decode a button-function byte to its display name ----
    def decode_button(self, byte: int) -> str:
        from .model.page import decode_button_function
        return decode_button_function(byte)

    # ---- whole-record copy / paste / clear (reuses ui-free record_ops) ----
    def _record(self, type_: int, idx: int):
        recs = self.dump.records(type_) if self.dump else []
        return recs[idx] if 0 <= idx < len(recs) else None

    def copy_record(self, type_: int, idx: int) -> bool:
        from .ui import record_ops
        rec = self._record(type_, idx)
        if rec is None:
            return False
        self._clip = record_ops.snapshot(self.dump, rec, type_)
        return True

    def can_paste(self, type_: int, idx: int) -> bool:
        from .ui import record_ops
        return record_ops.can_paste(getattr(self, "_clip", None), self._record(type_, idx), type_)

    def paste_record(self, type_: int, idx: int) -> bool:
        from .ui import record_ops
        rec = self._record(type_, idx)
        ok = rec is not None and record_ops.apply_paste(self.dump, rec, type_, getattr(self, "_clip", None))
        if ok:
            self.dirty = True
        return bool(ok)

    def clear_record(self, type_: int, idx: int) -> bool:
        from .ui import record_ops
        rec = self._record(type_, idx)
        if rec is None:
            return False
        record_ops.reset_record(self.dump, rec, type_)
        self.dirty = True
        return True

    def clear_labels(self, ext_type: int) -> int:
        n = 0
        for f in self._frames(ext_type):
            for i in range(len(f.values)):
                f.values[i] = 0
            n += 1
        if n:
            self.dirty = True
        return n

    def multi_apply(self, type_: int, offset: int, bitmask: int, on: bool, lo: int, hi: int) -> int:
        """Set/clear one flag bit across every record whose 1-based number is in [lo, hi]."""
        changed = 0
        for rec in self.dump.records(type_):
            if lo <= rec.number <= hi and offset < len(rec.values):
                v = rec.values[offset]
                nv = (v | bitmask) if on else (v & ~bitmask & 0xFF)
                if nv != v:
                    rec.values[offset] = nv
                    changed += 1
        if changed:
            self.dirty = True
        return changed

    # ---- raw byte view ----
    def raw_bytes(self, type_: int, idx: int) -> list:
        v = self._values(type_, idx)
        return list(v) if v is not None else []

    # ---- search / find ----
    def find(self, text: str = "", types=None, num_min: int = 1, num_max: int = 99999,
             channel=None, msgtype=None, number=None, first_only: bool = False) -> list:
        from . import search
        ms = search.search(self.dump, text=text, types=types, num_min=num_min, num_max=num_max,
                            channel=channel, msgtype=msgtype, number=number, first_only=first_only)
        return [{"type": m.type_, "type_name": m.type_name, "number": m.number,
                 "name": m.name, "where": m.where, "detail": m.detail} for m in ms]

    def find_csv(self, text: str = "", types=None, num_min: int = 1, num_max: int = 99999,
                 channel=None, msgtype=None, number=None, first_only: bool = False) -> str:
        """The Find results as CSV — same format as the desktop's 'Export results (CSV)…'."""
        from . import search
        ms = search.search(self.dump, text=text, types=types, num_min=num_min, num_max=num_max,
                            channel=channel, msgtype=msgtype, number=number, first_only=first_only)
        return search.results_csv(ms)

    # ---- CSV import / export + reports (reuses ui-free csvio) ----
    def export_text(self, kind: str) -> str:
        from . import csvio
        return csvio.export_text(self.dump, kind)

    def import_text(self, kind: str, text: str) -> dict:
        from . import csvio
        applied, warnings = csvio.import_text(self.dump, kind, text)
        if applied:
            self.dirty = True
        return {"applied": applied, "warnings": warnings}

    def report_text(self, kind: str) -> str:
        from . import csvio
        return csvio.report_text(self.dump, kind)

    # ---- Quick Repeated Command Programmer ----
    def quick_apply(self, area: str, row: int, lo: int, hi: int, command, pc_increment: bool = False) -> int:
        from . import quickprog
        n = quickprog.apply_command(self.dump, area, row, lo, hi, list(command), pc_increment)
        if n:
            self.dirty = True
        return n

    # ---- Re-order Records ----
    def move_record(self, type_: int, src_num: int, dst_num: int, sync_refs: bool = True) -> dict:
        from . import reorder
        res = reorder.move_record(self.dump, type_, src_num, dst_num, sync_refs)
        self.dirty = True
        return dict(res) if isinstance(res, dict) else {}

    # ---- WebSerial device bridge --------------------------------------------------------------
    # The browser can't drive blocking serial I/O under Pyodide, so the JS side (web/serial.js)
    # does the async navigator.serial reads/writes while these helpers keep every *byte* of the
    # protocol in Python (comms/protocol.py), the single hardware-confirmed source of truth.
    def dev_handshake(self) -> bytes:
        from .comms.protocol import handshake_frame
        return handshake_frame()

    def dev_session(self) -> bytes:
        from .comms.protocol import session_frame
        return session_frame()

    def dev_exit(self) -> bytes:
        from .comms.protocol import exit_frame
        return exit_frame()

    def dev_read_command(self, x: int) -> bytes:
        from .comms.protocol import read_command
        return read_command(x)

    def dev_read_cmds(self) -> list:
        """[[get_command, record_type, record_len_bytes], …] — what JS streams and how to slice."""
        from .comms.protocol import FOOT_READ_CMDS
        return [[x, rt, rl] for x, (rt, rl) in FOOT_READ_CMDS.items()]

    def dev_load(self, records_by_type) -> dict:
        """Build a Dump from device-read decoded records {record_type: [[values],…]} and make it
        the open document, so the whole editor (and Save) works on what the device returned."""
        from .comms.protocol import _synth_frame, DEFAULT_MODEL
        from .codec import Dump
        dump = Dump()
        for rtype, lists in dict(records_by_type).items():
            rt = int(rtype)
            for i, values in enumerate(lists):
                dump.frames.append(_synth_frame(rt, i, [int(v) & 0xFF for v in values], DEFAULT_MODEL))
        self.dump = dump
        self.dirty = False
        return self.counts()

    def dev_write_frame(self, type_: int, idx: int) -> bytes:
        """The .syx write frame for one record, to send back to the device (gated in the UI)."""
        frs = self._frames(type_)
        return bytes(frs[idx].to_bytes()) if 0 <= idx < len(frs) else b""
