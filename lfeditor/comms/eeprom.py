"""
FTDI EEPROM "driver" setup for the Liquid Foot+.

FAMC ships the Foot's FTDI chip with a **custom USB PID `0x87C0`** (vendor stays FTDI `0x0403`).
macOS's in-box FTDI VCP driver only binds standard PIDs, so at `0x87C0` no `/dev/cu.usbserial-*`
appears and this editor can't reach the device over USB-serial. Rewriting the EEPROM PID to the
standard FT-X **`0x6015`** makes Apple's driver expose it as a serial port — no kext/dext install.

This module powers the "Device Connection Setup" wizard:
  * `detect_state()`  — read-only: what state is the device in right now?
  * `backup_eeprom()` — read-only: save the full EEPROM image to a file (recovery insurance).
  * `set_product_id()` — the actual EEPROM write (gated behind `allow_write`), used by both
    Enable (`0x87C0 → 0x6015`) and Revert (`0x6015 → 0x87C0`).

All heavy deps (pyusb/libusb, pyftdi) are imported lazily so the editor runs without them; a
missing libusb backend is reported as a normal state, not a crash.

**Platform note on Revert:** writing the EEPROM needs raw USB access via libusb. At `0x87C0` no OS
driver owns the chip, so Enable works everywhere. At `0x6015`, macOS's FTDI DriverKit dext claims
the interface and libusb can't open it — so Revert is reliable on Linux/Windows but blocked on
macOS unless the driver is unbound. `revert_blocked_reason()` returns a message for the UI.
"""
from __future__ import annotations

import datetime as _dt
import os
import platform
from dataclasses import dataclass, field
from typing import Optional

FTDI_VID = 0x0403
FAMC_CUSTOM_PID = 0x87C0   # as shipped by FAMC — invisible to the macOS VCP driver
SERIAL_PID = 0x6015        # standard FT-X — exposed as /dev/cu.usbserial-* by Apple's driver
PID_OFFSET = 0x04          # EEPROM byte offset of the little-endian product id (pyftdi-confirmed)

# detection states
READY = "ready"                  # serial port present → already enabled & driver bound
ENABLED_NO_PORT = "enabled_no_port"  # chip at 0x6015 but no serial port yet (re-plug needed)
NEEDS_ENABLE = "needs_enable"    # chip at the FAMC custom PID → offer Enable
OTHER_FTDI = "other_ftdi"        # an FTDI device, but not a recognised LF+ PID
NO_DEVICE = "no_device"          # no FTDI device found
NO_BACKEND = "no_backend"        # libusb/pyusb not installed → can't inspect/program

_STATE_TEXT = {
    READY: "Ready — the Liquid Foot+ is connected as a serial port.",
    ENABLED_NO_PORT: "Enabled in EEPROM (PID 0x6015) but no serial port yet — unplug and "
                     "re-plug the device.",
    NEEDS_ENABLE: "Found a Liquid Foot+ with FAMC's custom PID (0x87C0). It needs enabling to "
                  "appear as a serial port.",
    OTHER_FTDI: "An FTDI device is connected, but not a recognised Liquid Foot+ PID.",
    NO_DEVICE: "No FTDI device found — check the USB cable and power.",
    NO_BACKEND: "libusb isn't installed, so the USB EEPROM can't be inspected. Install it with "
                "'brew install libusb' (macOS) and try again.",
}


@dataclass
class DeviceState:
    state: str
    message: str
    pid: Optional[int] = None          # detected product id, when known
    serial_ports: list[str] = field(default_factory=list)

    @property
    def can_enable(self) -> bool:
        return self.state == NEEDS_ENABLE

    @property
    def is_ready(self) -> bool:
        return self.state == READY


def _ftdi_usb_devices():
    """Return connected FTDI usb.core.Device objects. Raises if no libusb backend."""
    import usb.core  # lazy; raises usb.core.NoBackendError if libusb is absent
    return list(usb.core.find(find_all=True, idVendor=FTDI_VID)) or []


def detect_state() -> DeviceState:
    """Inspect the machine and report how the Foot is currently reachable (read-only)."""
    from .ports import find_serial_ports
    ports = [p.name for p in find_serial_ports()]
    if ports:
        return DeviceState(READY, _STATE_TEXT[READY], pid=SERIAL_PID, serial_ports=ports)
    try:
        devs = _ftdi_usb_devices()
    except Exception as exc:  # NoBackendError or any libusb failure
        if "backend" in str(exc).lower():
            return DeviceState(NO_BACKEND, _STATE_TEXT[NO_BACKEND])
        return DeviceState(NO_BACKEND, f"{_STATE_TEXT[NO_BACKEND]} ({exc})")
    pids = {int(d.idProduct) for d in devs}
    if SERIAL_PID in pids:
        return DeviceState(ENABLED_NO_PORT, _STATE_TEXT[ENABLED_NO_PORT], pid=SERIAL_PID)
    if FAMC_CUSTOM_PID in pids:
        return DeviceState(NEEDS_ENABLE, _STATE_TEXT[NEEDS_ENABLE], pid=FAMC_CUSTOM_PID)
    if pids:
        return DeviceState(OTHER_FTDI, _STATE_TEXT[OTHER_FTDI], pid=sorted(pids)[0])
    return DeviceState(NO_DEVICE, _STATE_TEXT[NO_DEVICE])


