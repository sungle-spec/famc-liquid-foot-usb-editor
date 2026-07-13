"""
Port discovery for the two ways to reach a Liquid Foot+:

* **MIDI** — the device's native transport (DIN or USB-MIDI). The 2013 editor used this
  exclusively; it needs no handshake. This is the primary path.
* **USB-serial** — the FTDI VCP path the 2020 Xojo editor added (same chip family as the
  Liquid Router). Appears as `/dev/cu.usbserial-*` (macOS), `/dev/ttyUSB*` (Linux) or an
  FTDI COM port (Windows).

All heavy deps (pyserial, mido) are imported lazily so the editor runs without them.
"""
from __future__ import annotations

import glob
import platform
from dataclasses import dataclass

FTDI_VID = 0x0403  # FTDI — the family the LF+ uses for USB-serial


@dataclass(frozen=True)
class PortInfo:
    kind: str        # "serial" | "midi-in" | "midi-out"
    name: str        # device path / port name to open
    label: str       # human label for the UI


def find_serial_ports() -> list[PortInfo]:
    """FTDI USB-serial ports, cross-platform. Returns [] if pyserial is missing."""
    out: list[PortInfo] = []
    system = platform.system()
    if system == "Darwin":
        for p in sorted(glob.glob("/dev/cu.usbserial-*")):
            out.append(PortInfo("serial", p, p))
    elif system == "Linux":
        for p in sorted(glob.glob("/dev/ttyUSB*")):
            out.append(PortInfo("serial", p, p))
    # Windows, or fallback: enumerate by FTDI vendor id via pyserial.
    try:
        from serial.tools import list_ports
        for p in list_ports.comports():
            desc = ((p.description or "") + " " + (p.device or "")).lower()
            if getattr(p, "vid", None) == FTDI_VID or "ftdi" in desc or "usbserial" in desc:
                if not any(o.name == p.device for o in out):
                    out.append(PortInfo("serial", p.device, f"{p.device} ({p.description})"))
    except Exception:
        pass
    return out


def find_midi_ports() -> tuple[list[PortInfo], list[PortInfo]]:
    """(inputs, outputs) MIDI ports via mido. Returns ([], []) if mido is missing."""
    try:
        import mido
        ins = [PortInfo("midi-in", n, n) for n in mido.get_input_names()]
        outs = [PortInfo("midi-out", n, n) for n in mido.get_output_names()]
        return ins, outs
    except Exception:
        return [], []


def discover() -> dict[str, list[PortInfo]]:
    """All reachable ports, grouped. UI calls this to populate the Connect dialog."""
    midi_in, midi_out = find_midi_ports()
    return {"serial": find_serial_ports(), "midi_in": midi_in, "midi_out": midi_out}
