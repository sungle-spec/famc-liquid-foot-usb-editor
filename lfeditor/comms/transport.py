"""
Transport abstraction: send/receive raw FAMC sysex bytes over either MIDI or USB-serial.

Both transports speak the *same* sysex (see docs/LF_PROTOCOL.md); only the carrier differs.
Nothing here writes to a device on its own — the protocol layer drives it, and writes are
gated by an explicit opt-in (see protocol.py). Hardware specifics that are unconfirmed
(serial baud/handshake) are flagged; the MIDI path is the JAR-proven one.
"""
from __future__ import annotations

import time
from typing import Protocol

SYSEX_START = 0xF0
SYSEX_END = 0xF7


class Transport(Protocol):
    def send(self, data: bytes) -> None: ...
    def read_frames(self, idle_timeout: float = 1.0, overall_timeout: float = 10.0) -> list[bytes]: ...
    def read_raw(self, idle_timeout: float = 1.0, overall_timeout: float = 10.0) -> list[bytes]: ...
    def flush_input(self) -> None: ...
    def close(self) -> None: ...


def split_sysex(buf: bytes) -> list[bytes]:
    """Extract complete F0..F7 frames from a byte buffer."""
    frames, i, n = [], 0, len(buf)
    while i < n:
        if buf[i] != SYSEX_START:
            i += 1
            continue
        j = buf.find(SYSEX_END, i + 1)
        if j == -1:
            break
        frames.append(buf[i:j + 1])
        i = j + 1
    return frames


class SerialTransport:
    """USB-serial (FTDI VCP) carrier, mirroring the Liquid Router's link.

    NOTE: the LF+ serial baud and whether it needs a handshake are **unconfirmed** (the JAR
    used MIDI only). Defaults mirror the Router (230400, DTR/RTS, optional handshake frame);
    adjust once tested on hardware. `handshake` bytes default to None (no handshake)."""

    def __init__(self, port: str, baud: int = 230400, handshake: bytes | None = None):
        import serial  # lazy
        self.ser = serial.Serial(port, baud, timeout=0.2)
        self.ser.dtr = True
        self.ser.rts = True
        time.sleep(0.3)
        self.ser.reset_input_buffer()
        if handshake:
            self.ser.write(handshake)
            self.ser.flush()
            time.sleep(0.3)
            self.ser.reset_input_buffer()

    def send(self, data: bytes) -> None:
        self.ser.write(data)
        self.ser.flush()

    def _drain(self, idle_timeout: float, overall_timeout: float) -> bytes:
        buf = bytearray()
        t0 = last = time.time()
        while time.time() - t0 < overall_timeout:
            n = self.ser.in_waiting
            chunk = self.ser.read(n if n else 1)
            if chunk:
                buf.extend(chunk)
                last = time.time()
            elif buf and time.time() - last > idle_timeout:
                break
        return bytes(buf)

    def read_raw(self, idle_timeout: float = 1.0, overall_timeout: float = 10.0) -> list[bytes]:
        """Raw drained bytes (the Foot's read stream is decoded blocks, not F0..F7 frames)."""
        data = self._drain(idle_timeout, overall_timeout)
        return [data] if data else []

    def read_frames(self, idle_timeout: float = 1.0, overall_timeout: float = 10.0) -> list[bytes]:
        return split_sysex(self._drain(idle_timeout, overall_timeout))

    def flush_input(self) -> None:
        """Discard any buffered incoming bytes (e.g. trailing live-view stream before a write)."""
        try:
            self.ser.reset_input_buffer()
        except Exception:               # noqa: BLE001
            pass

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass


class MidiTransport:
    """MIDI carrier (DIN or USB-MIDI) — the device's native transport (per the 2013 JAR).
    Needs an output port for requests/writes and an input port for the streamed reply."""

    def __init__(self, out_name: str, in_name: str):
        import mido  # lazy
        self._mido = mido
        self.out = mido.open_output(out_name)
        self.inp = mido.open_input(in_name)

    def send(self, data: bytes) -> None:
        # data already includes F0..F7; mido wants the bytes between (exclusive).
        msg = self._mido.Message("sysex", data=list(data[1:-1]))
        self.out.send(msg)

    def read_frames(self, idle_timeout: float = 1.0, overall_timeout: float = 10.0) -> list[bytes]:
        frames: list[bytes] = []
        t0 = last = time.time()
        while time.time() - t0 < overall_timeout:
            msg = self.inp.poll()
            if msg is not None and msg.type == "sysex":
                frames.append(bytes([SYSEX_START, *msg.data, SYSEX_END]))
                last = time.time()
            elif frames and time.time() - last > idle_timeout:
                break
            else:
                time.sleep(0.005)
        return frames

    # Over MIDI the carrier is already frame-delimited, so raw == frames.
    def read_raw(self, idle_timeout: float = 1.0, overall_timeout: float = 10.0) -> list[bytes]:
        return self.read_frames(idle_timeout, overall_timeout)

    def flush_input(self) -> None:
        while self.inp.poll() is not None:
            pass

    def close(self) -> None:
        for p in (getattr(self, "out", None), getattr(self, "inp", None)):
            try:
                p and p.close()
            except Exception:
                pass
