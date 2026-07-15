# Liquid Foot+ USB-Direct — read & write SOLVED on hardware (2026-06-15)

> **Status: read and write both working** over a single USB cable from a modern Apple-Silicon
> Mac, no kext / DriverKit extension / Developer account. Validated against a real Liquid Foot+
> (a full 384-preset reference rig). This is the source of truth for `lfeditor/comms/`.
> The same protocol also works from the **browser** (WebSerial, Chrome/Edge): verified on the
> same hardware 2026-07-13 — see [WEBSERIAL.md](WEBSERIAL.md). Song/Setlist/IASwitch also
> transfer over USB via a separate per-record request, confirmed 2026-07-15 (below) — read-only
> for now.

The Foot reuses the **exact** USB-serial protocol first cracked for the sibling FAMC Liquid
Router (a separate, private reverse-engineering project); only the **MODEL byte changes**
(Router `0x7A` → **Foot `0x7C`**) and the device's read-command set / write-ACK behaviour differ.

## TL;DR

1. The Foot's FTDI EEPROM PID was already rewritten from FAMC's custom `0x87C0` to the standard
   FT-X `0x6015`, so Apple's in-box FTDI driver exposes it as `/dev/cu.usbserial-<serial>`.
   (One-time, reversible — the wizard saves a full EEPROM backup first.)
   The editor automates this via **Hardware → Device Connection Setup…** (`lfeditor/comms/eeprom.py`
   + `ui/eeprom_wizard.py`): it detects the current state, saves a full EEPROM backup, then flips
   the PID word at EEPROM offset `0x04` (pyftdi `commit()` recomputes the CRC and verifies the
   read-back). **Enable** (`0x87C0 → 0x6015`) works on any OS because no driver owns the chip at
   `0x87C0`. **Revert** (`0x6015 → 0x87C0`) is reliable on Linux/Windows but **blocked on macOS**,
   where the FTDI DriverKit dext claims the `0x6015` device and libusb can't open it (the wizard
   disables Revert there and explains why). Needs `libusb` (`brew install libusb`) for USB access.
2. Talk to that port at **230400 baud, 8N1, DTR+RTS asserted**.
3. Send the **handshake** `F0 00 00 7C 0F 0F C9 00 00 00 00 F7` (device enters *Editor Mode*,
   front panel: "Editor Mode [sel] to exit", replies `F0 05 00 7C …`), then the **session-begin**
   control `F0 00 00 7C 0F 0F CA F7` (the real editor sends this once after the handshake; it
   returns nothing).
4. Send **get-commands** `F0 00 00 7C 0F 0F <X> F7`; the device streams that data type back as
   **concatenated decoded record values** (not nibble-encoded frames) + 1 trailing status byte.
5. **Write** by replaying/splicing a record's `.syx`-format frame
   `F0 00 00 7C 00 <type> 01 <recnum> <len> <nibbles> 00 F7`. The device **ACKs each write with
   `F0 09 F7`** (read-back also confirms it).
6. **Disconnect** by sending `F0 00 00 7C 0F 0F CC F7` (**leave Editor Mode**) then closing the
   port — the device's LCD drops back to normal (no need to press [sel]).

## Wire format

```
port  : /dev/cu.usbserial-<serial>
baud  : 230400, 8 data bits, no parity, 1 stop bit
lines : DTR asserted, RTS asserted   (NEVER toggle DTR low mid-session — it wedges the link)
frame : F0 00 00 7C <dir> .. <cmd> .. F7      (raw bytes; NOT MIDI — data may be > 0x7F)
        dir byte[4]: 0x00 = host→device, 0x05 = device→host
```

### Read get-commands (confirmed by probing each individually)

The device streams the **decoded** record values (the same bytes the codec produces from a `.syx`
frame), concatenated, fixed length per record, with one trailing status byte. The read-command
codes are **not** the record-type codes (just like the Router: read `0x05` ↔ write type `0x0A`).

