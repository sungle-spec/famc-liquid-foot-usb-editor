# Troubleshooting a faulty unit

What the LF+ itself offers for diagnosing a misbehaving unit, from the printed manual (p.15,
"Special Commands During Power Up") and from reading the v6.32 firmware images
([FIRMWARE_NOTES.md](FIRMWARE_NOTES.md)). Nothing here was tested on hardware by this project;
items marked *inferred* come from disassembly, not from FAMC documentation.

> **Careful with the buttons.** Several power-up combinations erase data. Hold **only** the
> buttons named in the row you want, and release them as described by the manual.

## Power-up buttons

Hold the button(s) while applying power.

| Hold at power-up | What happens | Use it for |
|---|---|---|
| **B6** | Expression-pedal test; shows raw pedal values (0–409) | Dead, noisy or mis-ranged pedal inputs |
| **B7** | Unit waits for MIDI firmware before starting | Recovery — see [FIRMWARE_LOADER.md](FIRMWARE_LOADER.md) |
| **B8** | Opens the unit's menu | Utilities, firmware loading, settings |
| **B1**, **B2** or **B3** | Selects a start-up mode | See the manual, p.15 |
| **B1 + B2 + B3 + B4** | **Global reset** | Last resort for odd settings; back up first |
| **B5 + B6 + B7 + B8** | **Factory erase** | Wipes the unit; back up first |

There is **no scribble-screen / LCD self-test** in the firmware: no routine draws a test
pattern, and the only LCD strings are the menu and status text. If a screen is dark or garbled
the fault is in the hardware or its cable, not something a setting will fix.

## Quick triage

1. **Nothing on the display** — check power first, then try **B7** at power-up. If the unit
   shows it is waiting for firmware, the boot path works and the application image is the
   problem: use the [Firmware Loader](FIRMWARE_LOADER.md), Route A.
2. **A pedal misbehaves** — hold **B6** at power-up and move the pedal through its full travel.
   A healthy input sweeps cleanly from 0 to about 409. Jumps, a stuck value or a limited range
   mean a calibration or hardware fault.
3. **Odd behaviour after editing** — pull a backup, then try a **global reset** and reload the
   backup. If the problem persists with a clean rig, it is not your data.
4. **Editor cannot see the unit** — see [GETTING_STARTED.md](GETTING_STARTED.md) and the USB
   MIDI Bridge notes in the [desktop guide](DESKTOP_GUIDE.md).

## `Firmware Failed` / `Error N`

Shown after a bad firmware send. Every such error is raised before the unit's boot loader is
involved, so the firmware already installed is unchanged. Decode the number with:

```bash
python -m lffirmware --explain-error 33
```

or open **Inspect…** in the loader. Full table: [FIRMWARE_LOADER.md](FIRMWARE_LOADER.md).

## Editor control bytes (for the curious)

The running firmware answers a few extra editor control bytes: `C8` enters firmware-wait without
a button hold, `D2` streams the four pedal values live, and `CD`/`CE` appear to switch the unit's
serial link between MIDI speed (31250 baud) and a much faster rate (about 230400) — *inferred*
from the baud-rate constants beside them, not confirmed. None are needed for normal use and the
editor does not send them.
