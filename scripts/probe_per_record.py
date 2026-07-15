#!/usr/bin/env python3
"""
Probe: does the LF+ answer the 2013 editor's PER-RECORD read requests over USB-serial?

Background (docs/LF_USB_DIRECT.md): the modern bulk get-commands (F0 00 00 7C 0F 0F <X> F7)
never returned Song(2)/Setlist(5)/Page(7)/IASwitch(3), so those types are edit-offline today.
But the decompiled 2013 editor (reference/jar_decompiled/liquidfoot/MidiFootController.java,
SendMsg) requests records ONE AT A TIME with a different frame that we never tried on hardware:

    F0 00 00 <id> 00 <cmd> 02 <recnum as 4 nibbles> F7

    cmd: 0x09 sysex-msg   0x0A preset   0x0B SONG   0x0C ia-switch
         0x0D SETLIST     0x0E config   0x0F connection-test

and receives ONE nibble-encoded .syx record frame back per request. If the device still
honours that framing, Songs/Set-Lists (and maybe Pages/IA-Switches) can go over USB.

Read-only: only read requests are sent; nothing writes device memory. The handshake puts the
front panel into "Editor Mode" (reversible; this script sends the CC exit control when done).

    python scripts/probe_per_record.py            # full probe, log to scripts/ARTIFACTS/
    python scripts/probe_per_record.py --no-editor-mode   # only the raw (no handshake) pass
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

# 2013 SendMsg wire bytes (MidiFootController.java tableswitch)
PER_RECORD_CMDS = {
    "conn_test": 0x0F,
    "preset":    0x0A,   # positive control — bulk path already proves presets are readable
    "song":      0x0B,   # the prize
    "setlist":   0x0D,   # the prize
    "ia_switch": 0x0C,
    "config":    0x0E,
    "sysex_msg": 0x09,
}

log_lines = []


def log(s=""):
    print(s)
    log_lines.append(s)


def msg(*body):
    return bytes([0xF0, 0x00, 0x00, MODEL_FOOT, *body, 0xF7])


def per_record_req(cmd, recnum):
    return msg(0x00, cmd, 0x02,
               (recnum >> 12) & 0xF, (recnum >> 8) & 0xF,
               (recnum >> 4) & 0xF, recnum & 0xF)


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
    ser = serial.Serial(port, BAUD, timeout=0.2)
    ser.dtr = True
    ser.rts = True
    time.sleep(settle)
    ser.reset_input_buffer()
    return ser


def drain(ser, idle=0.8, maxwait=4.0):
    buf = bytearray()
    t0 = last = time.time()
    while time.time() - t0 < maxwait:
        n = ser.in_waiting
        chunk = ser.read(n if n else 1)
        if chunk:
            buf.extend(chunk)
            last = time.time()
        elif buf and time.time() - last > idle:
            break
    return bytes(buf)


def try_decode(reply):
    """Best-effort: if the reply looks like a record .syx frame, decode via the codec."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from lfeditor.codec.frame import Frame, TYPE_NAMES, split_frames
        for f in split_frames(reply):
            fr = Frame.parse(f)
            log(f"      decoded: type={fr.type} ({TYPE_NAMES.get(fr.type, '?')}) "
                f"rec={fr.rec_num} values={len(fr.values)}")
    except Exception as e:                                       # noqa: BLE001
        log(f"      (codec decode failed: {e})")


def probe_one(ser, name, cmd, recnum):
    req = per_record_req(cmd, recnum)
    log(f"  {name:<10} cmd=0x{cmd:02X} rec={recnum}  ->  {req.hex(' ')}")
    ser.reset_input_buffer()
    ser.write(req)
    ser.flush()
    reply = drain(ser)
    if not reply:
        log("      . no reply")
        return None
    head = reply[:16].hex(" ")
    log(f"      REPLY {len(reply)} bytes: {head}{' ...' if len(reply) > 16 else ''}")
    if reply[:1] == b"\xf0":
        try_decode(reply)
    return reply


def run_pass(ser, label, recnums):
    log(f"\n== {label} ==")
    captured = {}
    for name, cmd in PER_RECORD_CMDS.items():
        for recnum in recnums:
            r = probe_one(ser, name, cmd, recnum)
            if r:
                captured[(name, recnum)] = r
                break            # answered — no need for the other numbering
            time.sleep(0.15)
    return captured


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-editor-mode", action="store_true",
                    help="skip the Editor-Mode pass; only try requests on a fresh port")
    ap.add_argument("--recnums", default="1,0",
                    help="record numbers to try per command (default: 1 then 0)")
    args = ap.parse_args()
    recnums = [int(n) for n in args.recnums.split(",")]

    port = find_port()
    if not port:
        print("No /dev/cu.usbserial-* port — plug the LF+ in first.")
        sys.exit(2)
    ART.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log(f"probe_per_record  {ts}  port={port} baud={BAUD}")

    captured = {}

    # Pass 1: raw port, no Editor Mode (the 2013 editor had no handshake concept).
    ser = open_serial(port)
    captured.update(run_pass(ser, "PASS 1: no handshake (raw port)", recnums))
    ser.close()
    time.sleep(0.5)

    # Pass 2: inside Editor Mode (handshake C9 + session CA), like our normal session.
    if not args.no_editor_mode:
        ser = open_serial(port)
        ser.write(handshake()); ser.flush()
        hs = drain(ser, idle=0.4, maxwait=2.0)
        log(f"\nhandshake reply: {len(hs)} bytes" + (f" [{hs[:12].hex(' ')}]" if hs else " (NONE)"))
        ser.write(session_begin()); ser.flush()
        drain(ser, idle=0.3, maxwait=0.8)
        captured.update(run_pass(ser, "PASS 2: Editor Mode", recnums))
        ser.write(exit_editor()); ser.flush()
        time.sleep(0.2)
        ser.close()

    # Save raw captures + log
    for (name, recnum), data in captured.items():
        out = ART / f"per_record_{ts}_{name}_{recnum}.bin"
        out.write_bytes(data)
        log(f"saved {out.name} ({len(data)} bytes)")
    logfile = ART / f"per_record_{ts}.log"
    logfile.write_text("\n".join(log_lines) + "\n")
    print(f"\nLog -> {logfile}")

    hits = [k for k in captured if k[0] in ("song", "setlist")]
    print("\nVERDICT:", "SONG/SETLIST ANSWERED — per-record path is alive; proceed to A1."
          if hits else "no song/setlist reply — see log; consider the interposer fallback.")


if __name__ == "__main__":
    main()