| `<X>` | Record type | Decoded len | Count | Stream bytes | Verified vs reference dump |
|---|---|---|---|---|---|
| `0x05` | Preset (1) | 170 | 384 | 65281 | ✅ 46 runtime-byte diffs / 65280 |
| `0x0D` | PresetExt9 (9) | 80 | 384 | 30721 | ✅ 0 diffs |
| `0x0F` | PresetExt10 (10) | 160 | 384 | 61441 | ✅ 0 diffs |
| `0x0A` | SysexMsg (6) | 42 | 255 | 10711 | ✅ 0 diffs |
| `0x0B` | Config (4) | 250 | 2 | 501 | ✅ runtime only |
| `0x0C` | IAMap (8) | 100 | 60 | 6001 | ✅ 4 runtime diffs |
| `0x10` | SongExt11 (11) | 96 | 254 | 24385 | ✅ 0 diffs |
| `0x0E` | — aux IA-sync *display* stream ("D:0 Effect:000 …") | — | — | 24001 | not a stored record type |

### Live expression-pedal stream (`D2`) — reverse-engineered 2026-06-16/17

The Exp-Pedals "Live View" is a **continuous stream**: send the control **`F0 00 00 7C 0F 0F D2 F7`**
**once** and the device streams **`FE`-delimited 8-byte frames** continuously, each carrying **four
16-bit big-endian ADC positions** (one per pedal): `FE <p0hi p0lo> <p1hi p1lo> <p2hi p2lo> <p3hi p3lo> FE`
(the real stream double-delimits, `… DATA FE FE DATA …`). You do **not** re-send `D2` — one is
enough. Confirmed on a real LF+ 12+: a swept pedal ranged ~84→1023 (10-bit ADC); un-connected pedals
sit at the stored default (409). Implemented in `comms/protocol.parse_live_positions` +
`ui/live_pedals.py` (the "Live Calibrate…" button on the Exp-Pedals tab).

**Saving calibration (`comms/protocol.write_records_live`) — captured from the original editor,
2026-06-17.** The calibration is **not** saved with a normal record write. A record write around the
stream is ignored: stopping the stream first (`CC` then `CA`) leaves the device unable to ACK, and a
bare write mid-stream is silently dropped. What the original editor does, all **while the stream is
still running** (no `CC`, no `CA`):

1. write a single **`0xFF`** byte (primes the device's command parser so it treats the following
   `F0…` as a command, not stream noise),
2. write **both** Config records (type 4) back-to-back — record #0 carries the new calibration
   (`value[17:33]`, MAX/toe at `[17+2p]`, MIN/heel at `[25+2p]`, 2-byte little-endian per pedal);
   record #1 is written unchanged,
3. read the device's single **`F0 09 F7`** ACK — it arrives only after the **last** record (record
   #0 alone draws no ACK),
4. re-send **`D2`** to resume the live stream.

