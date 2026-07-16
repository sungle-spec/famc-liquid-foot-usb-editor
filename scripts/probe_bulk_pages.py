#!/usr/bin/env python3
"""
Probe: do bulk get-commands 0x07/0x08/0x09 actually return Page/Song/Setlist on THIS hardware?

Background (docs/LF_USB_DIRECT.md): a 2026-06-15 manual probe found no bulk reply for Song(2)/
Setlist(5)/Page(7) across X=0x01-0x20, so the editor fell back to the 2013-style per-record path
for Song/Setlist and left Page unreadable entirely. A JR+ tester's 2026-07-16 feedback ("songs
write fine and pages read fine in the ORIGINAL editor") prompted disassembling that original
v6.31 editor (Xojo, full symbol table) — its Window1.Get_All_Pages/Songs/SetLists methods each
send exactly `F0 00 00 7C 0F 0F <X> F7` with X=0x07/0x08/0x09, and every OTHER Get_All_* method
in that binary matched our already-hardware-confirmed cmd bytes exactly, which validates the
method. That directly contradicts the 2026-06-15 probe's negative result — this script re-probes
0x07/0x08/0x09 (plus a scan of the still-unexplained bytes) against a real LF+ to find out which
account is right on THIS unit, and cross-checks any bulk Song reply against the proven per-record
path (0x0B) for a byte-exact match.

Read-only: only read requests are sent; nothing writes device memory. The handshake puts the
front panel into "Editor Mode" (reversible; this script sends the CC exit control when done).

    python scripts/probe_bulk_pages.py            # full probe, log to scripts/ARTIFACTS/
"""
import glob
import sys
import time
from datetime import datetime
from pathlib import Path

MODEL_FOOT = 0x7C
BAUD = 230400
ART = Path(__file__).resolve().parent / "ARTIFACTS"

# The three bulk commands the v6.31 disassembly found (see docstring above), plus every other
# byte in the 0x01-0x13 range that isn't already a known/mapped get-command — a blind scan in
# case there's a fourth undiscovered bulk type nobody's found a name for yet.
KNOWN_BULK = {0x05: "Preset", 0x0A: "SysexMsg", 0x0B: "Config", 0x0C: "IAMap",
              0x0D: "IALabels", 0x0E: "FirmwareData", 0x0F: "MAPLabels", 0x10: "SongExt11"}
CANDIDATE_BULK = {0x07: "Page", 0x08: "Song", 0x09: "Setlist"}
SCAN_BULK = [x for x in range(0x01, 0x14) if x not in KNOWN_BULK and x not in CANDIDATE_BULK]

# 2013 SendMsg per-record cmd for Song, used to cross-check a bulk Song reply.
PER_RECORD_SONG_CMD = 0x0B

log_lines = []


def log(s=""):
    print(s)
    log_lines.append(s)


def msg(*body):
    return bytes([0xF0, 0x00, 0x00, MODEL_FOOT, *body, 0xF7])


def bulk_req(x):
    return msg(0x0F, 0x0F, x)


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


def drain(ser, idle=1.0, maxwait=10.0):
    """Generous idle-timeout drain — bulk streams can be several KB, unlike the single bounded
    frame a per-record reply is (see lfeditor.comms.protocol.pull_records' defaults)."""
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


def probe_bulk(ser, x, label):
    req = bulk_req(x)
    log(f"  bulk 0x{x:02X} ({label:<10})  ->  {req.hex(' ')}")
    ser.reset_input_buffer()
    ser.write(req)
    ser.flush()
    reply = drain(ser)
    if not reply:
        log("      . no reply")
        return b""
    log(f"      REPLY {len(reply)} bytes: {reply[:16].hex(' ')}{' ...' if len(reply) > 16 else ''}")
    return reply


