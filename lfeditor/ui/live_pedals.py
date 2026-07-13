"""
Live expression-pedal calibration — the original editor's "Live View" with treadle bars.

When connected, the device streams each pedal's raw ADC position (FE-delimited 8-byte frames,
4×16-bit big-endian — confirmed on a real LF+ 12+, see comms/protocol.parse_live_positions). This
dialog starts that stream (control D2), shows a live bar per pedal, records the swept min/max, and
can write the calibration back to Config record #0 (value[17:33]) via the gated device write.

Storage note: the *stream* is big-endian, but the *stored* calibration in the config record is
little-endian (value[17+2p] low / value[18+2p] high). MAX (toe) lives at value[17+2p], MIN (heel)
at value[25+2p].
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QWidget, QMessageBox,
)

from ..comms.protocol import (
    live_view_start_frame, parse_live_positions, NUM_PEDALS, MODEL_FOOT, LIVE_DELIM,
    exit_frame, session_frame,
)
from ..model.expedal import CALIBRATION_MAX_OFF, CALIBRATION_MIN_OFF
from .theme import GREEN, RED, PANEL_LIGHT, BORDER, TEXT_DIM

ADC_FULL = 1023   # 10-bit pedal ADC


class _LiveReader(QThread):
    """Streams live pedal positions off the device on a background thread.

    Confirmed against the original editor's traffic: **one** `D2` makes the device stream FE frames
    **continuously** — we send it once, then just read. To stop we send `CC` then `CA` (leave the
    live view, re-begin the session) exactly like the original; that halts the stream and keeps the
    link in Editor Mode. (Re-sending `D2` in a loop floods the device and wedges the serial link.)"""
    positions = Signal(list)   # [p0, p1, p2, p3] raw ADC
    failed = Signal(str)

    def __init__(self, transport, model=MODEL_FOOT):
        super().__init__()
        self._t = transport
        self._model = model
        self._run = True
        self._ended = False

    def run(self):
        try:
            self._t.send(live_view_start_frame(self._model))   # start the continuous stream (once)
            leftover = b""
            while self._run:
                chunks = self._t.read_raw(idle_timeout=0.04, overall_timeout=0.3)
                if not chunks:
                    continue
                frames, leftover = parse_live_positions(leftover + b"".join(chunks))
                if frames:
                    self.positions.emit(frames[-1])       # the most recent position
                if len(leftover) > 64:                    # resync to the last delimiter
                    cut = leftover.rfind(bytes([LIVE_DELIM]))
                    leftover = leftover[cut:] if cut >= 0 else b""
        except Exception as exc:        # noqa: BLE001 — surface device errors to the UI
            self.failed.emit(str(exc))

    def pause(self):
        """Stop the read loop only — send NO device commands. The device keeps streaming.

        This is what we do before writing the calibration: the original editor writes the config
        *during* the active live stream (the write itself interrupts the stream and the device ACKs
        with ``F0 09 F7``). Stopping the stream first (CC/CA) leaves the device unable to ACK a
        config write, which was why Save Calibration failed."""
        self._run = False
        self.wait(800)

    def end_stream(self):
        """Stop streaming the original's way — `CC` (leave live view), drain the device's final
        flush burst, then `CA` (re-begin session) — so the link stays in Editor Mode and the next
        disconnect is clean. Only called when the dialog closes."""
        self.pause()
        if self._ended:
            return
        self._ended = True
        import time
        try:
            self._t.send(exit_frame(self._model))      # CC — leave live view
            # the device flushes a final stream burst after CC; drain until the line goes quiet,
            # otherwise that backlog swamps the disconnect.
            t0 = time.time()
            while time.time() - t0 < 3.0:
                if not self._t.read_raw(idle_timeout=0.15, overall_timeout=0.3):
                    break                                # quiet — stream has stopped
            self._t.send(session_frame(self._model))   # CA — re-begin the editor session
            self._t.read_raw(idle_timeout=0.15, overall_timeout=0.3)
            flush = getattr(self._t, "flush_input", None)
            if flush:
                flush()
        except Exception:               # noqa: BLE001
            pass


class _TreadleBar(QWidget):
    """One pedal's live position as a filling bar, with min/max sweep markers."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(54, 180)
        self.pos = 0
        self.lo = None   # swept min
        self.hi = None   # swept max

    def update_pos(self, value: int):
        self.pos = value
        self.lo = value if self.lo is None else min(self.lo, value)
        self.hi = value if self.hi is None else max(self.hi, value)
        self.update()

    def reset(self):
        self.lo = self.hi = None
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        track = self.rect().adjusted(w // 2 - 9, 6, -(w // 2 - 9), -6)
        p.setPen(QColor(BORDER)); p.setBrush(QColor(PANEL_LIGHT)); p.drawRoundedRect(track, 4, 4)
        frac = max(0.0, min(1.0, self.pos / ADC_FULL))
        fh = int(track.height() * frac)
        fill = track.adjusted(2, track.height() - fh + 2, -2, -2)
        p.setPen(Qt.NoPen); p.setBrush(QColor(GREEN)); p.drawRoundedRect(fill, 3, 3)
        # swept min/max markers
        p.setPen(QColor(RED))
        for mark in (self.lo, self.hi):
            if mark is not None:
                y = track.bottom() - int(track.height() * max(0.0, min(1.0, mark / ADC_FULL)))
                p.drawLine(track.left() - 3, y, track.right() + 3, y)


class LiveCalibrationDialog(QDialog):
    """Live treadle bars + sweep-capture + Save Calibration (gated write)."""

    def __init__(self, parent, transport, config_rec, on_save, model=MODEL_FOOT):
        super().__init__(parent)
        self.setWindowTitle("Live Pedal Calibration")
        self._t = transport
        self._cfg = config_rec        # Config record #0 (its .values gets the calibration)
        self._on_save = on_save       # (config_rec) -> push to device + mark dirty
        self._model = model

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Sweep each pedal heel↔toe; the bar shows the live position and the "
                              "red marks the swept range. Then Save Calibration."))
        grid = QGridLayout()
        self.bars: list[_TreadleBar] = []
        self.readouts: list[QLabel] = []
        for i in range(NUM_PEDALS):
            cap = QLabel(f"Pedal {i + 1}"); cap.setAlignment(Qt.AlignCenter)
            bar = _TreadleBar()
            ro = QLabel("—"); ro.setAlignment(Qt.AlignCenter); ro.setStyleSheet(f"color:{TEXT_DIM};")
            grid.addWidget(cap, 0, i)
            grid.addWidget(bar, 1, i, alignment=Qt.AlignHCenter)
            grid.addWidget(ro, 2, i)
            self.bars.append(bar); self.readouts.append(ro)
        root.addLayout(grid)

        btns = QHBoxLayout()
        self.btn_reset = QPushButton("Reset sweep"); self.btn_reset.clicked.connect(self._reset)
        self.btn_save = QPushButton("Save Calibration"); self.btn_save.setObjectName("xfer")
        self.btn_save.clicked.connect(self._save)
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        btns.addWidget(self.btn_reset); btns.addStretch(1)
        btns.addWidget(self.btn_save); btns.addWidget(close)
        root.addLayout(btns)

        self._reader = None
        self._start_reader()

    def _start_reader(self):
        """(Re)open the live stream on a fresh reader thread (a QThread can't be restarted)."""
        self._reader = _LiveReader(self._t, self._model)
        self._reader.positions.connect(self._on_positions)
        self._reader.failed.connect(self._on_fail)
        self._reader.start()

    def _on_positions(self, pos: list[int]):
        for i in range(min(NUM_PEDALS, len(pos))):
            self.bars[i].update_pos(pos[i])
            b = self.bars[i]
            self.readouts[i].setText(f"{pos[i]}  ({b.lo}–{b.hi})")

    def _on_fail(self, msg: str):
        QMessageBox.warning(self, "Live View", f"Live stream stopped:\n{msg}")

    def _reset(self):
        for b in self.bars:
            b.reset()

    def _save(self):
        # only write pedals that actually saw a usable sweep; leave the rest (no pedal connected /
        # not moved) at their stored calibration — mirrors the original's per-pedal calibrate.
        usable = [i for i, b in enumerate(self.bars)
                  if b.lo is not None and b.hi is not None and b.hi - b.lo >= 8]
        if not usable:
            QMessageBox.information(self, "Save Calibration",
                                    "Sweep at least one pedal heel→toe before saving.")
            return
        names = ", ".join(f"#{i + 1}" for i in usable)
        if QMessageBox.question(
                self, "Save Calibration",
                f"Write the swept min/max for pedal(s) {names} to the device?\n\n"
                "This overwrites the stored calibration for those pedals only.",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        # Write the calibration DURING the active live stream — do NOT send CC/CA first. We only
        # pause our read loop (so it doesn't race the write for the serial port); the device is
        # still streaming. send_record flushes stale RX, writes the config, and the write itself
        # interrupts the stream so the device ACKs (F0 09 F7) — exactly how the original editor
        # does it. Stopping the stream beforehand left the device unable to ACK.
        self._reader.pause()
        v = self._cfg.values
        for i in usable:
            lo, hi = self.bars[i].lo, self.bars[i].hi
            v[CALIBRATION_MAX_OFF + 2 * i] = hi & 0xFF
            v[CALIBRATION_MAX_OFF + 2 * i + 1] = (hi >> 8) & 0xFF
            v[CALIBRATION_MIN_OFF + 2 * i] = lo & 0xFF
            v[CALIBRATION_MIN_OFF + 2 * i + 1] = (lo >> 8) & 0xFF
        try:
            self._on_save(self._cfg)
        except Exception as exc:        # noqa: BLE001
            QMessageBox.critical(self, "Save Calibration", f"Write failed:\n{exc}")
            self._start_reader()        # resume the bars so the user can retry
            return
        QMessageBox.information(self, "Save Calibration", "Calibration written to the device.")
        self._start_reader()            # the write stopped the stream; restart it for more sweeps

    def closeEvent(self, e):
        if self._reader:
            self._reader.end_stream()
        super().closeEvent(e)

    def accept(self):
        if self._reader:
            self._reader.end_stream()
        super().accept()
