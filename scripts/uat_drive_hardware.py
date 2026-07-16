"""
Hardware UAT driver for the app.py refactor (Tier 2 of the UAT plan, automated).

Drives the REAL `MainWindow` — not a reimplementation of the protocol — against a REAL LF+ over
USB-serial, the same way `tests/test_uat_device.py::_win()` does for its fake-transport tests:
`_run_device` is patched to run synchronously (no QThread) so a script gets results back inline,
and `QMessageBox` is patched (borrowing `scripts/uat_drive.py`'s `silence_dialogs()` idea) to
auto-accept confirmations and capture the text a user would have read, so it can be asserted on.

This exercises exactly the code paths the app.py refactor touched: `_rebind_tabs`, `_finish_write`,
the rewritten `_read_back` (including its runtime per-record fallback branch), the de-cached
`_read_types`/`_writable_types`, and `closeEvent` → `disconnect_device`.

SAFETY — real device writes happen. Exactly two records are mutated (one Preset name, one Song
name), both restored to their original bytes and verified byte-identical to a pre-write backup
before the script finishes. A backup is taken (from the first full read) BEFORE any write step is
allowed to run; the script hard-fails rather than proceeding if that backup didn't land. No
Config/firmware/bulk-structural record is ever touched.

    QT_QPA_PLATFORM=offscreen python scripts/uat_drive_hardware.py
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import pathlib
import time
import traceback
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ART = ROOT / "scripts" / "ARTIFACTS"
ART.mkdir(exist_ok=True)

from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

PRESET_TYPE = 1
SONG_TYPE = 2
SETLIST_TYPE = 5

PASS, FAIL = 0, 0
FAILURES = []
LOG_LINES = []


def log(line: str = ""):
    print(line)
    LOG_LINES.append(line)


def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        log(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        log(f"  FAIL  {name}  {detail}")


def silence_dialogs():
    """Auto-accept every QMessageBox (Yes/Ok) so confirm-gated device actions proceed without a
    user, and capture the LAST text shown per kind so a step can assert on what it says."""
    seen = {}
    QMessageBox.question = staticmethod(lambda *a, **k: seen.__setitem__("question", a[2]) or QMessageBox.Yes)
    QMessageBox.warning = staticmethod(lambda *a, **k: seen.__setitem__("warning", a[2]) or QMessageBox.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: seen.__setitem__("information", a[2]) or QMessageBox.Ok)
    QMessageBox.critical = staticmethod(lambda *a, **k: seen.__setitem__("critical", a[2]) or QMessageBox.Ok)
    QDialog.exec = lambda self, *a, **k: QDialog.Accepted
    QDialog.exec_ = lambda self, *a, **k: QDialog.Accepted
    return seen


def sync_run_device(win):
    """Make win._run_device execute inline (no QThread) — same pattern as
    tests/test_uat_device.py::_win(), so a script gets the result immediately."""
    def _run(fn, on_ok, busy, title, wants_progress=False):
        try:
            result = fn(lambda msg: None) if wants_progress else fn()
        except Exception as exc:  # noqa: BLE001
            check(f"[device call: {title}]", False, traceback.format_exc(limit=3))
            raise
        on_ok(result)
    win._run_device = _run


def main():
    app = QApplication.instance() or QApplication([])
    seen = silence_dialogs()
    from lfeditor.ui.app import MainWindow
    from lfeditor.comms import MODEL_FOOT
    from lfeditor.comms.protocol import pull_one_record_per_record

    win = MainWindow()
    sync_run_device(win)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ---- T2.1: connect ---------------------------------------------------------------------
    log("== T2.1 Connect ==")
    win.connect_device()
    check("connect: transport open", win.transport is not None)
    if win.transport is None:
        check("connect: no LF+ found — aborting remaining steps", False,
              "plug in the Liquid Foot+ and retry")
        finish(1)
        return
    check("connect: status shows Editor Mode", "Editor Mode" in win.conn.text())

    # ---- T2.2 + backup: From LF+ (read all), then save it as the pre-write backup ---------
    log("\n== T2.2 From LF+ (read all) + mandatory pre-write backup ==")
    t0 = time.time()
    win.pull_from_device()
    elapsed = time.time() - t0
    check("pull: dump populated", win.dump is not None and len(win.dump.frames) > 0)
    counts = win.dump.counts() if win.dump else {}
    for kind in ("Song", "Setlist", "IASwitch", "Page"):
        check(f"pull: {kind} records present", counts.get(kind, 0) > 0, f"counts={counts}")
    check("pull: completed quickly (bulk path, not the old 562-request sweep)", elapsed < 60,
          f"{elapsed:.1f}s")

    backup_path = ART / f"uat_refactor_backup_{ts}.syx"
    win.dump.to_file(str(backup_path))
    backup_ok = backup_path.exists() and backup_path.stat().st_size > 10000
    check("backup: pre-write backup written", backup_ok, str(backup_path))
    if not backup_ok:
        check("backup: refusing to run write steps without a verified backup", False)
        win.close()
        finish(1)
        return
    # Freeze the pristine bytes for the two records we're about to touch, for later restore.
    orig_preset_bytes = win.dump.records(PRESET_TYPE)[0].frame.to_bytes()
    orig_song_bytes = win.dump.records(SONG_TYPE)[1].frame.to_bytes()

    # ---- T2.3: header From (single Song) -----------------------------------------------------
    log("\n== T2.3 Header From LF+ — single Song record ==")
    before_snapshot = {(f.type, f.rec_num): f.to_bytes() for f in win.dump.frames}
    song_rec_num = win.dump.records(SONG_TYPE)[1].frame.rec_num
    win.transfer("from", SONG_TYPE, 1)
    fresh = pull_one_record_per_record(win.transport, SONG_TYPE, song_rec_num, MODEL_FOOT)
    got = win.dump.records(SONG_TYPE)[1].frame.to_bytes()
    check("transfer(from, Song, 1): matches independent per-record read",
          fresh is not None and got == fresh.to_bytes())
    unrelated_changed = [
        key for key, b in before_snapshot.items()
        if key != (SONG_TYPE, song_rec_num)
        and b != next(f.to_bytes() for f in win.dump.frames if (f.type, f.rec_num) == key)
    ]
    check("transfer(from, Song, 1): no other record mutated", not unrelated_changed,
          f"{len(unrelated_changed)} unrelated records changed")

    # ---- T2.4: header All-From (Setlist) -----------------------------------------------------
    log("\n== T2.4 Header All-From LF+ — Set-List ==")
    n_before = len(win.dump.records(SETLIST_TYPE))
    win.transfer("all_from", SETLIST_TYPE, 0)
    n_after = len(win.dump.records(SETLIST_TYPE))
    check("transfer(all_from, Setlist): record count unchanged", n_before == n_after,
          f"{n_before} -> {n_after}")

    # ---- T2.5 + T2.6: edit + push one Preset, then push-again is a no-op -------------------
    log("\n== T2.5/T2.6 Edit + push one Preset, then push again (no edits) ==")
    p0 = win.dump.records(PRESET_TYPE)[0]
    original_preset_name = p0.name
    p0.name = "UATHWTEST"
    seen.clear()
    win.push_to_device()
    check("push: wrote 1 record, all acknowledged", "Wrote 1 record" in seen.get("information", ""),
          seen.get("information", "<none>"))
    check("push: baseline committed (nothing pending)", p0.frame not in win._changed_writable())
    seen.clear()
    win.push_to_device()
    check("push again: reports no edits", "No edits" in seen.get("information", ""),
          seen.get("information", "<none>"))

    # ---- T2.7: edit + push one Song via the header --------------------------------------
    log("\n== T2.7 Edit + push one Song via header To LF+ ==")
    s1 = win.dump.records(SONG_TYPE)[1]
    original_song_name = s1.name
    s1.name = "UATHWSONG"
    seen.clear()
    win.transfer("to", SONG_TYPE, 1)
    check("transfer(to, Song, 1): wrote + Song noun used",
          "Wrote 1 Song record" in seen.get("information", ""), seen.get("information", "<none>"))

    # ---- T2.8: re-pull, verify the edits landed, then restore + verify net-zero -----------
    log("\n== T2.8 Re-pull verifies edits landed, then restore to pre-test bytes ==")
    win.pull_from_device()
    check("re-pull: preset shows edited name", win.dump.records(PRESET_TYPE)[0].name == "UATHWTEST")
    check("re-pull: song shows edited name", win.dump.records(SONG_TYPE)[1].name == "UATHWSONG")

    win.dump.records(PRESET_TYPE)[0].name = original_preset_name
    win.dump.records(SONG_TYPE)[1].name = original_song_name
    seen.clear()
    win.push_to_device()
    check("restore: wrote 2 records, all acknowledged", "Wrote 2 record" in seen.get("information", ""),
          seen.get("information", "<none>"))
    win.pull_from_device()
    restored_preset = win.dump.records(PRESET_TYPE)[0].frame.to_bytes()
    restored_song = win.dump.records(SONG_TYPE)[1].frame.to_bytes()
    check("restore: preset byte-identical to pre-test backup", restored_preset == orig_preset_bytes)
    check("restore: song byte-identical to pre-test backup", restored_song == orig_song_bytes)

    # ---- T2.9: close() while connected sends the exit control ----------------------------
    log("\n== T2.9 MainWindow.close() while connected leaves Editor Mode ==")
    sent_frames = []
    real_send = win.transport.send
    real_close = win.transport.close
    closed = {"v": False}
    win.transport.send = lambda data: (sent_frames.append(bytes(data)), real_send(data))[-1]
    win.transport.close = lambda: (closed.__setitem__("v", True), real_close())
    win.close()
    exit_sent = any(len(f) >= 7 and f[4:7] == bytes([0x0F, 0x0F, 0xCC]) for f in sent_frames)
    check("close(): sent the leave-Editor-Mode (CC) control", exit_sent)
    check("close(): transport was closed", closed["v"])
    check("close(): win.transport cleared", win.transport is None)
    log("  NOTE: the device LCD actually leaving \"Editor Mode\" is a visual confirmation only "
        "a human at the unit can make — not script-observable. Please glance at the LCD now.")

    # ---- T2.10: reconnect, then disconnect via the toolbar path ---------------------------
    log("\n== T2.10 Reconnect, then disconnect via the toolbar path ==")
    win2 = MainWindow()
    sync_run_device(win2)
    win2.connect_device()
    check("reconnect: transport open", win2.transport is not None)
    if win2.transport is not None:
        win2.disconnect_device()
        check("disconnect_device(): transport cleared", win2.transport is None)
        check("disconnect_device(): status shows not connected", "not connected" in win2.conn.text())

    finish(1 if FAIL else 0)


def finish(code: int):
    log(f"\n==== HARDWARE UAT SUMMARY: {PASS} passed, {FAIL} failed ====")
    if FAILURES:
        log("\nFailures:")
        for n, d in FAILURES:
            log(f"  - {n}: {d.splitlines()[-1] if d else ''}")
    log_path = ART / f"uat_refactor_hardware_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path.write_text("\n".join(LOG_LINES) + "\n")
    print(f"\n(log written to {log_path})")
    sys.exit(code)


if __name__ == "__main__":
    main()
