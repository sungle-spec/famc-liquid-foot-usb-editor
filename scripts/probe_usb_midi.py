#!/usr/bin/env python3
"""
Probe: does the LF+ treat its USB-serial link as a live MIDI stream?

Two questions, prompted by forum feedback asking for the original "USB MIDI function"
(the FAMC driver used to present the FTDI USB as a CoreMIDI port) and for MIDI-clock
sync of the tempo LED over USB:

  1. CLOCK IN — if we stream MIDI realtime clock (0xF8, 24 ppqn) down the UART, does the
     tempo LED lock to it?  Tried both inside Editor Mode and after leaving it.
  2. MIDI OUT — outside Editor Mode, does the device emit MIDI (PC/CC from button presses)
     on the UART unprompted?  If yes, the UART is a bidirectional MIDI stream and a full
     virtual-MIDI-port bridge is feasible.

Non-destructive: realtime bytes and listening only — nothing writes device memory. The
Editor-Mode handshake is reversible (script sends the CC exit control when done).

    python scripts/probe_usb_midi.py                 # full run, interactive prompts
    python scripts/probe_usb_midi.py --bpm 100 --seconds 15
"""
import argparse
import glob
import sys
import time
from datetime import datetime
from pathlib import Path

MODEL_FOOT = 0x7C
BAUD = 230400
ART = Path(__file__).resolve().parent / "ARTIFACTS"

MIDI_CLOCK = 0xF8
MIDI_START = 0xFA
MIDI_STOP = 0xFC

log_lines = []


def log(s=""):
    print(s)
    log_lines.append(s)


def msg(*body):
    return bytes([0xF0, 0x00, 0x00, MODEL_FOOT, *body, 0xF7])


def handshake():
    return msg(0x0F, 0x0F, 0xC9, 0x00, 0x00, 0x00, 0x00)


def exit_editor():
    return msg(0x0F, 0x0F, 0xCC)


def find_port():
    ports = glob.glob("/dev/cu.usbserial-*")
    return ports[0] if ports else None


def open_serial(port, settle=0.3):
    import serial
    ser = serial.Serial(port, BAUD, timeout=0.05)
    ser.dtr = True
    ser.rts = True
    time.sleep(settle)
    ser.reset_input_buffer()
    return ser


def stream_clock(ser, bpm, seconds, label):
    """Send Start, then 0xF8 at 24 ppqn for `seconds`, then Stop. Logs any RX bytes."""
    interval = 60.0 / (bpm * 24)
    ticks = int(seconds / interval)
    log(f"\n== {label}: streaming MIDI clock {bpm} BPM ({ticks} ticks over ~{seconds}s) ==")
    log("   WATCH THE TEMPO LED — starting in 3s...")
    time.sleep(3)
    rx = bytearray()
    ser.reset_input_buffer()
    ser.write(bytes([MIDI_START]))
    t_next = time.time()
    for _ in range(ticks):
        ser.write(bytes([MIDI_CLOCK]))
        n = ser.in_waiting
        if n:
            rx.extend(ser.read(n))
        t_next += interval
        delay = t_next - time.time()
        if delay > 0:
            time.sleep(delay)
    ser.write(bytes([MIDI_STOP]))
    ser.flush()
    time.sleep(0.3)
    n = ser.in_waiting
    if n:
        rx.extend(ser.read(n))
    log(f"   sent {ticks} clock ticks; device sent back {len(rx)} bytes"
        + (f": {bytes(rx[:32]).hex(' ')}{' ...' if len(rx) > 32 else ''}" if rx else ""))
    return bytes(rx)


def listen(ser, seconds, label):
    log(f"\n== {label}: listening {seconds}s for device-originated bytes ==")
    log("   PRESS BUTTONS / SWITCH PRESETS on the LF+ now — listening in 3s...")
    time.sleep(3)
    rx = bytearray()
    t0 = time.time()
    ser.reset_input_buffer()
    while time.time() - t0 < seconds:
        n = ser.in_waiting
        chunk = ser.read(n if n else 1)
        if chunk:
            rx.extend(chunk)
    log(f"   received {len(rx)} bytes"
        + (f": {bytes(rx[:64]).hex(' ')}{' ...' if len(rx) > 64 else ''}" if rx else " (silence)"))
    return bytes(rx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bpm", type=int, default=120)
    ap.add_argument("--seconds", type=float, default=10.0)
    args = ap.parse_args()

    port = find_port()
    if not port:
        print("No /dev/cu.usbserial-* port — plug the LF+ in first.")
        sys.exit(2)
    ART.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log(f"probe_usb_midi  {ts}  port={port} baud={BAUD} bpm={args.bpm}")
    captures = {}

    # Phase 1: raw port, NO Editor Mode — the state the old driver would have used.
    ser = open_serial(port)
    captures["clock_raw"] = stream_clock(ser, args.bpm, args.seconds,
                                         "PHASE 1 (no Editor Mode)")
    captures["listen_raw"] = listen(ser, args.seconds, "PHASE 2 (no Editor Mode)")
    ser.close()
    time.sleep(0.5)

    # Phase 3: inside Editor Mode, then again right after leaving it on the same open port.
    ser = open_serial(port)
    ser.write(handshake()); ser.flush()
    time.sleep(0.5)
    hs = ser.read(ser.in_waiting or 1)
    log(f"\nhandshake reply: {len(hs)} bytes" + (f" [{hs[:12].hex(' ')}]" if hs else " (NONE)"))
    captures["clock_editor"] = stream_clock(ser, args.bpm, args.seconds,
                                            "PHASE 3 (Editor Mode)")
    ser.write(exit_editor()); ser.flush()
    time.sleep(0.3)
    ser.reset_input_buffer()
    captures["clock_after_exit"] = stream_clock(ser, args.bpm, args.seconds,
                                                "PHASE 4 (same port, after CC exit)")
    ser.close()

    for name, data in captures.items():
        if data:
            out = ART / f"usb_midi_{ts}_{name}.bin"
            out.write_bytes(data)
            log(f"saved {out.name} ({len(data)} bytes)")
    logfile = ART / f"usb_midi_{ts}.log"
    logfile.write_text("\n".join(log_lines) + "\n")
    print(f"\nLog -> {logfile}")
    print("\nInterpretation: LED synced in any phase -> clock-over-USB is real (gate B0a). "
          "Bytes received while pressing buttons -> UART emits MIDI (gate B0b, full bridge "
          "feasible). Neither -> the honest DIN answer (B1').")


if __name__ == "__main__":
    main()
