"""
In-depth offline UAT for the device-transfer paths.

`tests/test_uat.py` proves the *editor* side works head-less; this proves the *write* side does
too, without hardware. It drives the real `MainWindow` device methods (push_to_device, transfer,
_read_back) against a fake transport that ACKs (or refuses) writes, and asserts the behaviour a
user depends on:

* only records the user actually edited are sent (and they're sent byte-exact to the .syx frame);
* a successful write re-baselines the record so it isn't re-sent next time;
* a *failed* (un-ACKed) write does NOT re-baseline — the edit is still pending;
* per-record / all-of-type / read-back header transfers route to the right frames;
* every real record type is USB-writable (writable == readable); an unrecognised type is
  refused gracefully;
* per-record-type writes (Song/Set-List/IA-Slot) are additionally readback-verified, not just
  ACK-trusted;
* nothing is transmitted when there is no device, no dump, or no edits.

These lock in the app.py device-I/O refactor (shared `_send_all` / `_commit_baseline` helpers).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox

from lfeditor.comms.protocol import WRITE_ACK

ROOT = pathlib.Path(__file__).resolve().parent.parent
RJM = str(ROOT / "reference" / "sysex_dumps" / "RJM.syx")

from conftest import requires_rjm
pytestmark = requires_rjm


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _silence_dialogs(monkeypatch):
    """Auto-accept confirms; record the LAST info/warning text so tests can assert on it."""
    seen = {}
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: seen.__setitem__("warning", a[2]) or QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: seen.__setitem__("information", a[2]) or QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: seen.__setitem__("critical", a[2]) or QMessageBox.Ok))
    return seen


class FakeTransport:
    """A transport the device-write path can drive head-less.

    `ack=True` returns the device's per-write ACK on every read (so send_record succeeds);
    `ack=False` returns nothing (the write is treated as un-acknowledged). Captures every
    byte string sent so a test can assert exactly which frames went to the wire."""

    def __init__(self, ack=True):
        self.ack = ack
        self.sent = []
        self.flushed = 0

    def send(self, data):
        self.sent.append(bytes(data))

    def read_raw(self, idle_timeout=1.0, overall_timeout=10.0):
        return [WRITE_ACK] if self.ack else []

    def read_frames(self, idle_timeout=1.0, overall_timeout=10.0):
        return self.read_raw()

    def flush_input(self):
        self.flushed += 1

    def close(self):
        pass


class FakeVerifyTransport(FakeTransport):
    """Distinguishes the write-ACK read from the per-record readback-verification read by the
    request's own shape (byte[6]: 0x01 = write frame, 0x02 = per-record read command — see
    protocol.py's `_synth_frame`/`per_record_read_command`), so a test can make the two answer
    differently: `ack` gates the write ACK, `readback` is what a subsequent per-record read
    returns (None simulates the device not answering, e.g. an unverified write)."""

    def __init__(self, ack=True, readback=None):
        super().__init__(ack=ack)
        self.readback = readback

    def read_raw(self, idle_timeout=1.0, overall_timeout=10.0):
        last = self.sent[-1] if self.sent else b""
        if len(last) > 6 and last[6] == 0x02:
            return [self.readback] if self.readback else []
        return [WRITE_ACK] if self.ack else []


def _win(qapp, transport=None):
    """A loaded MainWindow whose device calls run synchronously (no worker thread)."""
    from lfeditor.ui.app import MainWindow
    w = MainWindow()
    w.load(RJM)
    # Run device work inline so assertions see the result immediately (faithful: only the
    # threading is removed; fn() and on_ok() are the real ones).
    w._run_device = lambda fn, on_ok, busy, title, wants_progress=False: \
        on_ok(fn(lambda msg: None) if wants_progress else fn())
    if transport is not None:
        w.transport = transport
    return w


PRESET_TYPE = 1   # writable + readable over USB (bulk path)
SONG_TYPE = 2      # writable + readable over USB (bulk 0x08, falls back to per-record)
UNKNOWN_TYPE = 99  # not a real record type — exercises the writable-gate branch itself


def _edit_first_preset_name(w, name="UAT_EDIT"):
    """Edit one writable record and return its frame."""
    f = next(fr for fr in w.dump.frames if fr.type == PRESET_TYPE)
    presets = w.tab_widgets[0]
    presets.rail.list.setCurrentRow(0)
    presets.header.name.setText(name)
    presets.header.name.editingFinished.emit()
    return f


# ---- refactor invariants -------------------------------------------------------------------

def test_read_and_writable_type_sets(qapp):
    """Writable == readable: every real record type reads over USB (bulk or per-record — see
    FOOT_READ_CMDS / FOOT_PER_RECORD_CMDS) and is now also writable by replaying its own .syx
    record frame, the same way the original editor's SetSong/SetSetlist/etc. do."""
    w = _win(qapp)
    assert w._writable_types() == w._read_types()
    assert PRESET_TYPE in w._writable_types()
    assert SONG_TYPE in w._writable_types()