> **Disconnect quirk:** after a calibration save the device often will not respond to the
> leave-Editor-Mode (`CC`) disconnect — the user must press the physical **[sel]** button. The
> original FAMC editor exhibits the same behaviour, so it is a device-firmware quirk, not an editor
> bug. (A session that didn't save calibration disconnects cleanly.) The dialog therefore writes
> during the live stream and resumes it; it only sends `CC`/`CA` on close.

**Not exposed over the *bulk* get-commands above:** Song (2), Setlist (5), Page (7) and IASwitch
(3) never returned from any bulk get-command (`01`–`20`, `C9`–`CF` all probed) — the device's
bulk editor-mode read set is a subset, the same situation the Router had (it exposed only
presets / loop-defs / global over USB that way).

### Per-record read — Song/Setlist/IASwitch, confirmed on hardware 2026-07-15

The bulk get-commands are not how the 2013 editor read these types. It requested records **one
at a time** with a different frame — `F0 00 00 <id> 00 <cmd> 02 <recnum as 4 nibbles> F7`, cmd
`0x0A` preset, **`0x0B` song**, `0x09` sysex-msg, **`0x0C` ia-switch**, **`0x0D` setlist**,
`0x0E` config, `0x0F` connection-test (decompiled `MidiFootController.SendMsg`) — and got back
one genuine, nibble-encoded `.syx` record frame per request. **This framing still works on the
modern serial link**, confirmed with `scripts/probe_per_record.py` against a real Liquid Foot+
12+: Song, Setlist, and IASwitch all answered, byte-identical to the on-disk `.syx` format, both
with and without the Editor-Mode handshake first. `recnum` is **0-based and matches the on-disk
record number exactly** (verified: requesting recnum=1 returns the on-disk `rec_num=1` record).

This is why the original editor could transfer Songs/Set-Lists over USB and the bulk-only path
couldn't — see `lfeditor/comms/protocol.py`'s `FOOT_PER_RECORD_CMDS` / `pull_records_per_record`
/ `pull_one_record_per_record`, wired into the desktop app and the web WebSerial bridge
(`lfeditor/webapi.py`'s `dev_per_record_cmds`/`dev_per_record_command`/`dev_ingest_per_record`,
`web/serial.js`'s `Device.pull()`). Because it's ~562 individual round trips (254+128+180
records), it's noticeably slower than the bulk path — expect it to dominate a full "From LF+".

**Still not exposed over USB by any known request:** Page (7) — the 2013 editor's own `SendMsg`
command table has no case for `GET_PAGE` at all, so there's no known per-record command either.
Edit Pages offline in the `.syx`, or capture the real editor's full read sequence (DYLD
interposer) to look for one.

**Write path for these types is NOT yet verified** — only the read direction has been tested on
hardware. They stay read-only over USB (not in `_writable_types()`) until a write is confirmed.

### Channel MIDI on the UART — confirmed 2026-07-15 (the "USB MIDI" recovery)

With the device global **"Allow MIDI CMDS = YES"** (Config rec 0 `value[47]`; also gated on the
global MIDI channel, `value[49]`), the LF+ **acts on channel-voice MIDI sent raw down the
USB-serial link**: Bank CC#0 + Program Change switches presets, and the manual's CC#1–8 trigger
set applies (IA on/off/bypass/toggle, page functions, MTC stop/play/cancel). Confirmed on a real
LF+ 12+ via `scripts/probe_midi_cmds.py` — the LCD followed PC changes sent at 230400 baud on a
raw port. Two hard limits, both firmware-side:

* **Editor Mode discards MIDI commands.** A PC sent mid-session is not processed (verified: sent
  "go to preset 4" in Editor Mode, exited — device still on preset 1). Editor transfers and MIDI
  command input are mutually exclusive uses of the link.
* Realtime (clock etc.) stays ignored in every state, and the device never sources MIDI on the
  UART (the complete capture vocabulary above has no device→host stream) — so this is a one-way,
  commands-only channel, not a full USB-MIDI port.

The editor's **Hardware ▸ USB MIDI In Bridge** (`lfeditor/ui/midi_bridge.py`) builds on this: it
opens the port raw (no handshake), creates a virtual MIDI input ("LF+ USB") on macOS/Linux — or
listens on a loopMIDI port on Windows — and forwards CC/PC byte-identical, so a DAW can switch
presets and fire IA slots over the editor cable. Sysex/realtime are filtered out.

### The real editor's full session (DYLD-interposer capture)

A DYLD-interposer capture of the official LF+ Editor's serial traffic with a real Foot
(see `docs/HARDWARE_RE_CAPTURE.md` for the procedure) shows the complete protocol — and its
**entire** command vocabulary:

```
>>W f000007c0f0fc900000000f7   handshake (sent twice)
>>W f000007c0f0fcaf7           CA  — session begin (no reply)
>>W f000007c0f0f05f7           get presets   (then 0D ext9, 0F ext10 …)
   … device streams records …
>>W f000007c000101…f7          write Preset (type 01)
>>W f000007c000901…f7          write PresetExt9 (type 09)
>>W f000007c000a01…f7          write PresetExt10 (type 0A)
<<R f009f7 f009f7 f009f7        three writes → three F0 09 F7 ACKs
```

So a "full preset" write is **three records** (main + ext9 + ext10), and the device **ACKs every
write**. On **disconnect** the editor sends one more control frame — `F0 00 00 7C 0F 0F CC F7`
(**CC = leave Editor Mode**) — then closes the port; the device's LCD returns to normal. (An
earlier, *truncated* capture had cut off before the disconnect, which is why this was first
mis-recorded as "no exit command exists" — re-capturing the full connect→disconnect session with
the interposer revealed the `CC` frame.)

