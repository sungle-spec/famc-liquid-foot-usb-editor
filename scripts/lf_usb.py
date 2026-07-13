#!/usr/bin/env python3
"""
Liquid Foot+ USB-Direct transport probe (read path).

Ports the *proven* Liquid Router serial protocol (see the sibling repo's
USB_DIRECT_MAC.md) to the Foot. Only the MODEL byte changes: Router=0x7A, Foot=0x7C.

    port  : /dev/cu.usbserial-<serial>   (device EEPROM PID already set to 0x6015)
    baud  : 230400, 8N1, DTR+RTS asserted
    frame : F0 00 00 7C <dir> .. <cmd> .. F7     (raw bytes; NOT MIDI, data may be > 0x7F)
    handshake (enter Editor Mode) : F0 00 00 7C 0F 0F C9 00 00 00 00 F7
    get-command                   : F0 00 00 7C 0F 0F <X> F7

Read-only. Nothing here writes device memory; the handshake puts the front panel into
"Editor Mode" (reversible — press [sel] to exit).

    python scripts/lf_usb.py pull              # handshake + a get-command set, save raw
    python scripts/lf_usb.py probe             # probe each get-command X individually
    python scripts/lf_usb.py pull --cmds 05,0d,0f --save out.bin
"""
import argparse
import glob
import sys
import time

MODEL_FOOT = 0x7C
BAUD = 230400


def msg(*body):
    return bytes([0xF0, 0x00, 0x00, MODEL_FOOT, *body, 0xF7])


def handshake():
    return msg(0x0F, 0x0F, 0xC9, 0x00, 0x00, 0x00, 0x00)


def get_cmd(x):
    return msg(0x0F, 0x0F, x)


def find_port():
    for p in glob.glob('/dev/cu.usbserial-*'):
        return p
    return None


def open_serial(port, settle=0.3):
    import serial
    ser = serial.Serial(port, BAUD, timeout=0.2)
    ser.dtr = True
    ser.rts = True
    time.sleep(settle)
    ser.reset_input_buffer()
    return ser


def drain(ser, idle=1.2, maxwait=8.0):
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


def deframe(buf):
    out, i = [], 0
    while i < len(buf):
        if buf[i] == 0xF0:
            end = buf.find(0xF7, i + 1)
            if end == -1:
                break
            out.append(buf[i:end + 1])
            i = end + 1
        else:
            i += 1
    return out


def summarize(buf):
    msgs = deframe(buf)
    print(f'  {len(buf)} bytes, {len(msgs)} F0..F7 msgs')
    # header signature of each msg: bytes 1..6
    from collections import Counter
    sigs = Counter()
    for m in msgs:
        sig = ' '.join(f'{b:02X}' for b in m[:7])
        sigs[sig] += 1
    for sig, n in sigs.most_common(20):
        print(f'    x{n:<4} F0 {sig} ... (len varies)')
    return msgs


def cmd_pull(args):
    port = find_port()
    if not port:
        print('No /dev/cu.usbserial-* port (device plugged in + EEPROM at 0x6015?)')
        sys.exit(2)
    cmds = [int(c, 16) for c in args.cmds.split(',')] if args.cmds else [0xCA, 0x05, 0x0D, 0x0F]
    print(f'Port {port} @ {BAUD} — handshake (Editor Mode) + get-cmds {[hex(c) for c in cmds]}')
    ser = open_serial(port)
    ser.write(handshake()); ser.flush(); time.sleep(0.3)
    hs = drain(ser, idle=0.5, maxwait=2.0)
    print(f'Handshake reply: {len(hs)} bytes' + (f'  [{hs[:12].hex()}]' if hs else ' (none)'))
    for c in cmds:
        ser.write(get_cmd(c)); ser.flush(); time.sleep(0.25)
    data = drain(ser)
    ser.close()
    print(f'Stream: {len(data)} bytes')
    summarize(data)
    if args.save:
        open(args.save, 'wb').write(data)
        print(f'Raw -> {args.save}')


def cmd_probe(args):
    port = find_port()
    if not port:
        print('No port'); sys.exit(2)
    xs = [int(c, 16) for c in args.xs.split(',')] if args.xs else list(range(0x01, 0x12)) + [0xCA, 0xCB, 0xCC, 0xCD]
    print(f'Probing {len(xs)} get-commands on {port} (fresh handshake each)...')
    results = {}
    for x in xs:
        ser = open_serial(port)
        ser.write(handshake()); ser.flush(); time.sleep(0.3)
        ser.reset_input_buffer()
        ser.write(get_cmd(x)); ser.flush()
        data = drain(ser, idle=0.8, maxwait=4.0)
        results[x] = len(data)
        tag = f'{len(data):>7} bytes' if data else '      . (none)'
        print(f'  X=0x{x:02X}: {tag}')
        ser.close()
        time.sleep(0.2)
    rich = {x: n for x, n in results.items() if n > 0}
    print('\nReturned data for:', ', '.join(f'0x{x:02X}({n})' for x, n in sorted(rich.items())) or 'NONE')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('pull'); p.add_argument('--cmds'); p.add_argument('--save')
    p.set_defaults(fn=cmd_pull)
    q = sub.add_parser('probe'); q.add_argument('--xs')
    q.set_defaults(fn=cmd_probe)
    args = ap.parse_args()
    args.fn(args)
