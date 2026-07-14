# LF+ Firmware Loader (beta) — firmware flashing & bricked-unit recovery

> **STATUS: BETA — NOT YET VALIDATED ON HARDWARE.** The loader reproduces exactly what the
> original 2013 FAMC editor did on the wire (confirmed from its decompiled source), plus the
> safety checks FAMC never had. It is being validated with community testers, **bricked units
> first** (see the [tester protocol](#tester-protocol)). Until that ladder is climbed:
> **do not use this on a working device you can't afford to lose.**

Firmware flashing is what bricked several units in the first place, which is why the editor
itself has always kept *Load Firmware* disabled. This standalone tool exists for two reasons:

1. **Recovery**: the LF+ has a documented rescue mode that works even when the main firmware is
   dead — hold **B7 while powering on** and the unit *"waits for MIDI Firmware before doing
   anything else"* (manual p.15, "Special Commands During Power Up"). A bricked unit fed the
   correct-model firmware image through that mode has a real chance of coming back.
2. **Updates** for working units, eventually — after the beta validation ladder is complete.

## What it does

- Verifies a firmware file **before anything is sent**: correct LF+ firmware header
  (`F0 00 00 7C 08 06`), single sysex frame, valid payload, and — critically — a **SHA-256 match
  against the 241 known FAMC firmware releases** (v3.34 → v6.32, all five models). File *size
  cannot* identify the model (sizes collide across models between versions), so hash identity is
  the safety net; unknown files need an explicit override.
- Refuses model mismatches: the image's verified identity must match the model **you** select.
  Wrong-model firmware can permanently damage a unit.
- Sends the image the way the original editor did: **one sysex message over MIDI** (the device's
  MIDI DIN input — *not* the LF+ USB socket), ~82–86 s at DIN speed.
- Keeps your computer awake during the send, records everything (including any device replies)
  to a **session log** you can share for analysis, and walks you through the manual's own
  procedure for each route.

**Not included: firmware files.** They are FAMC's copyrighted binaries. Get them from your
original editor install (`…/LF+ Editor/Firmware/`), a FAMC download you kept, or ask on the
forum — the loader will verify whatever you feed it against the known-good hash list.

## What you need

- A **USB-MIDI interface** (any class-compliant one) cabled: computer MIDI OUT → LF+ **MIDI IN**.
- The firmware `.syx` **for your exact model** (`LF+12+_FIRM.syx`, `LF+MINI_FIRM.syx`, …).
- The loader: download "LF+ Firmware Loader" from the
  [releases](https://github.com/sungle-spec/famc-liquid-foot-editor-builds/releases), or run
  from source: `python -m lffirmware`.

## Route A — recover a bricked unit

A unit bricked by a failed update has nothing to lose, and this is the documented rescue path:

1. Power the unit **off**. Cable computer MIDI OUT → device MIDI IN.
2. **Hold B7 alone** and power on; keep holding until the unit indicates it is waiting for
   firmware. ⚠ *Hold only B7* — B5+B6+B7+B8 together is a full factory **erase**, and
   B1+B2+B3+B4 is a global reset (same manual table).
3. In the loader: choose the firmware file (it verifies), select your model, select the MIDI
   output, tick every checklist item, type the model name, **FLASH**.
4. Wait. The transfer takes about a minute and a half; the device should then program itself
   and restart. **Do not power off, unplug, or press anything** until it has restarted —
   interrupting the flash is exactly what bricks these units.
5. Whatever happens, keep the session log (path is shown in the app) and report back.

If the unit doesn't respond in firmware-wait mode, or restarts still broken: it may need a
different version first (very old firmware had a documented two-step upgrade path), or the
failed flash may have taken the bootloader with it. Send the log — every attempt teaches us
something.

## Route B — update a working unit (testers only, for now)

1. **Back up first** and verify the backup opens in the editor: toolbar **From LF+**, then
   **Backup**.
2. Device menu → Utilities → **FIRMWARE LOADING** → SELECT → *"Waiting For Firmware"*
   (manual p.90).
3. Same loader flow as Route A. The safest first test is **re-flashing the version you already
   run** — any outcome is recoverable by definition if the flash path works.
4. After restart: check the firmware version, pull a fresh backup, and confirm your rig
   decodes identically.

## CLI

```bash
python -m lffirmware --list-ports
python -m lffirmware --image LF+12+_FIRM.syx --model 12+ --dry-run     # verify only, sends nothing
python -m lffirmware --image LF+12+_FIRM.syx --model 12+ --port "USB MIDI Interface"
```

`--dry-run` performs every check and shows exactly what a real run would send — safe anywhere,
no MIDI I/O. `--allow-unverified` is required for images not in the known-hash list.

## Tester protocol

The validation ladder (in order — each gate must pass before the next starts):

| Phase | Who | What | Gate |
|---|---|---|---|
| 1 | anyone with a working unit + the original editor (macOS) | capture an official firmware update with `scripts/capture_original.sh` (see [HARDWARE_RE_CAPTURE.md](HARDWARE_RE_CAPTURE.md)) | tells us whether the modern editor adds any handshake around the image (the 2013 one didn't) |
| 2 | **bricked-unit owners** | Route A recovery attempt | ≥1 successful un-brick, or ≥1 no-change-no-harm run |
| 3 | a working-unit volunteer | Route B same-version re-flash, then a real version step | version + backup integrity verified |

Every run: send the session log (`~/LFFirmwareLoader-logs/`), your model, firmware version
flashed, MIDI interface used, and what the device LCD did. Report on the GitHub issues page or
the forum thread.

## Risk statement

This tool can permanently damage your device. It is independent, unofficial, unsupported, and
provided as-is — **use it entirely at your own risk**, and never without a backup. A bricked
unit may also be beyond software recovery (a failed flash can corrupt the bootloader itself);
Route A is a genuine chance, not a promise.
