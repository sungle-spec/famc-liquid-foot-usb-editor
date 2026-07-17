#!/usr/bin/env python3
"""
Probe: does the LF+ act on CHANNEL-VOICE MIDI commands arriving over the USB-serial link?

The manual's MIDI Implementation chart (last page) lists the commands the device accepts —
Bank Change (CC#0), Program Change, IA triggers (CC#1-4), Page functions (CC#5-6), MTC
(CC#7-8) — all gated behind the global "Allow MIDI in = YES". Every earlier probe ran with
that global OFF (confirmed from the 2026-07-15 backup: Config rec 0 value[47] = 0), so the
door was closed. The old FAMC CoreMIDI driver presented the USB link as a MIDI port, which
suggests the firmware may route UART channel-voice bytes into the same MIDI engine as DIN.
If it does, a "drive the LF+ from a DAW over the editor cable" bridge becomes possible.

Run in two stages around flipping the global ON THE FRONT PANEL (no editor writes needed):

    python scripts/probe_midi_cmds.py --stage control   # Allow MIDI in still NO (baseline)
    #   ...flip Global menu -> "Allow MIDI in" -> YES on the device...
    python scripts/probe_midi_cmds.py --stage open      # the real test
    #   ...flip it back to NO (or keep it; it's a performance setting)...

Each stage sends, in three link states (raw port / Editor Mode / after CC exit):
  * Bank Change CC#0 val 0 + Program Change -> preset #2, pause, then preset #1
  * IA ON trigger CC#1 val 1 (slot 1), pause, IA OFF trigger CC#2 val 1
WATCH THE LCD: a preset-number change (or an IA slot firing) in any state = gate PASSED.

Non-destructive: channel messages change the *active* preset/IA state (a front-panel button
press does the same), never stored memory. Nothing is written; Editor Mode is exited cleanly.
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

log_lines = []


def log(s=""):
    print(s)
    log_lines.append(s)


def msg(*body):
    return bytes([0xF0, 0x00, 0x00, MODEL_FOOT, *body, 0xF7])


def handshake():
    return msg(0x0F, 0x0F, 0xC9, 0x00, 0x00, 0x00, 0x00)


def session_begin():
    return msg(0x0F, 0x0F, 0xCA)


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


def rx_drain(ser, wait=0.5):
    time.sleep(wait)
    n = ser.in_waiting
    return bytes(ser.read(n)) if n else b""


def send_cmd(ser, label, data):
    ser.write(bytes(data))
    ser.flush()
    rx = rx_drain(ser)
    log(f"   {label:<28} -> {bytes(data).hex(' ')}"
        + (f"   RX {len(rx)}B: {rx[:24].hex(' ')}" if rx else ""))
    return rx


def midi_pass(ser, chan0, label):
    """One test pass on an open port. chan0 is the 0-based MIDI channel (15 = editor '16')."""
    log(f"\n== {label} ==")
    log("   WATCH THE LCD — starting in 3s...")
    time.sleep(3)
    cc, pc = 0xB0 | chan0, 0xC0 | chan0
    rx = bytearray()
    rx += send_cmd(ser, "Bank A (CC#0=0)", [cc, 0x00, 0x00])
    rx += send_cmd(ser, "PC -> preset #2", [pc, 0x01])
    time.sleep(2.0)
    rx += send_cmd(ser, "PC -> preset #1", [pc, 0x00])
    time.sleep(1.0)
    rx += send_cmd(ser, "IA ON  slot 1 (CC#1=1)", [cc, 0x01, 0x01])
    time.sleep(1.5)
    rx += send_cmd(ser, "IA OFF slot 1 (CC#2=1)", [cc, 0x02, 0x01])
    time.sleep(1.0)
    return bytes(rx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["control", "open"], required=True,
                    help="control = Allow MIDI in still NO (baseline); "
                         "open = after flipping it to YES on the front panel")
    ap.add_argument("--chan", type=int, default=16,
                    help="device global MIDI channel, 1-based (backup says 16)")
    args = ap.parse_args()
    chan0 = (args.chan - 1) & 0xF

    port = find_port()
    if not port:
        print("No /dev/cu.usbserial-* port — plug the LF+ in first.")
        sys.exit(2)
    ART.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log(f"probe_midi_cmds  {ts}  stage={args.stage}  port={port}  midi-chan={args.chan}")
    if args.stage == "control":
        log("(baseline: Allow MIDI in should still be NO — expecting no LCD reaction)")
    else:
        log("(Allow MIDI in should now be YES on the panel — the real test)")

    captures = {}

    # State 1: raw port, no Editor Mode.
    ser = open_serial(port)
    captures["raw"] = midi_pass(ser, chan0, "STATE 1: raw port (no handshake)")
    ser.close()
    time.sleep(0.5)

    # State 2: inside Editor Mode; state 3: same open port right after the CC exit control.
    ser = open_serial(port)
    ser.write(handshake()); ser.flush()
    hs = rx_drain(ser, 0.6)
    log(f"\nhandshake reply: {len(hs)} bytes" + (f" [{hs[:12].hex(' ')}]" if hs else " (NONE)"))
    ser.write(session_begin()); ser.flush()
    rx_drain(ser, 0.4)
    captures["editor"] = midi_pass(ser, chan0, "STATE 2: Editor Mode")
    ser.write(exit_editor()); ser.flush()
    time.sleep(0.3)
    ser.reset_input_buffer()
    captures["after_exit"] = midi_pass(ser, chan0, "STATE 3: same port, after CC exit")
    ser.close()

    for name, data in captures.items():
        if data:
            out = ART / f"midi_cmds_{ts}_{args.stage}_{name}.bin"
            out.write_bytes(data)
            log(f"saved {out.name} ({len(data)} bytes)")
    logfile = ART / f"midi_cmds_{ts}_{args.stage}.log"
    logfile.write_text("\n".join(log_lines) + "\n")
    print(f"\nLog -> {logfile}")
    print("\nGate: LCD changed preset / fired an IA in ANY state during the 'open' stage")
    print("-> the computer→LF+ CC/PC route is present. No reaction in all states with the")
    print("flag on means this inbound probe did not observe it; it does not test the separate")
    print("C9 → CA → CF gated LF+→computer output stream.")


if __name__ == "__main__":
    main()