def test_send_all_routes_written_and_failed(qapp):
    w = _win(qapp, FakeTransport(ack=True))
    frames = [fr for fr in w.dump.frames if fr.type == PRESET_TYPE][:3]
    written, failed = w._send_all(frames)
    assert written == frames and failed == []
    w.transport.ack = False
    written, failed = w._send_all(frames)
    assert written == [] and failed == frames


def test_send_all_readback_verifies_per_record_types(qapp):
    """Song/Setlist/IASwitch writes aren't just ACK-trusted (their write-frame format was
    inferred, not hardware-confirmed the way the read path was — see docs/LF_USB_DIRECT.md):
    a write that ACKs but reads back the wrong (or no) bytes must count as failed."""

    def _win_song():
        w = _win(qapp)
        return w, next(fr for fr in w.dump.frames if fr.type == SONG_TYPE)

    w, song = _win_song()
    w.transport = FakeVerifyTransport(ack=True, readback=song.to_bytes())
    written, failed = w._send_all([song])
    assert written == [song] and failed == []

    w, song = _win_song()
    w.transport = FakeVerifyTransport(ack=True, readback=None)   # ACKed but unverifiable
    written, failed = w._send_all([song])
    assert written == [] and failed == [song]


def test_commit_baseline_clears_pending(qapp):
    w = _win(qapp)
    f = _edit_first_preset_name(w)
    assert f in w._changed_writable()
    w._commit_baseline([f])
    assert f not in w._changed_writable()


# ---- push_to_device (the "To LF+" button / Send-All-Edits) ---------------------------------

def test_push_sends_only_edited_record_byte_exact(qapp, _silence_dialogs):
    t = FakeTransport(ack=True)
    w = _win(qapp, t)
    f = _edit_first_preset_name(w)
    expected = f.to_bytes()
    w.push_to_device()
    # exactly one writable record changed, so exactly one frame should hit the wire, byte-exact
    assert expected in t.sent, "edited record was not written to the device"
    assert sum(1 for b in t.sent if b == expected) == 1
    # and a clean Preset record we did NOT touch must not be sent
    untouched = [fr for fr in w.dump.frames if fr.type == PRESET_TYPE][5].to_bytes()
    assert untouched not in t.sent
    # success re-baselines: a second push finds nothing to send
    t.sent.clear()
    w.push_to_device()
    assert t.sent == []
    assert "No edits" in _silence_dialogs.get("information", "")


def test_push_with_no_edits_sends_nothing(qapp, _silence_dialogs):
    t = FakeTransport(ack=True)
    w = _win(qapp, t)
    w.push_to_device()
    assert t.sent == []
    assert "No edits" in _silence_dialogs.get("information", "")


def test_failed_write_stays_pending(qapp, _silence_dialogs):
    t = FakeTransport(ack=False)   # device never ACKs
    w = _win(qapp, t)
    f = _edit_first_preset_name(w)
    w.push_to_device()
    assert f.to_bytes() in t.sent              # we tried
    assert f in w._changed_writable()          # but it's NOT baselined — still pending
    assert "not confirmed" in _silence_dialogs.get("warning", "")


# ---- per-record / per-type header transfers ------------------------------------------------

def test_transfer_to_sends_single_record(qapp):
    t = FakeTransport(ack=True)
    w = _win(qapp, t)
    target = [fr for fr in w.dump.frames if fr.type == PRESET_TYPE][2]
    w.transfer("to", PRESET_TYPE, 2)
    assert t.sent == [target.to_bytes()]


def test_transfer_all_to_sends_every_record_of_type(qapp):
    t = FakeTransport(ack=True)
    w = _win(qapp, t)
    presets = [fr for fr in w.dump.frames if fr.type == PRESET_TYPE]
    w.transfer("all_to", PRESET_TYPE, 0)
    assert len(t.sent) == len(presets)
    assert set(t.sent) == {fr.to_bytes() for fr in presets}


