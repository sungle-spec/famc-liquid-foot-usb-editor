"""
Exploratory offline UAT driver.

Drives the real MainWindow head-less across every shipped fixture + factory file:
  - builds all tabs, binds the dump
  - walks EVERY record in EVERY tab's rail (pure navigation must not mutate bytes)
  - exercises every menu action (load factory x8, clear-labels x3)
  - drives real widget edits on each editable tab, saves, reloads, checks persistence
  - save/open byte-exact round-trip through the window
  - EEPROM offline detection returns a sane state

Prints a PASS/FAIL line per check and a final summary. Exit code != 0 on any failure.
Run: QT_QPA_PLATFORM=offscreen python scripts/uat_drive.py
"""
import os
import sys
import pathlib
import tempfile
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QMessageBox, QComboBox, QLineEdit, QSpinBox, QPushButton

from lfeditor.codec import Dump
from lfeditor.resources import FACTORY_DEFAULTS, FACTORY_SPECIAL, factory_path

FIXTURES = ROOT / "reference" / "sysex_dumps"
RJM = str(FIXTURES / "RJM.syx")

PASS, FAIL = 0, 0
FAILURES = []


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


def silence_dialogs(monkey_targets):
    """Make every QMessageBox button-return 'Yes' so confirm-gated actions proceed, and stop
    modal dialogs (e.g. the About box) from blocking forever in head-less/offscreen runs —
    a real `QDialog.exec()` has no user to close it, so we make it return immediately."""
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.about = staticmethod(lambda *a, **k: None)
    from PySide6.QtWidgets import QDialog
    QDialog.exec = lambda self, *a, **k: QDialog.Accepted
    QDialog.exec_ = lambda self, *a, **k: QDialog.Accepted


def all_fixture_paths():
    paths = []
    for p in sorted(FIXTURES.glob("*.syx")):
        paths.append(("fixture", p.name, str(p)))
    for _label, fname in FACTORY_DEFAULTS + FACTORY_SPECIAL:
        paths.append(("factory", fname, factory_path(fname)))
    return paths


def walk_every_record(win, tag):
    """Select every record on every rail-bearing tab; bytes must be identical afterwards."""
    before = win.dump.to_bytes()
    crashed = None
    for w in win.tab_widgets:
        rail = getattr(w, "rail", None)
        if rail is None:
            continue
        n = rail.list.count()
        for r in range(n):
            try:
                rail.list.setCurrentRow(r)
            except Exception:  # noqa: BLE001
                crashed = f"{type(w).__name__} row {r}: {traceback.format_exc(limit=2)}"
                break
        if crashed:
            break
    if crashed:
        check(f"[{tag}] walk all records", False, crashed)
        return
    after = win.dump.to_bytes()
    check(f"[{tag}] walk all records — no mutation", before == after,
          f"{len(before)} vs {len(after)} bytes / content differs" if before != after else "")


def toggle_raw(win, tag):
    try:
        win.act_raw.setChecked(True)
        win.act_raw.setChecked(False)
        check(f"[{tag}] raw-bytes toggle", True)
    except Exception:  # noqa: BLE001
        check(f"[{tag}] raw-bytes toggle", False, traceback.format_exc(limit=2))


def load_build_check(MainWindow, kind, name, path):
    """Open a file, build every tab, confirm byte-exact load and full record walk."""
    win = MainWindow()
    raw = pathlib.Path(path).read_bytes()
    try:
        win.load(path)
    except Exception:  # noqa: BLE001
        check(f"[{name}] load", False, traceback.format_exc(limit=3))
        return None
    # byte-exact: the dump the window holds must re-encode to the original file bytes
    reenc = win.dump.to_bytes()
    check(f"[{name}] load byte-exact round-trip", reenc == raw,
          f"{len(reenc)} vs {len(raw)}")
    walk_every_record(win, name)
    toggle_raw(win, name)
    return win


def _all_child_widgets(field):
    """Every interactive child widget a field exposes (top .w plus grids of cells)."""
    from PySide6.QtWidgets import QWidget
    seen, out = set(), []
    top = getattr(field, "w", None)
    roots = [top] if isinstance(top, QWidget) else []
    # bespoke grids keep their cells in lists/dicts on the field
    for attr in vars(field).values():
        if isinstance(attr, (list, tuple)):
            roots += [x for x in attr if isinstance(x, QWidget)]
        elif isinstance(attr, dict):
            roots += [x for x in attr.values() if isinstance(x, QWidget)]
    interactive = (QComboBox, QLineEdit, QSpinBox, QPushButton)
    for root in roots:
        if root is None:
            continue
        for wdg in [root] + root.findChildren(QWidget):
            if id(wdg) in seen:
                continue
            seen.add(id(wdg))
            if isinstance(wdg, interactive):
                out.append(wdg)
    return out