def revert_blocked_reason() -> Optional[str]:
    """Why Revert (0x6015 → 0x87C0) can't run here, or None if it can."""
    if platform.system() == "Darwin":
        return ("On macOS the system FTDI driver owns the device at PID 0x6015, so the EEPROM "
                "can't be rewritten back to 0x87C0 from here. Revert from a Linux/Windows machine, "
                "or unbind the driver first.")
    return None


def _open_eeprom(pid: int):
    """Open an FtdiEeprom for the device currently enumerated at `pid` (registers the custom PID
    so pyftdi will recognise it). Caller must close()."""
    from pyftdi.ftdi import Ftdi
    from pyftdi.eeprom import FtdiEeprom
    # teach pyftdi about FAMC's non-standard product id so it can open/decode it
    try:
        Ftdi.add_custom_product(FTDI_VID, FAMC_CUSTOM_PID, "LF+")
    except ValueError:
        pass  # already registered
    eeprom = FtdiEeprom()
    eeprom.open(f"ftdi://0x{FTDI_VID:04x}:0x{pid:04x}/1")
    return eeprom


def backup_eeprom(pid: int, directory: str) -> str:
    """Read the full EEPROM image of the device at `pid` and write it to a timestamped .bin in
    `directory`. Returns the file path. Read-only on the device."""
    os.makedirs(directory, exist_ok=True)
    eeprom = _open_eeprom(pid)
    try:
        raw = bytes(eeprom.data)
    finally:
        eeprom.close()
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(directory, f"lf_eeprom_{pid:04x}_{stamp}.bin")
    with open(path, "wb") as fh:
        fh.write(raw)
    return path


@dataclass
class WriteResult:
    ok: bool
    message: str
    backup_path: Optional[str] = None
    old_pid: Optional[int] = None
    new_pid: Optional[int] = None


def set_product_id(current_pid: int, new_pid: int, backup_dir: str,
                   allow_write: bool = False, dry_run: bool = False) -> WriteResult:
    """Rewrite the FTDI EEPROM product id (current_pid → new_pid).

    Always backs up the EEPROM image first. The real write is refused unless `allow_write=True`
    (the wizard sets this only after an explicit user confirmation). `dry_run` validates and logs
    without committing. pyftdi's commit() recomputes the EEPROM CRC and verifies the read-back,
    raising on mismatch — so a failed write is reported, not silently wrong.
    """
    if platform.system() == "Darwin" and new_pid == FAMC_CUSTOM_PID:
        reason = revert_blocked_reason()
        if reason:
            return WriteResult(False, reason, old_pid=current_pid, new_pid=new_pid)
    # 1) always capture a recovery backup first
    try:
        backup = backup_eeprom(current_pid, backup_dir)
    except Exception as exc:  # noqa: BLE001
        return WriteResult(False, f"Could not read/back-up the EEPROM: {exc}",
                           old_pid=current_pid, new_pid=new_pid)
    if not allow_write:
        return WriteResult(False, "Write not authorised (allow_write is off). Backup saved.",
                           backup_path=backup, old_pid=current_pid, new_pid=new_pid)
    # 2) modify just the product-id word and commit (CRC + verify handled by pyftdi)
    eeprom = _open_eeprom(current_pid)
    try:
        if not hasattr(eeprom, "_eeprom") or not hasattr(eeprom, "_dirty"):
            return WriteResult(False, "Unexpected pyftdi version (EEPROM internals changed).",
                               backup_path=backup, old_pid=current_pid, new_pid=new_pid)
        eeprom._eeprom[PID_OFFSET] = new_pid & 0xFF
        eeprom._eeprom[PID_OFFSET + 1] = (new_pid >> 8) & 0xFF
        eeprom._dirty.add("product_id")     # force CRC recompute + the modified flag
        changed = eeprom.commit(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        return WriteResult(False, f"EEPROM write failed: {exc}. Your backup is at {backup}.",
                           backup_path=backup, old_pid=current_pid, new_pid=new_pid)
    finally:
        eeprom.close()
    if dry_run:
        return WriteResult(True, f"Dry run OK — would set PID 0x{new_pid:04x}. Backup at {backup}.",
                           backup_path=backup, old_pid=current_pid, new_pid=new_pid)
    if not changed:
        return WriteResult(False, "EEPROM reported no change (already at that PID?).",
                           backup_path=backup, old_pid=current_pid, new_pid=new_pid)
    return WriteResult(True, f"PID set to 0x{new_pid:04x}. Unplug and re-plug the device to "
                       f"finish. Backup saved to {backup}.",
                       backup_path=backup, old_pid=current_pid, new_pid=new_pid)
