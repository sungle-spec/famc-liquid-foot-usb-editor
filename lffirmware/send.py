"""The send engine: one sysex, one shot, fully logged.

The 2013 FAMC editor sent a firmware image as a single javax.sound.midi SysexMessage with no
app-level chunking or ACK (decompiled MidiFootController.SendFirmwareSysexFile) — the MIDI
interface/driver does the pacing, and the device-side DIN link is the fixed 31.25 kbaud
bottleneck (~250 KB ≈ 80–110 s). We reproduce exactly that, plus everything the original never
did: image verification first, sleep inhibition during the send, and a timestamped session log.
"""
from __future__ import annotations

import datetime
import pathlib
import platform
import subprocess
import sys
import time
from contextlib import contextmanager

from . import __version__
from .images import ImageReport

MIDI_DIN_BYTES_PER_SEC = 31250 / 10  # 31.25 kbaud, 10 bits per byte on the wire


def list_ports() -> list[str]:
    import mido
    return list(dict.fromkeys(mido.get_output_names()))


def estimate_seconds(size: int) -> float:
    return size / MIDI_DIN_BYTES_PER_SEC


@contextmanager
def inhibit_sleep():
    """Keep the machine awake for the duration of the send. A sleeping laptop mid-flash is a
    guaranteed brick — fight it on every OS, best-effort."""
    system = platform.system()
    proc = None
    old_state = None
    try:
        if system == "Darwin":
            proc = subprocess.Popen(["caffeinate", "-dimsu"])
        elif system == "Windows":
            import ctypes
            ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2
            old_state = ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
        elif system == "Linux":
            try:
                proc = subprocess.Popen(
                    ["systemd-inhibit", "--what=sleep:idle",
                     "--why=LF+ firmware flash in progress", "sleep", "infinity"])
            except FileNotFoundError:
                pass
        yield
    finally:
        if proc:
            proc.terminate()
        if old_state is not None:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


class SessionLog:
    """Timestamped log file — remote testers send this back for analysis."""

    def __init__(self, log_dir: str | pathlib.Path | None = None):
        d = pathlib.Path(log_dir) if log_dir else pathlib.Path.home() / "LFFirmwareLoader-logs"
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = d / f"lffirmware-{stamp}.log"
        self._f = self.path.open("w")
        self.write(f"LF+ Firmware Loader {__version__} — {platform.platform()} "
                   f"python {sys.version.split()[0]}")

    def write(self, line: str) -> None:
        stamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self._f.write(f"[{stamp}] {line}\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()


def send_firmware(port_name: str, image: bytes, rep: ImageReport, log: SessionLog,
                  on_progress=None, listen_for_replies: bool = True) -> dict:
    """Stream the image to `port_name` as one sysex message (the 2013-editor way).

    Returns a result dict (also fully logged). `on_progress(elapsed, estimated)` is called from
    a ticker while the blocking send runs in this thread — call send_firmware itself from a
    worker thread if you need a live UI.
    """
    import threading

    import mido

    est = estimate_seconds(len(image))
    log.write(f"image: {rep.path}")
    log.write(f"sha256={rep.sha256} size={rep.size} "
              f"identity={'KNOWN ' + str(rep.known_model) + ' v' + str(rep.known_version) if rep.is_known_good else 'UNVERIFIED'}")
    log.write(f"port: {port_name!r}; estimated DIN transfer time {est:.0f}s")

    inp = None
    replies: list[bytes] = []
    if listen_for_replies:
        # If the same interface has an input side, record anything the device says.
        try:
            in_names = [n for n in mido.get_input_names() if n.split(":")[0] == port_name.split(":")[0]]
            if in_names:
                inp = mido.open_input(in_names[0])
                log.write(f"listening on input: {in_names[0]!r}")
        except Exception as exc:  # noqa: BLE001 — reply capture is best-effort
            log.write(f"no input listener: {exc}")

    out = mido.open_output(port_name)
    msg = mido.Message("sysex", data=list(image[1:-1]))

    stop = threading.Event()

    def _tick():
        t0 = time.monotonic()
        while not stop.is_set():
            if on_progress:
                on_progress(time.monotonic() - t0, est)
            stop.wait(0.5)

    ticker = threading.Thread(target=_tick, daemon=True)
    ticker.start()
    log.write("SEND begin (single sysex message — do not disconnect or power off)")
    t0 = time.monotonic()
    try:
        with inhibit_sleep():
            time.sleep(0.02)  # the 2013 editor's 20 ms pre-send settle
            out.send(msg)
            elapsed = time.monotonic() - t0
            log.write(f"SEND returned after {elapsed:.1f}s (driver may still be draining "
                      f"its buffer — keep everything connected)")
            # Give the interface time to drain + the device time to start replying/flashing.
            settle = max(5.0, est - elapsed + 10.0)
            log.write(f"settle wait {settle:.0f}s")
            deadline = time.monotonic() + settle
            while time.monotonic() < deadline:
                if inp is not None:
                    m = inp.poll()
                    if m is not None:
                        raw = bytes(m.bytes())
                        replies.append(raw)
                        log.write(f"device reply: {raw.hex(' ')}")
                        continue
                time.sleep(0.05)
    finally:
        stop.set()
        ticker.join(timeout=1)
        out.close()
        if inp is not None:
            inp.close()

    total = time.monotonic() - t0
    log.write(f"SEND complete — total {total:.1f}s, {len(replies)} device replies")
    log.write("now watch the device: it should program itself and restart (manual p.90)")
    return {"seconds": total, "replies": [r.hex(" ") for r in replies], "log": str(log.path)}