def _perturb(wdg):
    """Change a widget's value via its real signal path. Returns True if it tried an edit."""
    if not wdg.isEnabled():
        return False
    if isinstance(wdg, QComboBox):
        if wdg.count() < 2:
            return False
        new = (wdg.currentIndex() + 1) % wdg.count()
        wdg.setCurrentIndex(new)
        wdg.activated.emit(new)  # bespoke fields listen on activated/currentIndexChanged
        return True
    if isinstance(wdg, QSpinBox):
        new = wdg.value() + (1 if wdg.value() < wdg.maximum() else -1)
        if new == wdg.value():
            return False
        wdg.setValue(new)
        wdg.editingFinished.emit()
        return True
    if isinstance(wdg, QLineEdit):
        if wdg.isReadOnly() or wdg.maxLength() < 1:
            return False
        old = wdg.text()
        new = (old[:-1] + "X") if old and not old.endswith("X") else (old + "1")[:wdg.maxLength()]
        if new == old:
            new = "0" * min(2, wdg.maxLength())
        wdg.setText(new)
        wdg.editingFinished.emit()
        return True
    if isinstance(wdg, QPushButton) and wdg.isCheckable():
        wdg.setChecked(not wdg.isChecked())
        wdg.toggled.emit(wdg.isChecked())
        wdg.clicked.emit()
        return True
    return False


def edit_persist_check(MainWindow):
    """Perturb every interactive widget on every editable tab; verify write-back + round-trip."""
    win = MainWindow()
    win.load(RJM)
    perturbed = 0
    bytewrites = 0
    per_tab = {}

    for w in win.tab_widgets:
        rail = getattr(w, "rail", None)
        tabname = type(w).__name__
        if rail is not None and rail.list.count():
            rail.list.setCurrentRow(0)
        before_dump = win.dump.to_bytes()
        tab_writes = 0
        for f in getattr(w, "_all_fields", []):
            for wdg in _all_child_widgets(f):
                snap = win.dump.to_bytes()
                try:
                    if _perturb(wdg):
                        perturbed += 1
                        if win.dump.to_bytes() != snap:
                            bytewrites += 1
                            tab_writes += 1
                except Exception:  # noqa: BLE001
                    check(f"perturb {tabname}.{f.label!r} {type(wdg).__name__}", False,
                          traceback.format_exc(limit=2))
        per_tab[tabname] = tab_writes

    # everything we changed must still save + reload byte-exact
    with tempfile.NamedTemporaryFile(suffix=".syx", delete=False) as tf:
        tmp = tf.name
    win.dump.to_file(tmp)
    win2 = MainWindow()
    win2.load(tmp)
    same = win2.dump.to_bytes() == pathlib.Path(tmp).read_bytes()
    check("heavy-edit: save/reload round-trip byte-exact", same)
    check("heavy-edit: edits reached the byte buffer", bytewrites > 0,
          f"{perturbed} widgets perturbed, {bytewrites} changed bytes")
    os.unlink(tmp)
    print(f"        ({perturbed} widgets perturbed, {bytewrites} produced byte writes)")
    for t, c in per_tab.items():
        print(f"          {t}: {c} byte-writing edits")