def test_transfer_refuses_unknown_type(qapp):
    """All 11 real record types are USB-writable now, so this exercises the underlying gating
    branch in transfer() with a type the protocol doesn't recognise at all."""
    t = FakeTransport(ack=True)
    w = _win(qapp, t)
    w.transfer("to", UNKNOWN_TYPE, 0)
    assert t.sent == []


def test_transfer_offline_is_graceful(qapp):
    w = _win(qapp)                         # no transport assigned
    assert w.transport is None
    w.transfer("to", PRESET_TYPE, 0)       # must not raise
    w.transfer("all_to", PRESET_TYPE, 0)


# ---- read-back overlay (the "From LF+" header button) --------------------------------------

def test_read_back_overlays_device_record(qapp, monkeypatch):
    """`transfer('from', …)` pulls a fresh dump and overlays the requested record onto ours."""
    from lfeditor.ui import app as app_mod
    t = FakeTransport(ack=True)
    w = _win(qapp, t)

    # Build a device dump that differs from ours in exactly one Preset, and stub pull_dump.
    import copy
    dev = copy.deepcopy(w.dump)
    dev_target = [fr for fr in dev.frames if fr.type == PRESET_TYPE][1]
    dev_target.values[0] = (dev_target.values[0] + 1) & 0xFF   # change byte 0
    new_bytes = dev_target.to_bytes()
    monkeypatch.setattr(app_mod, "pull_dump", lambda *a, **k: dev, raising=False)
    # _read_back imports pull_dump from ..comms inside the function; patch there too
    monkeypatch.setattr("lfeditor.comms.pull_dump", lambda *a, **k: dev, raising=False)

    ours_before = [fr for fr in w.dump.frames if fr.type == PRESET_TYPE][1].to_bytes()
    assert ours_before != new_bytes
    w.transfer("from", PRESET_TYPE, 1)
    ours_after = [fr for fr in w.dump.frames if fr.type == PRESET_TYPE][1].to_bytes()
    assert ours_after == new_bytes, "device record was not overlaid onto the loaded dump"


def _bulk_silent_song(qapp, monkeypatch):
    """A window whose bulk pull returns nothing, plus a device-side variant of Song #2 —
    the setup for exercising _read_back's runtime per-record fallback."""
    import copy
    from lfeditor.codec import Dump
    w = _win(qapp, FakeTransport(ack=True))
    monkeypatch.setattr("lfeditor.comms.pull_dump", lambda *a, **k: Dump(), raising=False)
    dev_song = copy.deepcopy([fr for fr in w.dump.frames if fr.type == SONG_TYPE][1])
    dev_song.values[0] = (dev_song.values[0] + 1) & 0xFF
    return w, dev_song


def test_read_back_from_falls_back_to_per_record_when_bulk_silent(qapp, monkeypatch):
    """A device that doesn't answer the bulk Song command (firmware variance) must still serve
    a single-record 'From LF+' via the per-record path — the same fallback pull_dump uses."""
    w, dev_song = _bulk_silent_song(qapp, monkeypatch)
    asked = {}

    def fake_one(transport, type_, rec_num, model):
        asked["req"] = (type_, rec_num)
        return dev_song
    monkeypatch.setattr("lfeditor.comms.protocol.pull_one_record_per_record", fake_one)

    w.transfer("from", SONG_TYPE, 1)
    assert asked["req"] == (SONG_TYPE, dev_song.rec_num)
    ours = [fr for fr in w.dump.frames if fr.type == SONG_TYPE][1]
    assert ours.to_bytes() == dev_song.to_bytes()


def test_read_back_all_from_falls_back_to_per_record_when_bulk_silent(qapp, monkeypatch):
    """Same fallback for the all-of-type 'All From LF+' — recovered over pull_records_per_record."""
    w, dev_song = _bulk_silent_song(qapp, monkeypatch)
    monkeypatch.setattr("lfeditor.comms.protocol.pull_records_per_record",
                        lambda *a, **k: [dev_song])

    w.transfer("all_from", SONG_TYPE, 0)
    ours = [fr for fr in w.dump.frames if fr.type == SONG_TYPE][1]
    assert ours.to_bytes() == dev_song.to_bytes()
