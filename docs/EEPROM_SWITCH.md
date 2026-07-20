# The FTDI EEPROM switch (Device Connection Setup wizard)

**Hardware ▸ Device Connection Setup…** is what makes the Liquid Foot+ appear as a USB-serial
port at all. This page explains what it actually does, what it needs, and what to expect — read
it once before your first Enable, and keep it handy if Revert ever comes up.

## What it does

FAMC ships the Foot's FTDI chip with a **custom USB Product ID (`0x87C0`)**. Most operating
systems' built-in FTDI drivers only bind to FTDI's *standard* PIDs, so at `0x87C0` no serial port
appears at all — the editor has nothing to talk to. The chip is otherwise a completely ordinary
FTDI part; only a 2-byte field in its EEPROM (offset `0x04`) needs to change.

**Enable** rewrites that PID from `0x87C0` to the standard FT-X value `0x6015`. The moment it
does, the OS's own built-in FTDI driver binds to the device and a serial port appears — no
separate driver install, no kext, no dext. **Revert** writes it back to `0x87C0`, e.g. if you
want to go back to using FAMC's original editor (Windows, or macOS via Parallels).

This is implemented in [`lfeditor/comms/eeprom.py`](../lfeditor/comms/eeprom.py) (the actual
read/backup/write logic) and [`lfeditor/ui/eeprom_wizard.py`](../lfeditor/ui/eeprom_wizard.py)
(the dialog).

## Prerequisites

| OS | What you need |
|---|---|
| **macOS** | `brew install libusb` — needed for the EEPROM *write* itself (`pyftdi`/`pyusb` talk to the chip directly over USB). No driver install needed otherwise; the built-in FTDI VCP driver picks up `0x6015` automatically. |
| **Windows** | Usually nothing extra — the FTDI VCP driver ships with Windows, or was already installed by the original FAMC editor. If no COM port shows up, get it from [ftdichip.com](https://ftdichip.com/drivers/vcp-drivers/). |
| **Linux** | Add yourself to the `dialout` group: `sudo usermod -aG dialout $USER`, then log out and back in. Built-in driver otherwise. |

`pyftdi` and `pyusb` are bundled with the app (see `requirements.txt`); `libusb` is the one
native OS-level library you install yourself, and only on macOS.

## What happens when you click Enable or Revert

1. **A full EEPROM backup is read and saved first**, unconditionally — before anything is
   written, and even if the write is later refused or fails. Saved to
   `~/Documents/FAMC/EEPROM_Backups/`, timestamped per attempt
   (`lf_eeprom_<pid>_<timestamp>.bin`).
2. You get an explicit confirmation dialog describing exactly what's about to change.
3. The PID field is rewritten via `pyftdi`'s `set_property("product_id", ...)` + `commit()`.
   `commit()` recomputes the EEPROM CRC and **reads the data back to verify the write actually
   landed** — it raises an error rather than silently leaving the EEPROM in a bad state if the
   verification fails.
4. On success, the dialog tells you to unplug and re-plug the device.

## Issues to be aware of

1. **The device needs a moment — or a physical replug — to show its new identity.** Right after
   a successful write, checking the device's state can still show the *old* PID for a bit,
   because the OS caches the USB descriptors from when the device was first plugged in. This is
   not a failure; it just needs a beat to settle, or an actual unplug/replug, before the new PID
   is visible. Don't panic and don't retry immediately if a fresh check looks stale — refresh
   again after a few seconds, or replug.
2. **Don't unplug the device mid-write.** The confirmation dialog says this explicitly — this is
   the one genuinely risky moment in the whole process. The write itself takes well under a
   second; the risk window is small but real.
3. **The backup is your safety net.** If anything does go wrong, `~/Documents/FAMC/EEPROM_Backups/`
   has a byte-exact image from immediately before the write.
4. **EEPROMs have finite write endurance**, like any EEPROM technology. Nothing chip-specific is
   documented here, but treat Enable/Revert as an occasional one-time setup action rather than
   something to toggle back and forth routinely.
5. **If you're scripting this yourself outside the app** (e.g. a standalone Python script, like
   the one from the original protocol-cracking forum post), use `pyftdi`'s
   `FtdiEeprom.set_property("product_id", pid)` followed by `commit()` — **not** direct
   manipulation of the raw EEPROM byte array. An earlier version of this app's own code did the
   raw-byte approach and it was a real, confirmed-on-hardware bug: it skips some of pyftdi's
   internal bookkeeping (in particular, duplicating the value into a mirrored EEPROM sector),
   and can silently fail to actually commit the change while still reporting no error.
6. **Revert is not blocked on macOS.** An earlier version of this wizard pre-emptively disabled
   Revert on macOS based on an assumption about how Apple's FTDI driver behaves — that assumption
   was never tested against real hardware and turned out to be wrong. Revert has since been
   confirmed live, on real hardware, on macOS. Both directions use the identical write path on
   every OS.

## See also

- [DESKTOP_GUIDE.md — first-time setup](DESKTOP_GUIDE.md#first-time-setup-make-the-device-appear-as-a-serial-port)
  — the illustrated walkthrough.
- [GETTING_STARTED.md §4](GETTING_STARTED.md#4-connect-your-lf-macos-one-time-setup) — the quick
  version for new users.
- [LF_USB_DIRECT.md](LF_USB_DIRECT.md) — the underlying USB-serial protocol this unlocks.