def bespoke_tab_check(MainWindow):
    """Drive the two hand-built tabs (Midi/Groups, Pages) whose controls aren't in _all_fields."""
    from lfeditor.ui.tabs.midi_groups_tab import MidiGroupsTab
    from lfeditor.ui.tabs.pages_tab import PagesTab

    win = MainWindow()
    win.load(RJM)

    # ---- Midi/Groups ----
    mg = next(w for w in win.tab_widgets if isinstance(w, MidiGroupsTab))
    groups = {
        "exclusive spinners": [getattr(f, "w", None) for f in getattr(mg, "_excl", [])],
        "grouped combos": list(getattr(mg, "_grp_combos", [])),
        "channel names": list(getattr(mg, "_name_edits", [])),
        "max-pre spinners": list(getattr(mg, "_maxpre", [])),
        "+1 rockers": list(getattr(mg, "_tg_plus1", [])),
        "send rockers": list(getattr(mg, "_tg_send", [])),
        "msb rockers": list(getattr(mg, "_tg_msb", [])),
    }
    for gname, widgets in groups.items():
        wrote = 0
        for wdg in widgets:
            if wdg is None:
                continue
            snap = win.dump.to_bytes()
            if _perturb(wdg) and win.dump.to_bytes() != snap:
                wrote += 1
        check(f"Midi/Groups: {gname} write back to bytes", wrote > 0,
              f"{len(widgets)} controls, 0 wrote")

    # ---- Pages ----
    pg = next(w for w in win.tab_widgets if isinstance(w, PagesTab))
    pg.rail.list.setCurrentRow(0)
    pg._select(0)  # select first footswitch so the button panel binds
    page_groups = {
        "param fields": [getattr(f, "w", None) for f in getattr(pg, "_param_fields", [])],
        "function-type combos": list(getattr(pg, "f_types", [])),
        "function-value combos": list(getattr(pg, "f_values", [])),
        "trigger combo": [getattr(pg, "trig", None)],
    }
    for gname, widgets in page_groups.items():
        wrote = 0
        for wdg in widgets:
            if wdg is None:
                continue
            snap = win.dump.to_bytes()
            if _perturb(wdg) and win.dump.to_bytes() != snap:
                wrote += 1
        check(f"Pages: {gname} write back to bytes", wrote > 0,
              f"{len(widgets)} controls, 0 wrote")

    # Pages drag-swap: swap two tiles and confirm bytes move
    snap = win.dump.to_bytes()
    try:
        pg._swap(0, 1, False)  # move (not copy)
        check("Pages: tile drag-swap mutates bytes", win.dump.to_bytes() != snap)
    except Exception:  # noqa: BLE001
        check("Pages: tile drag-swap", False, traceback.format_exc(limit=2))

    # everything edited here still saves + reloads byte-exact
    with tempfile.NamedTemporaryFile(suffix=".syx", delete=False) as tf:
        tmp = tf.name
    win.dump.to_file(tmp)
    win2 = MainWindow(); win2.load(tmp)
    check("bespoke tabs: save/reload round-trip byte-exact",
          win2.dump.to_bytes() == pathlib.Path(tmp).read_bytes())
    os.unlink(tmp)


def symmetry_and_window_check(MainWindow):
    """Known-value edit survives save/reload; window save_file path works; transfers safe offline."""
    win = MainWindow()
    win.load(RJM)

    # set a known full-name on preset record 0 via its real header field, save through the window
    presets_tab = win.tab_widgets[0]
    presets_tab.rail.list.setCurrentRow(0)
    name_edit = presets_tab.header.name  # green LCD full-name editor
    KNOWN = "UAT_NAME_7"
    name_edit.setText(KNOWN)
    name_edit.editingFinished.emit()

    with tempfile.NamedTemporaryFile(suffix=".syx", delete=False) as tf:
        tmp = tf.name
    win.path = tmp
    win.save_file()             # exercises MainWindow.save_file (not just dump.to_file)
    check("window.save_file clears dirty + writes", not win._dirty and os.path.getsize(tmp) > 0)

    win2 = MainWindow(); win2.load(tmp)
    got = (win2.dump.presets[0].name or "").strip()
    check("known-value edit survives save/reload", got == KNOWN, f"got {got!r}")
    os.unlink(tmp)

    # transfers must be graceful offline (no transport) — info dialog, no crash
    try:
        win.transfer("to", 1, 0)
        win.transfer("from", 1, 0)
        win.transfer("all_to", 1, 0)
        win.push_to_device()
        win.pull_from_device()
        check("transfer buttons safe offline (no device)", True)
    except Exception:  # noqa: BLE001
        check("transfer buttons safe offline (no device)", False, traceback.format_exc(limit=2))


class _FakeAckTransport:
    """Captures sent frames; ACKs (or refuses) writes so the write path runs head-less."""
    def __init__(self, ack=True):
        from lfeditor.comms.protocol import WRITE_ACK
        self._ack = ack
        self._WRITE_ACK = WRITE_ACK
        self.sent = []

    def send(self, data):
        self.sent.append(bytes(data))

    def read_raw(self, idle_timeout=1.0, overall_timeout=10.0):
        return [self._WRITE_ACK] if self._ack else []

    def read_frames(self, idle_timeout=1.0, overall_timeout=10.0):
        return self.read_raw()

    def flush_input(self):
        pass

    def close(self):
        pass


