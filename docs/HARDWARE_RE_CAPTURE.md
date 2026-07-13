# Hardware RE — capturing the editor's live serial traffic

A handful of controls in the original **LF+ Editor v6.31** write **no byte to a saved `.syx`** —
toggling them changes nothing in a backup file. They are therefore *not* part of the stored record
format; they are sent to the device as **live commands** (or are pure editor-runtime state). To map
them we must watch the bytes the original editor puts on the wire while it is connected to a real
Liquid Foot+.

## The controls still to map (all hardware-dependent)

| Tab | Control | Notes |
|---|---|---|
| Exp Pedals | **Hi-Res Mode** | rescales the live calibration block; not a clean stored flag |
| Exp Pedals | **Force-zipper** | no byte in the backup |
| Exp Pedals | **2nd Button** | disabled for the pedal types we could test |
| Pages | **"menu" button trigger** | writes no byte to the backup (editor-display) |
| Pages | **selected / not-selected preset-button colours** | writes no byte to the backup |

## Why this can't be fully automated here

Injecting the logger requires launching the editor's binary **directly** (so `DYLD_INSERT_LIBRARIES`
survives — macOS strips it from `open`/LaunchServices launches). But a directly-launched Xojo app's
windows are **not click-hittable by automation** (clicks fall through to the desktop/Notification
Center), and keystrokes can't reach its custom widgets. So the editor must be driven **by hand** at
the machine; the capture itself is automatic.

## Procedure

1. **Connect** the Liquid Foot+ over USB (it enumerates as `/dev/cu.usbserial-XXXXXXXX`,
   "Liquid Foot+ Series").
2. From a Terminal, launch the **injected** editor (this also builds the dylib if needed):
   ```sh
   sh scripts/lf_capture_launch.sh
   ```
   The log starts at `scripts/ARTIFACTS/lf_runtime_capture.txt` (`=== interposer loaded ===`).
3. In the editor, click **CONNECT** (top-right) and wait for the unit's LCD to show *Editor Mode*.
   The handshake bytes appear in the log — this confirms capture is working end-to-end.
4. For **one** control at a time: note the current log size (`wc -c …`), toggle the control (and
   click **Send Global Settings To LF+** if it doesn't transmit live), then stop. The bytes appended
   after your mark are that control's command.
5. Repeat per control, one at a time, so each command is isolated in the log delta.
6. Click **CONNECT** again to disconnect cleanly. **Do not** force-quit the editor mid-session
   (dropping DTR while connected can wedge the unit — press the device's **[sel]** to recover).

## Decoding

Frames are raw bytes (not MIDI): `F0 00 00 7C <dir> … <cmd> … F7` (model byte `0x7C` = Foot). Diff a
control's OFF-state capture against its ON-state capture; the differing command/byte is the mapping.
Add confirmed findings to `model/*.py` + `docs/LF_DATA_MODEL.md`. See `scripts/lf_usb.py` and
`docs/LF_USB_DIRECT.md` for the proven frame format and the get-command set.
