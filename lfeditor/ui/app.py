"""Main window — native rewrite of the LF+ Editor shell."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QToolBar, QFileDialog, QMessageBox, QLabel, QWidget,
)

from ..codec import Dump
from .theme import ACCENT, RED, AMBER
from .specs import RECORD_TABS, GLOBAL_TABS
from .tabs import SectionedTab, GlobalTab, MidiGroupsTab, PagesTab


class _DeviceTask(QThread):
    """Runs one blocking device call off the UI thread; emits the result or an error string."""
    ok = Signal(object)
    err = Signal(str)
    progress = Signal(str)   # only used when the caller opts in (see MainWindow._run_device)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.ok.emit(self._fn())
        except Exception as exc:  # noqa: BLE001
            self.err.emit(str(exc))

# Tab order matches the original editor (two rows there; one bar here).
TAB_ORDER = [
    "Presets", "Set-List", "IA-Slot", "IA-Maps", "Midi/Groups", "Global",
    "Songs", "Pages", "Sysex Msgs", "Exp Pedals", "Colors",
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dump: Dump | None = None
        self.path: str | None = None
        self._dirty = False
        self.transport = None  # open device link, or None
        self._record_clip = None  # whole-record copy buffer (see ui/record_ops.py)
        self._find_dialog = None  # the non-modal Find / Q-LIST window
        self._midi_monitor = None  # the non-modal MIDI monitor / pass-thru window
        self._midi_bridge = None   # the non-modal USB MIDI In Bridge window
        self._device_busy = False  # True while a _DeviceTask transfer runs (bridge pauses)

        self.setWindowTitle("LF+ Editor (native)")
        self.resize(1320, 860)
        self.setMinimumSize(1024, 680)
        self._build_toolbar()

        self.tabs = QTabWidget()
        self.tab_widgets: list[QWidget] = []
        for name in TAB_ORDER:
            w = self._make_tab(name)
            self.tabs.addTab(w, name)
            self.tab_widgets.append(w)
        self.setCentralWidget(self.tabs)

        # Q-LIST: left-side quick-pick dock that follows the current tab (on by default)
        from .qlist_dock import QListDock
        self.qlist = QListDock(self, lambda: self.dump, self.reveal, self._qlist_pick_type)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.qlist)
        self.qlist.visibilityChanged.connect(
            lambda vis: self.act_qlist.setChecked(vis) if self.act_qlist.isChecked() != vis else None)
        self.tabs.currentChanged.connect(self._sync_qlist)
        self.act_qlist.setChecked(True)   # show the dock; rails are hidden, this is the navigator
        self._sync_qlist()

        self._build_menus()

        self.status = QLabel("No file loaded")
        self.status.setObjectName("status")
        self.statusBar().addWidget(self.status)
        self.conn = QLabel()
        self.statusBar().addPermanentWidget(self.conn)
        self._set_conn("not connected", RED)
        self._update_title()

    def _make_tab(self, name: str) -> QWidget:
        """Build the faithful tab widget for `name`."""
        if name in RECORD_TABS:
            return SectionedTab(RECORD_TABS[name], on_transfer=self.transfer)
        if name in GLOBAL_TABS:
            return GlobalTab(GLOBAL_TABS[name], on_transfer=self.transfer)
        if name == "Midi/Groups":
            return MidiGroupsTab(on_transfer=self.transfer)
        if name == "Pages":
            return PagesTab(on_transfer=self.transfer)
        raise KeyError(name)

    def _build_menus(self):
        from ..resources import FACTORY_DEFAULTS, FACTORY_SPECIAL
        bar = self.menuBar()

        # ---- File ----
        filem = bar.addMenu("File")
        filem.addAction("Open…", self.open_file)
        filem.addAction("Save", self.save_file)
        filem.addAction("Backup (Save As)…", self.save_as)
        filem.addSeparator()
        facd = filem.addMenu("Load Factory Defaults into Editor")
        for label, fname in FACTORY_DEFAULTS:
            facd.addAction(label, lambda _=False, f=fname, n=label: self.load_factory(f, n))
        facs = filem.addMenu("Load Special Factory Programming")
        for label, fname in FACTORY_SPECIAL:
            facs.addAction(label, lambda _=False, f=fname, n=label: self.load_factory(f, n))
        filem.addSeparator()
        from ..csvio import KINDS
        impm = filem.addMenu("Import from CSV")
        expm = filem.addMenu("Export to CSV")
        for key, spec in KINDS.items():
            impm.addAction(spec["label"],
                           lambda _=False, k=key, n=spec["label"]: self.import_records(k, n))
            expm.addAction(spec["label"],
                           lambda _=False, k=key, n=spec["label"]: self.export_records(k, n))
        filem.addSeparator()
        # NoRole stops macOS from spiriting "About" away into the (Python) application menu,
        # so it stays visible here. Also mirror it under Help for discoverability.
        about_act = QAction("About / License", self)
        about_act.setMenuRole(QAction.MenuRole.NoRole)
        about_act.triggered.connect(self._about)
        filem.addAction(about_act)

        # ---- Edit ----
        editm = bar.addMenu("Edit")
        editm.addAction(self.act_copy)
        editm.addAction(self.act_paste)
        editm.addAction(self.act_find)
        editm.addAction("Clear Current Record…", self.clear_record)
        editm.addSeparator()
        editm.addAction("Clear Preset Labels…", lambda: self.clear_labels(9, "Preset Labels"))
        editm.addAction("Clear Preset MAP Labels…",
                        lambda: self.clear_labels(10, "Preset MAP Labels"))
        editm.addAction("Clear Song Preset Labels…",
                        lambda: self.clear_labels(11, "Song Preset Labels"))

        # ---- Utilities ----
        util = bar.addMenu("Utilities")
        util.addAction("Quick Repeated Command Programmer…", self.open_quick_prog)
        util.addAction("Re-order Records (Save / Sync)…", self.open_reorder)
        util.addAction("MIDI Monitor / Pass-Thru…", self.open_midi_monitor)
        util.addSeparator()
        for name in ("External Device Definitions", "External Device Sync (Kemper/Axe-Fx)"):
            act = util.addAction(name)
            act.setEnabled(False)
        util.setToolTipsVisible(True)

        # ---- Hardware ----
        hw = bar.addMenu("Hardware")
        hw.addAction("Device Connection Setup…", self.open_eeprom_wizard)
        hw.addSeparator()
        hw.addAction("Connect / Disconnect", self.toggle_connect)
        hw.addAction("From LF+ (read all)", self.pull_from_device)
        hw.addAction("To LF+ (write edits)", self.push_to_device)
        hw.addSeparator()
        act = hw.addAction("USB MIDI In Bridge…", self.open_midi_bridge)
        act.setToolTip("Send MIDI commands (preset changes, IA triggers) to the LF+ over this "
                       "USB cable — needs the device global “Allow MIDI CMDS = YES”")
        hw.addSeparator()
        for name in ("Reset Config in LF+", "Reset LF+ to Factory Defaults",
                     "Load Firmware From File…", "Review / Install Latest Firmware…"):
            act = hw.addAction(name)
            act.setEnabled(False)   # Phase 2/3 — device writes / firmware flashing (not yet)
        hw.setToolTipsVisible(True)

        # ---- Reports (read-only human-readable CSV summaries) ----
        rep = bar.addMenu("Reports")
        rep.addAction("Preset report…", lambda: self.save_report("presets", "Preset"))
        rep.addAction("Song report…", lambda: self.save_report("songs", "Song"))
        rep.addAction("Set-List report…", lambda: self.save_report("setlists", "Set-List"))

        # ---- Complete Transfers ----
        ct = bar.addMenu("Complete Transfers")
        ct.addAction("Get Everything from LF+", self.pull_from_device)
        ct.addAction("Send All Edits to LF+", self.push_to_device)

        # ---- Settings ----
        setm = bar.addMenu("Settings")
        self.act_raw = QAction("Show raw bytes", self, checkable=True)
        self.act_raw.toggled.connect(self._toggle_raw)
        setm.addAction(self.act_raw)
        setm.addAction(self.act_qlist)   # Q-LIST show/hide (also a toolbar toggle)

        # ---- Help ----
        helpm = bar.addMenu("Help")
        h_about = QAction("About / License", self)
        h_about.setMenuRole(QAction.MenuRole.NoRole)
        h_about.triggered.connect(self._about)
        helpm.addAction(h_about)

    def _toggle_raw(self, on: bool):
        for w in self.tab_widgets:
            if hasattr(w, "set_raw_visible"):
                w.set_raw_visible(on)

    def open_eeprom_wizard(self):
        from .eeprom_wizard import EepromWizard
        EepromWizard(self).exec()

    def open_midi_monitor(self):
        if getattr(self, "_midi_monitor", None) is None:
            from .midi_monitor import MidiMonitorDialog
            self._midi_monitor = MidiMonitorDialog(self)
        self._midi_monitor.show()
        self._midi_monitor.raise_()
        self._midi_monitor.activateWindow()

    def open_midi_bridge(self):
        if getattr(self, "_midi_bridge", None) is None:
            from .midi_bridge import UsbMidiBridgeDialog
            self._midi_bridge = UsbMidiBridgeDialog(self)
        self._midi_bridge.show()
        self._midi_bridge.raise_()
        self._midi_bridge.activateWindow()

    def _refresh_after_bulk_edit(self):
        """Re-bind every tab after a bulk edit (quick-prog / re-order) changed many records."""
        if self.dump is None:
            return
        for w in self.tab_widgets:
            w.set_dump(self.dump)
        self.mark_dirty()

    def open_quick_prog(self):
        from .quickprog_dialog import QuickProgDialog
        QuickProgDialog(self, lambda: self.dump, self._refresh_after_bulk_edit).exec()

    def open_reorder(self):
        from .reorder_dialog import ReorderDialog
        ReorderDialog(self, lambda: self.dump, self._refresh_after_bulk_edit).exec()

    # --- toolbar / actions ---
    def _build_toolbar(self):
        from .icons import icon
        from PySide6.QtCore import QSize
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(26, 26))
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.addToolBar(tb)
        # file group — open / save / backup, as icons like the original
        for label, name, slot, key in [
            ("Open", "open", self.open_file, QKeySequence.Open),
            ("Save", "save", self.save_file, QKeySequence.Save),
            ("Backup", "backup", self.save_as, QKeySequence.SaveAs),
        ]:
            act = QAction(icon(name), label, self)
            if key:
                act.setShortcut(key)
            act.triggered.connect(slot)
            tb.addAction(act)
        tb.addSeparator()
        # edit group — clear / copy / paste the current record (mirrors the original)
        self.act_clear = QAction(icon("clear"), "Clear", self)
        self.act_clear.setToolTip("Reset the current record to default")
        self.act_clear.triggered.connect(self.clear_record)
        tb.addAction(self.act_clear)
        self.act_copy = QAction(icon("copy"), "Copy", self)
        self.act_copy.setShortcut("Ctrl+Shift+C")
        self.act_copy.setToolTip("Copy the whole current record")
        self.act_copy.triggered.connect(self.copy_record)
        tb.addAction(self.act_copy)
        self.act_paste = QAction(icon("paste"), "Paste", self)
        self.act_paste.setShortcut("Ctrl+Shift+V")
        self.act_paste.setToolTip("Paste the copied record over the current one")
        self.act_paste.triggered.connect(self.paste_record)
        self.act_paste.setEnabled(False)
        tb.addAction(self.act_paste)
        tb.addSeparator()
        # find / Q-LIST
        self.act_find = QAction(icon("find"), "Find", self)
        self.act_find.setShortcut(QKeySequence.Find)   # Cmd/Ctrl+F
        self.act_find.setToolTip("Find records by name or MIDI command")
        self.act_find.triggered.connect(self.open_find)
        tb.addAction(self.act_find)
        self.act_qlist = QAction(icon("find"), "Q-LIST", self)
        self.act_qlist.setCheckable(True)
        self.act_qlist.setToolTip("Show/hide the Q-LIST: a searchable record list you can drag onto "
                                  "slot pickers and command rows")
        self.act_qlist.toggled.connect(self.toggle_qlist)
        tb.addAction(self.act_qlist)
        tb.addSeparator()
        self.act_connect = QAction("Connect", self)
        self.act_connect.triggered.connect(self.toggle_connect)
        tb.addAction(self.act_connect)
        self.act_from = QAction("From LF+", self)
        self.act_from.triggered.connect(self.pull_from_device)
        self.act_from.setEnabled(False)
        tb.addAction(self.act_from)
        self.act_to = QAction("To LF+", self)
        self.act_to.triggered.connect(self.push_to_device)
        self.act_to.setEnabled(False)
        tb.addAction(self.act_to)

    # --- device session (all device I/O runs on a worker thread) ---
    WRITABLE_TYPES = None  # set lazily from FOOT_READ_CMDS
    READ_TYPES = None      # set lazily from FOOT_READ_CMDS + FOOT_PER_RECORD_CMDS

    def _writable_types(self):
        # Writable == readable: every type we can read over USB (bulk + per-record — see
        # _read_types) we can also write, by replaying the same .syx record frame the device
        # itself uses (the 2013 editor's SetSong/SetSetlist/etc. do exactly this — see
        # docs/LF_USB_DIRECT.md). Per-record types don't get a hardware ACK guarantee the way
        # the bulk-path write does, so _send_all() additionally reads each one back and compares
        # bytes before calling it a success.
        if self.WRITABLE_TYPES is None:
            self.WRITABLE_TYPES = self._read_types()
        return self.WRITABLE_TYPES

    def _read_types(self):
        if self.READ_TYPES is None:
            from ..comms import FOOT_READ_CMDS
            from ..comms.protocol import FOOT_PER_RECORD_CMDS
            self.READ_TYPES = ({rt for rt, _ in FOOT_READ_CMDS.values()}
                               | {rt for rt, _ in FOOT_PER_RECORD_CMDS.values()})
        return self.READ_TYPES

    def _send_all(self, frames):
        """Write every frame in `frames` to the device; return (written, failed) frame lists.

        Per-record types (Song/Setlist/IASwitch — see PER_RECORD_CMD_FOR_TYPE) get an extra
        readback-and-compare check: their write-frame format was inferred from the decompiled
        2013 editor (SetToSysex), not independently hardware-confirmed the way the read path
        was, so the device's F0 09 F7 ACK alone isn't treated as sufficient — a write that ACKs
        but reads back different bytes (or doesn't read back at all) counts as failed rather than
        silently reporting success on an unconfirmed write."""
        from ..comms import send_record
        from ..comms.protocol import MODEL_FOOT, PER_RECORD_CMD_FOR_TYPE, pull_one_record_per_record
        written, failed = [], []
        for f in frames:
            if f.type in PER_RECORD_CMD_FOR_TYPE:
                def verify(f=f):
                    back = pull_one_record_per_record(self.transport, f.type, f.rec_num, MODEL_FOOT)
                    return back is not None and back.to_bytes() == f.to_bytes()
                ok = send_record(self.transport, f, allow_write=True, verify_read=verify)
            else:
                ok = send_record(self.transport, f, allow_write=True)
            (written if ok else failed).append(f)
        return written, failed

    def _commit_baseline(self, frames):
        """Mark `frames` as the new 'unchanged' reference after a successful device write."""
        for f in frames:
            self._baseline[(f.type, f.rec_num)] = f.to_bytes()

    def _set_conn(self, text: str, color: str):
        """Single source of truth for the status-bar connection LED + label."""
        self.conn.setText(f"●  {text}")
        self.conn.setStyleSheet(f"color: {color}; padding-right: 10px;")

    def _set_busy(self, busy: bool, msg: str = ""):
        self._device_busy = busy   # the USB MIDI In Bridge pauses forwarding while True
        self.act_connect.setEnabled(not busy)
        self.act_from.setEnabled(not busy and self.transport is not None)
        self.act_to.setEnabled(not busy and self.transport is not None and self.dump is not None)
        if busy:
            self._set_conn(msg, AMBER)   # amber = working

    def _run_device(self, fn, on_ok, busy_msg, fail_title, wants_progress=False):
        """Run `fn` (a blocking device call) on a worker; route result to `on_ok`.

        With `wants_progress=True`, `fn` is called as `fn(emit)` where `emit(msg)` updates the
        status-bar text live (queued across threads by Qt's signal/slot mechanism) — for a call
        that can legitimately take minutes (e.g. the ~562-request per-record sweep), a static
        busy message is indistinguishable from a hang; see the 2026-07-16 forum report that
        turned out to be exactly this."""
        self._set_busy(True, busy_msg)
        task = self._task = _DeviceTask(None, self)
        task._fn = (lambda: fn(task.progress.emit)) if wants_progress else fn
        if wants_progress:
            task.progress.connect(lambda msg: self._set_conn(msg, AMBER))

        def done(result):
            self._set_busy(False)
            on_ok(result)

        def failed(message):
            self._set_busy(False)
            self._refresh_conn_label()
            QMessageBox.critical(self, fail_title, message)

        task.ok.connect(done)
        task.err.connect(failed)
        task.start()

    def _refresh_conn_label(self):
        if self.transport is not None:
            self._set_conn("connected (Editor Mode)", ACCENT)
        else:
            self._set_conn("not connected", RED)

    # --- record-change tracking (for "push my edits") ---
    def _snapshot_baseline(self):
        """Remember each record's bytes so we can tell which ones the user edited."""
        self._baseline = {(f.type, f.rec_num): f.to_bytes() for f in self.dump.frames}

    def _changed_writable(self):
        """Frames the user edited since the last load/read, limited to USB-writable types."""
        base = getattr(self, "_baseline", {})
        writable = self._writable_types()
        out = []
        for f in self.dump.frames:
            if f.type in writable and f.to_bytes() != base.get((f.type, f.rec_num)):
                out.append(f)
        return out

    def toggle_connect(self):
        if self.transport is not None:
            return self.disconnect_device()
        self.connect_device()

    def connect_device(self):
        """Open the USB-serial link and handshake into Editor Mode (see docs/LF_USB_DIRECT.md)."""
        from ..comms import find_serial_ports, SerialTransport, connect, MODEL_FOOT
        # A running USB MIDI In Bridge holds the port raw — release it for the editor session.
        bridge = getattr(self, "_midi_bridge", None)
        if bridge is not None and bridge.running:
            bridge.stop()
        ports = find_serial_ports()
        if not ports:
            QMessageBox.warning(self, "Connect", "No USB-serial device found.\n\n"
                                "Plug in the Liquid Foot+ (its FTDI port must be at PID 0x6015).")
            return
        port = ports[0].name

        def work():
            t = SerialTransport(port)
            return t, connect(t, MODEL_FOOT)

        def ok(result):
            t, reply = result
            if not reply:
                t.close()
                self._refresh_conn_label()
                QMessageBox.warning(self, "Connect", "No handshake reply — the device didn't "
                                    "enter Editor Mode. Unplug/replug and try again (don't "
                                    "reconnect too fast).")
                return
            self.transport = t
            self.act_connect.setText("Disconnect")
            self.act_from.setEnabled(True)
            self.act_to.setEnabled(self.dump is not None)
            self._set_conn(f"connected — {os.path.basename(port)} (Editor Mode)", ACCENT)

        self._run_device(work, ok, f"connecting to {os.path.basename(port)}…", "Connect failed")

    def disconnect_device(self):
        if self.transport is not None:
            from ..comms import disconnect, MODEL_FOOT
            disconnect(self.transport, MODEL_FOOT)   # send CC (leave Editor Mode), then close
            self.transport = None
        self.act_connect.setText("Connect")
        self.act_from.setEnabled(False)
        self.act_to.setEnabled(False)
        self._set_conn("not connected", RED)

    def pull_from_device(self):
        """Read the device's records and overlay them onto the loaded dump (or load fresh)."""
        from ..comms import pull_dump, MODEL_FOOT
        from ..comms.protocol import FOOT_PER_RECORD_CMDS
        from ..codec.frame import TYPE_NAMES
        if self.transport is None:
            return
        read_types = self._read_types()

        def work(emit):
            # Bulk types (now including Page/Song/Setlist — see FOOT_READ_CMDS) come back in
            # one shot with no per-record progress needed. The per-record fallback only runs for
            # whichever types the bulk phase didn't answer (normally just IASwitch, which has no
            # bulk command at all) — see pull_dump()'s docstring — so progress is reported per
            # type as it actually happens, not against a fixed 562-request estimate.
            def on_progress(cmd, rec_num, count):
                rtype, _count = FOOT_PER_RECORD_CMDS[cmd]
                tname = TYPE_NAMES.get(rtype, f"type{rtype}")
                if (rec_num + 1) % 25 == 0 or rec_num + 1 == count:
                    emit(f"reading device… {tname} ({rec_num + 1}/{count})")
            return pull_dump(self.transport, MODEL_FOOT, on_progress=on_progress)

        def ok(dev):
            if self.dump is None:
                self.dump = dev
                note = "Loaded device records, including Songs/Set-Lists/IA-Switches/Pages."
            else:
                by_key = {(f.type, f.rec_num): f for f in dev.frames}
                for i, f in enumerate(self.dump.frames):
                    repl = by_key.get((f.type, f.rec_num))
                    if repl is not None:
                        self.dump.frames[i] = repl
                note = (f"Overlaid {len(dev.frames)} device records onto the loaded backup "
                        f"(types {sorted(read_types)}).")
            for w in self.tab_widgets:
                w.set_dump(self.dump)
            self._snapshot_baseline()   # device is now the reference for "changed"
            self._dirty = False
            self._update_title()
            self._refresh_conn_label()
            QMessageBox.information(self, "From LF+", note)

        self._run_device(work, ok, "reading device…", "From LF+ failed", wants_progress=True)

    def push_to_device(self):
        """Write every record the user edited since the last load/read (gated, ACK-verified)."""
        from ..codec.frame import TYPE_NAMES
        if self.transport is None or self.dump is None:
            return
        changed = self._changed_writable()
        if not changed:
            QMessageBox.information(self, "To LF+", "No edits to push.\n\nNothing has changed in "
                                    "a USB-writable record since the last Open or From LF+.")
            return
        from collections import Counter
        by_type = Counter(TYPE_NAMES.get(f.type, f"type{f.type}") for f in changed)
        summary = ", ".join(f"{n}× {t}" for t, n in by_type.items())
        if QMessageBox.question(
            self, "Write edits to device?",
            f"Write {len(changed)} edited record(s) to the Liquid Foot+?\n\n{summary}\n\n"
            "Each write is surgical and the device ACKs it.",
        ) != QMessageBox.Yes:
            return

        frames = list(changed)

        def ok(result):
            written, failed = result
            self._commit_baseline(written)   # written records are the new baseline
            self._refresh_conn_label()
            if failed:
                names = [f"{TYPE_NAMES.get(f.type, f.type)} #{f.rec_num + 1}" for f in failed]
                QMessageBox.warning(self, "To LF+", f"Wrote {len(written)} record(s); "
                                    f"{len(failed)} not confirmed:\n" + "\n".join(names))
            else:
                QMessageBox.information(self, "To LF+", f"Wrote {len(written)} record(s) "
                                       "— all acknowledged by the device.")

        self._run_device(lambda: self._send_all(frames), ok,
                         f"writing {len(frames)} record(s)…", "To LF+ failed")

    def open_live_calibration(self):
        """Open the live expression-pedal calibration view (treadle bars + Save Calibration)."""
        if self.transport is None:
            QMessageBox.information(self, "Live Calibration",
                                    "Connect to the Liquid Foot+ first — it must be in Editor Mode.")
            return
        if self.dump is None or not self.dump.records(4):
            QMessageBox.information(self, "Live Calibration",
                                    "Open a .syx first so the calibration can be saved into the "
                                    "Config record.")
            return
        from .live_pedals import LiveCalibrationDialog
        from ..comms import write_records_live, MODEL_FOOT
        cfg0 = self.dump.records(4)[0]

        def on_save(_rec):
            # The original editor saves calibration by writing BOTH config records (#0 holds the
            # calibration; #1 is written unchanged) back-to-back DURING the live stream, after a
            # single 0xFF prelude — see comms.write_records_live. cfg0.values already has the new
            # min/max; records(4) yields #0 then #1 in dump order.
            config = self.dump.records(4)
            if not write_records_live(self.transport, [r.frame for r in config], allow_write=True):
                raise RuntimeError("the device did not acknowledge the calibration write")
            self._commit_baseline([r.frame for r in config])
            self._refresh_after_bulk_edit()
            self._refresh_conn_label()

        LiveCalibrationDialog(self, self.transport, cfg0, on_save, MODEL_FOOT).exec()

    def transfer(self, kind: str, type_: int, index: int):
        """Per-record / per-type transfer from the header buttons (To/From/All To/All From)."""
        if self.transport is None:
            QMessageBox.information(self, "Not connected",
                                   "Connect to the Liquid Foot+ first (Connect in the toolbar).")
            return
        if self.dump is None:
            return
        writable = self._writable_types()
        from ..codec.frame import TYPE_NAMES
        tname = TYPE_NAMES.get(type_, f"type{type_}")
        if kind in ("to", "all_to") and type_ not in writable:
            QMessageBox.information(self, "To LF+",
                                   f"{tname} records aren't written over USB on this device.")
            return

        if kind == "to":
            frames = [f for f in self.dump.frames if f.type == type_][index:index + 1]
        elif kind == "all_to":
            frames = [f for f in self.dump.frames if f.type == type_]
        else:
            return self._read_back(type_, index, kind)

        if not frames:
            return
        if QMessageBox.question(
            self, "Write to device?",
            f"Write {len(frames)} {tname} record(s) to the Liquid Foot+?",
        ) != QMessageBox.Yes:
            return

        def ok(result):
            written, failed = result
            self._commit_baseline(written)
            self._refresh_conn_label()
            msg = f"Wrote {len(written)} {tname} record(s)."
            if failed:
                msg += f"  {len(failed)} not confirmed."
            QMessageBox.information(self, "To LF+", msg)

        self._run_device(lambda: self._send_all(frames), ok,
                         f"writing {len(frames)} {tname}…", "To LF+ failed")

    def _read_back(self, type_: int, index: int, kind: str):
        read_types = self._read_types()
        from ..codec.frame import TYPE_NAMES
        tname = TYPE_NAMES.get(type_, f"type{type_}")
        if type_ not in read_types:
            QMessageBox.information(self, "From LF+",
                                   f"{tname} records aren't exposed over USB; edit them offline.")
            return

        def ok(dev):
            by_key = {(f.type, f.rec_num): f for f in dev.frames if f.type == type_}
            n = 0
            for i, f in enumerate(self.dump.frames):
                if f.type != type_:
                    continue
                if kind == "from" and [fr for fr in self.dump.frames if fr.type == type_].index(f) != index:
                    continue
                repl = by_key.get((f.type, f.rec_num))
                if repl is not None:
                    self.dump.frames[i] = repl
                    n += 1
            for w in self.tab_widgets:
                w.set_dump(self.dump)
            self._snapshot_baseline()
            QMessageBox.information(self, "From LF+", f"Read {n} {tname} record(s) from the device.")

        from ..codec import Dump
        from ..comms import pull_dump, MODEL_FOOT
        from ..comms.protocol import (
            PER_RECORD_CMD_FOR_TYPE, READ_CMD_FOR_TYPE, pull_one_record_per_record,
            pull_records_per_record,
        )
        if type_ in PER_RECORD_CMD_FOR_TYPE and type_ not in READ_CMD_FOR_TYPE:
            # Song/Setlist/IASwitch all have per-record commands, but since each also has a
            # cheaper bulk equivalent now (0x08/0x09/0x06 — see FOOT_READ_CMDS), this branch is
            # normally unreachable in practice; it stays as a defensive fallback for a type that
            # somehow loses its bulk command on a given device/firmware.
            if kind == "from":
                rec_num = [f for f in self.dump.frames if f.type == type_][index].rec_num

                def work(_emit):
                    fr = pull_one_record_per_record(self.transport, type_, rec_num, MODEL_FOOT)
                    return Dump(frames=[fr] if fr else [])
            else:
                cmd = PER_RECORD_CMD_FOR_TYPE[type_]

                def work(emit):
                    def on_progress(_cmd, rec_num, count):
                        if (rec_num + 1) % 25 == 0 or rec_num + 1 == count:
                            emit(f"reading {tname}… ({rec_num + 1}/{count})")
                    return Dump(frames=pull_records_per_record(
                        self.transport, MODEL_FOOT, cmds=[cmd], on_progress=on_progress))
        else:
            cmd = READ_CMD_FOR_TYPE.get(type_)
            cmds = [cmd] if cmd is not None else None

            def work(_emit):
                return pull_dump(self.transport, MODEL_FOOT, cmds=cmds, per_record=False)

        self._run_device(work, ok, f"reading {tname}…", "From LF+ failed", wants_progress=True)

    # --- file ops ---
    def open_file(self):
        start = os.path.join(os.path.dirname(__file__), "..", "..", "reference", "sysex_dumps")
        path, _ = QFileDialog.getOpenFileName(self, "Open LF+ backup", start, "Sysex (*.syx)")
        if path:
            self.load(path)

    def load(self, path: str):
        try:
            self.dump = Dump.from_file(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self.path = path
        self._dirty = False
        for w in self.tab_widgets:
            w.set_dump(self.dump)
        self._sync_qlist()
        self._snapshot_baseline()  # edits are tracked relative to the freshly-loaded file
        if self.transport is not None:
            self.act_to.setEnabled(True)
        c = self.dump.counts()
        self.status.setText(
            f"{os.path.basename(path)}  —  "
            + "  ".join(f"{v} {k}" for k, v in c.items() if k in
                        ("Preset", "Song", "Setlist", "Page", "IASwitch", "IAMap", "SysexMsg"))
        )
        self._update_title()

    def _confirm_discard(self) -> bool:
        """Return True if it's OK to replace the open document (no unsaved changes, or user OK)."""
        if not self._dirty:
            return True
        return QMessageBox.question(
            self, "Discard changes?",
            "The open document has unsaved changes. Replace it anyway?",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Yes

    def load_factory(self, filename: str, label: str):
        from ..resources import factory_path
        if not self._confirm_discard():
            return
        path = factory_path(filename)
        if not os.path.exists(path):
            QMessageBox.critical(self, "Factory defaults missing",
                                 f"Bundled factory file not found:\n{path}")
            return
        self.load(path)
        # treat as a fresh untitled document so the user can't overwrite the bundled file
        self.path = None
        self._dirty = True
        self._update_title()
        self.status.setText(f"Loaded factory defaults — {label}  (save as a new backup)")

    def clear_labels(self, rtype: int, what: str):
        if not self.dump:
            return
        recs = self.dump.records(rtype)
        if not recs:
            QMessageBox.information(self, "Nothing to clear", f"No records hold {what}.")
            return
        if QMessageBox.warning(
                self, f"Clear {what}?",
                f"This blanks all {what} in the open document ({len(recs)} records). "
                "Save, or use To LF+, to apply it to the device. Continue?",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        for rec in recs:
            for i in range(getattr(rec, "count", 0)):
                rec.set_label(i, "")
        for w in self.tab_widgets:
            w.set_dump(self.dump)
        self.mark_dirty()
        self.status.setText(f"Cleared {what} in {len(recs)} records")

    # --- whole-record copy / paste / clear (toolbar, mirrors the original) ---
    def _active_record_tab(self):
        """The current tab if it supports whole-record ops, else None."""
        tab = self.tabs.currentWidget()
        if hasattr(tab, "current_record") and hasattr(tab, "reload_current"):
            return tab
        return None

    def copy_record(self):
        if not self.dump:
            return
        tab = self._active_record_tab()
        rec = tab.current_record() if tab else None
        if rec is None:
            self.status.setText("Nothing to copy on this tab")
            return
        from .record_ops import snapshot, TYPE_SINGULAR
        self._record_clip = snapshot(self.dump, rec, tab.current_type())
        self.act_paste.setEnabled(True)
        label = TYPE_SINGULAR.get(tab.current_type(), "record")
        self.status.setText(f"Copied {label} #{rec.number} — paste over another {label}")

    def paste_record(self):
        if not self.dump or self._record_clip is None:
            return
        tab = self._active_record_tab()
        rec = tab.current_record() if tab else None
        if rec is None:
            return
        from .record_ops import apply_paste, can_paste, TYPE_SINGULAR
        if not can_paste(self._record_clip, rec, tab.current_type()):
            want = TYPE_SINGULAR.get(self._record_clip.type_, "record")
            QMessageBox.information(
                self, "Paste",
                f"The copied item is a {want}. Select a {want} record to paste it.")
            return
        apply_paste(self.dump, rec, tab.current_type(), self._record_clip)
        tab.reload_current()
        self.mark_dirty()
        label = TYPE_SINGULAR.get(tab.current_type(), "record")
        self.status.setText(f"Pasted into {label} #{rec.number}")

    def clear_record(self):
        if not self.dump:
            return
        tab = self._active_record_tab()
        rec = tab.current_record() if tab else None
        if rec is None:
            self.status.setText("Nothing to clear on this tab")
            return
        from .record_ops import reset_record, TYPE_SINGULAR
        label = TYPE_SINGULAR.get(tab.current_type(), "record")
        if QMessageBox.warning(
                self, "Clear record?",
                f"Reset {label} #{rec.number} to its default (name, commands and states)? "
                "This can't be undone.",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        reset_record(self.dump, rec, tab.current_type())
        tab.reload_current()
        self.mark_dirty()
        self.status.setText(f"Cleared {label} #{rec.number}")

    # --- CSV import / export / reports ---
    def export_records(self, kind: str, label: str):
        if not self.dump:
            return
        from ..csvio import export_csv
        path, _ = QFileDialog.getSaveFileName(self, f"Export {label} to CSV",
                                              f"{label}.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            n = export_csv(self.dump, kind, path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.status.setText(f"Exported {n} {label} record(s) → {os.path.basename(path)}")

    def import_records(self, kind: str, label: str):
        if not self.dump:
            QMessageBox.information(self, "Import", "Open a .syx file first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, f"Import {label} from CSV", "", "CSV (*.csv)")
        if not path:
            return
        from ..csvio import import_csv
        try:
            applied, warnings = import_csv(self.dump, kind, path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        if applied:
            for w in self.tab_widgets:
                w.set_dump(self.dump)
            self.mark_dirty()
        msg = f"Imported {applied} {label} record(s) from {os.path.basename(path)}."
        if warnings:
            msg += f"\n\n{len(warnings)} row(s) skipped:\n" + "\n".join(warnings[:12])
            if len(warnings) > 12:
                msg += f"\n… and {len(warnings) - 12} more."
            QMessageBox.warning(self, "Import — with warnings", msg)
        else:
            QMessageBox.information(self, "Import complete", msg)
        self.status.setText(f"Imported {applied} {label} record(s)")

    def save_report(self, kind: str, label: str):
        if not self.dump:
            return
        from ..csvio import write_report
        path, _ = QFileDialog.getSaveFileName(self, f"{label} report",
                                              f"{label} report.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            write_report(self.dump, kind, path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Report failed", str(exc))
            return
        self.status.setText(f"Wrote {label} report → {os.path.basename(path)}")

    # --- Find / Q-LIST ---
    TYPE_TO_TAB = {1: "Presets", 2: "Songs", 3: "IA-Slot", 5: "Set-List",
                   6: "Sysex Msgs", 7: "Pages", 8: "IA-Maps"}
    TAB_TO_TYPE = {v: k for k, v in TYPE_TO_TAB.items()}

    def _sync_qlist(self):
        """Point the Q-LIST at the current tab's record type (or empty for non-record tabs)."""
        name = self.tabs.tabText(self.tabs.currentIndex())
        self.qlist.show_type(self.TAB_TO_TYPE.get(name))

    def _qlist_pick_type(self, type_: int):
        """A Q-LIST type button was clicked — switch to that type's tab."""
        name = self.TYPE_TO_TAB.get(type_)
        if name in TAB_ORDER:
            self.tabs.setCurrentIndex(TAB_ORDER.index(name))

    def _ensure_find_dialog(self):
        if self._find_dialog is None:
            from .find_dialog import FindDialog
            self._find_dialog = FindDialog(self, lambda: self.dump, self.reveal)
        return self._find_dialog

    def open_find(self):
        d = self._ensure_find_dialog()
        d.show()
        d.raise_()
        d.activateWindow()

    def toggle_qlist(self, on: bool):
        """The Q-LIST toggle: show/hide the left-side quick-pick dock."""
        if on:
            self._sync_qlist()
            self.qlist.show()
            self.qlist.raise_()
        else:
            self.qlist.hide()

    def reveal(self, type_: int, number: int):
        """Select the tab + record for a Find result (number is 1-based record number)."""
        name = self.TYPE_TO_TAB.get(type_)
        if name is None or name not in TAB_ORDER:
            return
        idx = TAB_ORDER.index(name)
        self.tabs.setCurrentIndex(idx)
        tab = self.tab_widgets[idx]
        recs = getattr(tab, "_records", [])
        for i, rec in enumerate(recs):
            if rec.number == number:
                if hasattr(tab, "_goto"):
                    tab._goto(i)
                return

    def _about(self):
        from .about_dialog import AboutDialog
        AboutDialog(self).exec()

    def save_file(self):
        if not self.dump:
            return
        if not self.path:
            return self.save_as()
        self.dump.to_file(self.path)
        self._dirty = False
        self._update_title()

    def save_as(self):
        if not self.dump:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save backup", self.path or "backup.syx",
                                              "Sysex (*.syx)")
        if path:
            self.dump.to_file(path)
            self.path = path
            self._dirty = False
            self._update_title()

    # --- dirty tracking ---
    def mark_dirty(self):
        self._dirty = True
        self._update_title()

    def _update_title(self):
        name = os.path.basename(self.path) if self.path else "untitled"
        star = "•" if self._dirty else ""
        self.setWindowTitle(f"LF+ Editor (native, emulates v6.31) — {name} {star}")

    def closeEvent(self, event):
        if self.transport is not None:
            from ..comms import disconnect, MODEL_FOOT
            disconnect(self.transport, MODEL_FOOT)   # leave Editor Mode, then close
            self.transport = None
        super().closeEvent(event)


def _selftest() -> int:
    """Headless smoke test of the *packaged* app: build the window, load a bundled factory
    file (the only data shipped in a frozen build), confirm the tabs populated, and exit.

    Run by CI against each freshly-built binary (`LFPlusEditor --selftest`) so a broken bundle —
    a missing hidden import or un-bundled resource — fails loudly instead of only at a user's
    first launch. Returns a process exit code (0 = OK)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from ..resources import FACTORY_DEFAULTS, factory_path
        app = QApplication.instance() or QApplication([])
        from .theme import build_stylesheet
        app.setStyleSheet(build_stylesheet())
        win = MainWindow()
        win.load(factory_path(FACTORY_DEFAULTS[0][1]))   # bundled, always present
        assert win.dump is not None, "factory file did not load"
        assert win.dump.counts().get("Preset", 0) > 0, "no presets decoded"
        assert len(win.tab_widgets) == len(TAB_ORDER), "not every tab was built"
        from .. import __version__
        print(f"selftest OK — LF+ Editor (native) {__version__}, "
              f"{win.dump.counts().get('Preset', 0)} presets, {len(win.tab_widgets)} tabs")
        return 0
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"selftest FAILED: {exc}")
        return 1


def main():
    import sys
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(_selftest())
    app = QApplication.instance() or QApplication([])
    from .theme import build_stylesheet
    app.setStyleSheet(build_stylesheet())
    win = MainWindow()
    # Convenience: auto-load a dump if its path is passed or the sample exists.
    sample = os.path.join(os.path.dirname(__file__), "..", "..",
                          "reference", "sysex_dumps", "RJM.syx")
    if len(sys.argv) > 1 and sys.argv[1].endswith(".syx"):
        win.load(sys.argv[1])
    elif os.path.exists(sample):
        win.load(os.path.abspath(sample))
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