def main():
    port = find_port()
    if not port:
        print("No /dev/cu.usbserial-* port — plug the LF+ in first.")
        sys.exit(2)
    ART.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log(f"probe_bulk_pages  {ts}  port={port} baud={BAUD}")

    ser = open_serial(port)
    ser.write(handshake())
    ser.flush()
    hs = drain(ser, idle=0.4, maxwait=2.0)
    log(f"\nhandshake reply: {len(hs)} bytes" + (f" [{hs[:12].hex(' ')}]" if hs else " (NONE)"))
    if not hs:
        log("No handshake reply — aborting (device not in Editor Mode).")
        ser.close()
        sys.exit(1)
    ser.write(session_begin())
    ser.flush()
    drain(ser, idle=0.3, maxwait=0.8)

    captured = {}

    log("\n== Candidate bulk commands (from v6.31 disassembly) ==")
    for x, label in CANDIDATE_BULK.items():
        captured[x] = probe_bulk(ser, x, label)

    log("\n== Scan of unmapped bytes 0x01-0x13 (looking for a 4th undiscovered bulk type) ==")
    for x in SCAN_BULK:
        captured[f"scan_{x:02x}"] = probe_bulk(ser, x, "?")

    # Cross-check: if bulk Song (0x08) answered, compare its first record against the proven
    # per-record path (0x0B, recnum 0) for a byte-exact match.
    song_bulk = captured.get(0x08, b"")
    if song_bulk:
        log("\n== Cross-check: bulk Song(0x08) vs per-record Song(0x0B, rec 0) ==")
        ser.reset_input_buffer()
        ser.write(per_record_req(PER_RECORD_SONG_CMD, 0))
        ser.flush()
        song_pr = drain(ser, idle=0.3, maxwait=3.0)
        log(f"  per-record reply: {len(song_pr)} bytes: {song_pr[:16].hex(' ')}")
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from lfeditor.codec.frame import Frame, nibbles_to_values
            pr_frame = Frame.parse(song_pr)
            # bulk Song is a decoded stream (125 bytes/record + 1 trailing status byte), not a
            # nibble-encoded .syx frame — slice the first 125 decoded bytes for comparison.
            bulk_first_values = list(song_bulk[:125])
            match = bulk_first_values == pr_frame.values
            log(f"  bulk[0:125] == per-record rec0 values: {match}")
            if not match:
                log(f"    bulk:       {bulk_first_values[:16]}...")
                log(f"    per-record: {pr_frame.values[:16]}...")
        except Exception as e:                                    # noqa: BLE001
            log(f"  (cross-check decode failed: {e})")

    # Verify: Page count/len should be 50 * 210 decoded bytes + 1 trailing status byte.
    page_bulk = captured.get(0x07, b"")
    if page_bulk:
        n = (len(page_bulk) - 1) / 210 if len(page_bulk) % 210 == 1 else len(page_bulk) / 210
        log(f"\n== Page(0x07) reply: {len(page_bulk)} bytes -> ~{n:.1f} records "
            f"(expect 50 @ 210 bytes/record) ==")

    ser.write(exit_editor())
    ser.flush()
    time.sleep(0.2)
    ser.close()

    for key, data in captured.items():
        if not data:
            continue
        name = key if isinstance(key, str) else f"{key:02x}"
        out = ART / f"bulk_pages_{ts}_{name}.bin"
        out.write_bytes(data)
        log(f"saved {out.name} ({len(data)} bytes)")
    logfile = ART / f"bulk_pages_{ts}.log"
    logfile.write_text("\n".join(log_lines) + "\n")
    print(f"\nLog -> {logfile}")

    hits = [x for x in CANDIDATE_BULK if captured.get(x)]
    names = ", ".join(CANDIDATE_BULK[x] for x in hits)
    print("\nVERDICT:", f"Bulk answered for: {names or '(none)'} — "
          f"{len(hits)}/{len(CANDIDATE_BULK)} of the disassembly's candidate commands confirmed.")


if __name__ == "__main__":
    main()