def device_transfer_check(MainWindow):
    """Drive the real device-write path against a fake transport (no hardware)."""
    PRESET = 1

    def fresh(transport):
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
        QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Yes)
        win = MainWindow(); win.load(RJM)
        win._run_device = lambda fn, on_ok, busy, title: on_ok(fn())  # run inline, no thread
        win.transport = transport
        return win

    # 1. push sends only the edited record, byte-exact, then re-baselines it
    try:
        t = _FakeAckTransport(ack=True)
        win = fresh(t)
        f = next(fr for fr in win.dump.frames if fr.type == PRESET)
        win.tab_widgets[0].rail.list.setCurrentRow(0)
        win.tab_widgets[0].header.name.setText("UAT_DEV")
        win.tab_widgets[0].header.name.editingFinished.emit()
        expected = f.to_bytes()
        win.push_to_device()
        sent_once = t.sent.count(expected) == 1
        t.sent.clear()
        win.push_to_device()                       # nothing left to send after a good write
        check("device: push sends only the edited record (byte-exact)", sent_once)
        check("device: successful write re-baselines (no re-send)", t.sent == [])
    except Exception:  # noqa: BLE001
        check("device: push edited record", False, traceback.format_exc(limit=2))

    # 2. a failed (un-ACKed) write leaves the edit pending
    try:
        t = _FakeAckTransport(ack=False)
        win = fresh(t)
        f = next(fr for fr in win.dump.frames if fr.type == PRESET)
        win.tab_widgets[0].rail.list.setCurrentRow(0)
        win.tab_widgets[0].header.name.setText("UAT_NAK")
        win.tab_widgets[0].header.name.editingFinished.emit()
        win.push_to_device()
        check("device: failed write stays pending (not baselined)", f in win._changed_writable())
    except Exception:  # noqa: BLE001
        check("device: failed write stays pending", False, traceback.format_exc(limit=2))

    # 3. header transfers: per-record, all-of-type, and refusing a non-writable type
    try:
        t = _FakeAckTransport(ack=True)
        win = fresh(t)
        target = [fr for fr in win.dump.frames if fr.type == PRESET][2]
        win.transfer("to", PRESET, 2)
        check("device: transfer 'to' sends the one selected record", t.sent == [target.to_bytes()])
        t.sent.clear()
        presets = [fr for fr in win.dump.frames if fr.type == PRESET]
        win.transfer("all_to", PRESET, 0)
        check("device: transfer 'all_to' sends every record of the type",
              set(t.sent) == {fr.to_bytes() for fr in presets})
        t.sent.clear()
        win.transfer("to", 2, 0)                    # Song — not USB-writable
        check("device: transfer refuses a non-writable type", t.sent == [])
    except Exception:  # noqa: BLE001
        check("device: header transfers", False, traceback.format_exc(limit=2))


def menu_check(MainWindow):
    # load every factory file via the menu path
    for label, fname in FACTORY_DEFAULTS + FACTORY_SPECIAL:
        win = MainWindow()
        win.load(RJM)
        try:
            win.load_factory(fname, label)
            ok = win.path is None and win._dirty and win.dump.counts().get("Preset", 0) == 384
            check(f"menu: Load Factory '{label}'", ok)
        except Exception:  # noqa: BLE001
            check(f"menu: Load Factory '{label}'", False, traceback.format_exc(limit=2))

    # clear-labels for the three extension record types
    for rtype, what in [(9, "Preset Labels"), (10, "Preset MAP Labels"), (11, "Song Preset Labels")]:
        win = MainWindow()
        win.load(RJM)
        recs = win.dump.records(rtype)
        if not recs:
            check(f"menu: Clear {what}", False, "no extension records of this type")
            continue
        recs[0].set_label(0, "KEEPME")
        win.clear_labels(rtype, what)
        cleared = all(not any(r.labels()) for r in win.dump.records(rtype))
        check(f"menu: Clear {what}", cleared and win._dirty)

    # About (must not raise)
    win = MainWindow()
    try:
        win._about()
        check("menu: About", True)
    except Exception:  # noqa: BLE001
        check("menu: About", False, traceback.format_exc(limit=2))


def eeprom_check():
    from lfeditor.comms import eeprom
    try:
        st = eeprom.detect_state()
        valid = st in vars(eeprom).values() or isinstance(st, str) or st is not None
        check("eeprom: offline detect_state returns a state", st is not None, repr(st))
    except Exception:  # noqa: BLE001
        check("eeprom: offline detect_state", False, traceback.format_exc(limit=2))


def main():
    app = QApplication.instance() or QApplication([])
    silence_dialogs(None)
    from lfeditor.ui.app import MainWindow

    print("== Load + build + walk every record, every fixture & factory file ==")
    for kind, name, path in all_fixture_paths():
        load_build_check(MainWindow, kind, name, path)

    print("\n== Edit / save / reload persistence ==")
    edit_persist_check(MainWindow)

    print("\n== Bespoke tabs (Midi/Groups, Pages) ==")
    bespoke_tab_check(MainWindow)

    print("\n== Edit symmetry, window save, offline-transfer safety ==")
    symmetry_and_window_check(MainWindow)

    print("\n== Device transfers (fake transport, no hardware) ==")
    device_transfer_check(MainWindow)

    print("\n== Menu actions ==")
    menu_check(MainWindow)

    print("\n== EEPROM offline ==")
    eeprom_check()

    print(f"\n==== UAT SUMMARY: {PASS} passed, {FAIL} failed ====")
    if FAILURES:
        print("\nFailures:")
        for n, d in FAILURES:
            print(f"  - {n}: {d.splitlines()[-1] if d else ''}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