### Writing (ACK- and read-back-verified, reversible)

```
1. open @230400, DTR+RTS;  send  F0 00 00 7C 0F 0F C9 …F7  then  F0 00 00 7C 0F 0F CA F7
2. send the record frame    F0 00 00 7C 00 <type> 01 <recnum> <len> <nibbles> 00 F7
3. device replies  F0 09 F7  (ACK).  A read-back of the record double-confirms it.
```

Proven by a staged test on preset #384 (the default "Pre #384" patch), with a full backup first:
**identity-write → change nick → read-back showed only bytes [16:23] changed (surgical, no
collateral corruption) → restore original frame → read-back byte-identical to baseline.** Also
verified end-to-end through the wired `send_record()` (ACK `True`, read-back confirmed, restored).
`lfeditor/comms/protocol.py::_synth_frame` rebuilds a writeable frame from decoded values; verified
it re-encodes **byte-identically** to the device's real frame for all 7 readable types.

## Robustness notes (learned the hard way)

- **Don't hammer reconnects and don't drop DTR.** Rapid connect/disconnect cycles — and
  especially toggling `DTR`/`RTS` *low* — left the device unresponsive (handshake returned 0
  bytes). Recovery: wait a few seconds and re-open cleanly (DTR/RTS high, 0.5 s settle).
  `connect()` retries up to 6× with 1.5 s gaps and never drops DTR.
- The handshake reply is 29 bytes (`F0 05 00 7C 06 20 4B 01 00 0A …`); its body carries device
  status/info (unparsed — not needed for read/write).
- **Leaving Editor Mode is a software command: `CC`.** `connect()`/`disconnect()` mirror the real
  editor — handshake `C9` + `CA` on connect, `CC` + port-close on disconnect — so the device's LCD
  returns to normal automatically (the physical `[sel]` is only needed if a session is aborted
  without sending `CC`). Verified on hardware: `CC` is exactly what the editor's CONNECT-toggle-off
  emits. (Note: get-commands keep working even outside Editor Mode — that LCD state gates the
  display, not the protocol — so "did `CC` exit?" can't be detected from the serial side; the
  capture + the unit's LCD are the ground truth.)
- Records stream in 62-byte FTDI read packets (62 data + 2 status per 64-byte USB frame); the
  transport just drains until idle, so this is transparent.

## Reproduce

```bash
python scripts/lf_usb.py pull --save out.bin     # handshake + default get-cmds, save raw
python scripts/lf_usb.py probe                    # probe each get-command individually
```

…or through the wired API (`lfeditor/comms/`):

```python
from lfeditor.comms import SerialTransport, connect, pull_dump, MODEL_FOOT, find_serial_ports
t = SerialTransport(find_serial_ports()[0].name)
connect(t, MODEL_FOOT)            # enter Editor Mode
dump = pull_dump(t, MODEL_FOOT)   # -> codec Dump (Preset/Ext9/Ext10/SysexMsg/Config/IAMap/SongExt11)
t.close()
```

Writes go through `send_record(transport, frame, allow_write=True, verify_read=...)` — disabled
unless `allow_write=True` is passed explicitly.
