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
    """USB-serial (FTDI VCP) carrier for the hardware-confirmed LF+ link.

    The LF+ uses 230400 baud with DTR/RTS held high. Protocol handshakes are normally driven by
    ``protocol.connect``; ``handshake`` remains an optional compatibility hook.
    """

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

    def read_available(self, max_bytes: int = 4096) -> bytes:
        """Return only bytes already buffered by the serial driver, without waiting.

        Exceptions from ``in_waiting`` or ``read`` deliberately propagate so a continuously
        running bridge can detect device removal and enter its normal cleanup path. This method
        never changes DTR/RTS and never resets the input buffer.
        """
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        available = self.ser.in_waiting
        if available <= 0:
            return b""
        return bytes(self.ser.read(min(available, max_bytes)))

    def read_frames(self, idle_timeout: float = 1.0, overall_timeout: float = 10.0) -> list[bytes]:
        return split_sysex(self._drain(idle_timeout, overall_timeout))

    def read_one_frame(self, overall_timeout: float = 3.0) -> bytes:
        """Read until exactly one complete F0..F7 frame has arrived, returning IMMEDIATELY —
        no idle wait. For protocol paths where the device's reply is always exactly one bounded
        frame (the per-record read path — see protocol.py), `read_raw`'s idle-timeout drain pays
        a fixed cost on *every* request just to confirm silence after a reply that already told
        us it was complete (its own F7 terminator). At ~562 per-record requests in a full pull,
        that idle wait alone (previously 0.3s) added ~2.8 minutes versus the original editor,
        which doesn't have this tax — found 2026-07-16 investigating a "hangs on reading
        device" report that turned out to be this, not an actual device stall. Any bytes after
        the frame are left for the next read (each request/reply pair is independent)."""
        buf = bytearray()
        t0 = time.time()
        while time.time() - t0 < overall_timeout:
            n = self.ser.in_waiting
            chunk = self.ser.read(n if n else 1)
            if chunk:
                buf.extend(chunk)
                frames = split_sysex(bytes(buf))
                if frames:
                    return frames[0]
        return bytes(buf)

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

    def read_one_frame(self, overall_timeout: float = 3.0) -> bytes:
        """One sysex message, returned the instant it arrives — no idle wait after (mido
        already delivers whole messages, so there's nothing to wait for). See
        SerialTransport.read_one_frame for why this matters for the per-record read path."""
        t0 = time.time()
        while time.time() - t0 < overall_timeout:
            msg = self.inp.poll()
            if msg is not None and msg.type == "sysex":
                return bytes([SYSEX_START, *msg.data, SYSEX_END])
            time.sleep(0.005)
        return b""

    def flush_input(self) -> None:
        while self.inp.poll() is not None:
            pass

    def close(self) -> None:
        for p in (getattr(self, "out", None), getattr(self, "inp", None)):
            try:
                p and p.close()
            except Exception:
                pass
