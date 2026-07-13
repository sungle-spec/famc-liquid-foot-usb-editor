# Web device I/O (WebSerial)

The web editor can talk to a Liquid Foot+ over USB directly from the browser using the
[Web Serial API](https://developer.mozilla.org/docs/Web/API/Web_Serial_API). The serial
framing/protocol is the same one the desktop app uses (`lfeditor/comms/protocol.py`), and the
browser path is **verified on real hardware** (2026-07-13, LF+ over FTDI USB-serial, Chrome on
macOS): connect, full pull byte-identical to a desktop-path pull of the same device, per-record
write + ACK + readback, restore, clean disconnect — the full smoke test below, all steps passing.

## How it works

Pyodide is single-threaded and can't block on async serial I/O, so the work is split:

- **Python keeps every byte of the protocol** — `webapi.Session.dev_*` wraps
  `comms/protocol.py` (`handshake_frame`, `read_command`, `FOOT_READ_CMDS`, `_synth_frame`, the
  `.syx` write framing). This is the single, hardware-confirmed source of truth; the browser never
  re-implements the wire format.
- **JS does the async orchestration** — [`web/serial.js`](../web/serial.js) opens the port
  (`navigator.serial`, 230400 baud, DTR/RTS asserted), writes the request frames Python builds,
  drains the streamed reply with an idle timeout, slices it into fixed-length records per
  `FOOT_READ_CMDS`, and hands the decoded records back to `dev_load`, which builds a `Dump` the rest
  of the editor (and **Save**) works on.

## Using it

Requires **Chrome or Edge** over **https** (or `localhost`). Firefox/Safari don't implement
WebSerial — the **Connect** button is disabled there.

1. **Connect** — pick the LF+'s serial port; the app handshakes it into Editor Mode (the device LCD
   shows "Editor Mode"). The dot turns green.
2. **From LF+** — reads every USB-exposed data type (Presets, Config, IA-Maps, Sysex messages, and
   the preset/song label extension records) into the editor. Non-destructive.
3. **To LF+** — writes the *current* record back (gated behind a confirm). Keep a backup;
   there is no undo. The device ACKs each write (`F0 09 F7`).
4. **Disconnect** — leaves Editor Mode and closes the port.

## Limits

- **Songs / Set-Lists / Pages / IA-Switches are not exposed over the USB read set** (same as the
  desktop USB path — the device's editor-mode read set is a subset). Edit those offline and save a
  `.syx`.
- No live expression-pedal calibration view yet (the desktop has it; it's a streaming `D2` mode).
- **Always keep a `.syx` backup before writing** — writes have no undo.
- The **Connect** click must be a real user click: Chrome only shows the serial-port picker for a
  genuine user gesture (synthesized/automated clicks are rejected with "No port selected").

## Hardware smoke test — PASSED 2026-07-13

Everything below the transport is pinned by `tests/test_webapi_device.py`, which proves the
`dev_*` bridge is byte-identical to the desktop's hardware-confirmed `comms/protocol.py` and
simulates a device read sliced exactly the way `serial.js` slices it. So this procedure only has
to answer one question: **does `navigator.serial` move the same bytes the desktop's pyserial
does?** On 2026-07-13 it did, on every step: the full browser pull matched the desktop-path pull
SHA-256-per-record-type across all 7 exposed types (384 Presets, 384 Ext9, 384 Ext10, 255
SysexMsg, 2 Config, 60 IAMap, 254 SongExt11); a preset nick write was ACKed and read back
changed; the restore write returned the device byte-identical to the pre-test baseline.

Keep the procedure below as the regression check for future browser/OS changes. Budget
~20 minutes with the LF+ on USB. Do the steps in order — each one depends on the last.

### 0. Baseline with the desktop app (proven path)

1. Desktop editor → **From LF+** → **Backup** to `device_desktop.syx`. This is the reference dump
   *and* your restore point — take it before the browser touches the device.
2. Quit the desktop editor (or at least disconnect). **Only one program can hold the serial port**;
   a lingering desktop connection is the #1 reason the browser sees no ports or no reply.

### 1. Connect

1. Serve the web app (`python web/devserver.py`, then `http://localhost:8000` in **Chrome/Edge** —
   WebSerial needs localhost or https) and click **Connect**.
2. The browser port picker should list the FTDI port (macOS: `usbserial-…`; Windows: `COMn`,
   needs the FTDI VCP driver — [install steps](GETTING_STARTED.md#3-windows-install-the-ftdi-vcp-driver-first);
   Linux: `ttyUSB0`, needs `dialout` group).
3. Expected: toast *"Connected — device in Editor Mode"*, green dot, device LCD shows Editor Mode.
   The handshake retries up to 6× (the device sometimes drops the first attempt after a previous
   session), so give it ~10 s before calling it a failure.

### 2. Pull (non-destructive)

1. **From LF+**. Expected: progress messages, then counts for Presets(384) / PresetExt9 /
   PresetExt10 / SysexMsg / Config(2) / IAMap — and the read-complete note that Songs/Set-Lists/
   Pages/IA-Switches aren't in the USB read set.
2. **Save** the result as `device_web.syx`.
3. Compare against the desktop baseline — decoded values must match for every exposed type:

   ```bash
   .venv/bin/python - device_desktop.syx device_web.syx <<'EOF'
   import sys
   from lfeditor.codec import Dump
   from lfeditor.comms.protocol import FOOT_READ_CMDS
   a, b = (Dump.from_file(p) for p in sys.argv[1:3])
   for rtype, _len in FOOT_READ_CMDS.values():
       va = [f.values for f in a.frames if f.type == rtype]
       vb = [f.values for f in b.frames if f.type == rtype]
       print(f"type {rtype}: {'OK' if va == vb else 'MISMATCH'} ({len(va)} vs {len(vb)} records)")
   EOF
   ```

   All `OK` = the browser read path is verified.

### 3. One gated write (smallest safe change)

1. Pick a scratch preset you don't gig with, change only its **Nick** name, **To LF+**, confirm.
2. Expected: toast *"Write acknowledged by device"* (the `F0 09 F7` ACK). *"No ACK"* means don't
   trust the write — re-pull and check.
3. Verify on the device (or re-pull and look at the nick), then restore the original nick and
   write once more. Device back to its starting state.

### 4. Disconnect

Click Connect again (now Disconnect). Expected: device LCD leaves Editor Mode (the `CC` exit
control), port released — the desktop app can reconnect immediately afterwards.

### If it fails

| Symptom | Likely cause |
| --- | --- |
| Port picker empty | Desktop editor still holding the port; FTDI driver missing (Win); not in `dialout` (Linux); bad cable |
| "No reply — is the LF+ connected…" | Device off / wrong port picked; port held elsewhere; try replugging USB, then Connect again |
| Pull completes but counts are short / step-2 compare mismatches | Timing: a get-command reply idled past `serial.js` limits (`drain(1000, 12000)` per command). Raise them and retry — and note which type broke |
| Writes never ACK but desktop writes do | Suspect write buffering in the browser path — stop testing writes, report with the console log |

Console (F12) logs the byte counts per command — screenshot it for any failure.
