# Liquid Foot+ USB-Direct — read & write SOLVED on hardware (2026-06-15)

> **Status: read and write both working** over a single USB cable from a modern Apple-Silicon
> Mac, no kext / DriverKit extension / Developer account. Validated against a real Liquid Foot+
> (a full 384-preset reference rig). This is the source of truth for `lfeditor/comms/`.
> The same protocol also works from the **browser** (WebSerial, Chrome/Edge): verified on the
> same hardware 2026-07-13 — see [WEBSERIAL.md](WEBSERIAL.md). Song/Setlist/IASwitch also
> transfer over USB via a per-record request, confirmed 2026-07-15 (below), and as of 2026-07-16
> **every one of Page/Song/Setlist/IASwitch has a hardware-confirmed bulk read command too**
> (0x06/0x07/0x08/0x09 — see below), with the per-record path kept as an automatic fallback.
> Every record type is now writable as well as readable, including per-record types, which get
> an extra readback-and-compare check the bulk path doesn't need (below).

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
| `0x0E` | Firmware data stream (not a stored record type) | — | — | 24001 | see note below |
| `0x06` | IASwitch (3) | 250 | 180 | 45001 | ✅ found + verified 2026-07-16, see below |
| `0x07` | Page (7) | 210 | 50 | 10501 | ✅ found + verified 2026-07-16, see below |
| `0x08` | Song (2) | 125 | 254 | 31751 | ✅ found + verified 2026-07-16, see below |
| `0x09` | Setlist (5) | 90 | 128 | 11521 | ✅ found + verified 2026-07-16, see below |

`0x0E`'s stream was originally logged as an "aux IA-sync *display* stream" from its shape; the
v6.31 disassembly (below) resolves it as `Get_All_Firmware_Data` — a firmware-data read, still
not a stored user record type either way, so it's still intentionally excluded from
`FOOT_READ_CMDS`.

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

**2026-06-15 finding, since corrected 2026-07-16 (see below):** at the time, Song (2), Setlist
(5), Page (7) and IASwitch (3) never returned from any bulk get-command in a manual probe
(`01`–`20`, `C9`–`CF`) — the device's bulk editor-mode read set looked like a subset, the same
situation the Router had (it exposed only presets / loop-defs / global over USB that way). This
led to the per-record fallback below for Song/Setlist/IASwitch, and Page being treated as
unreachable by any known request. A JR+ tester's 2026-07-16 report that the *original* editor
reads Pages and writes Songs over USB prompted a second look — see "Bulk Page/Song/Setlist"
below, which found the earlier probe's negative result was apparently a false negative (timeout
or session-state artifact), not a real device limit. IASwitch (3) turned out to have a bulk
command too (0x06) — found live on hardware, not in the disassembly (see below).

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
`web/serial.js`'s `Device.pull()`). Song/Setlist/IASwitch each later gained a bulk command too
(0x08/0x09/0x06 — see "Bulk Page/Song/Setlist/IASwitch" below), so as of 2026-07-16 this
~562-round-trip path (254+128+180 records) is a **fallback**, only exercised for whichever of
the three a device doesn't answer over bulk — `pull_dump()` picks per type automatically.

**Read timing, fixed 2026-07-16.** A forum report of "From LF+" hanging on "reading device…"
traced to two issues, both now fixed: (1) each reply is a single bounded frame (device goes
quiet right after), but the original read used an idle-timeout drain that waits `idle_timeout`
seconds of silence *after* the frame's own `F7` terminator before returning — a fixed 0.3s tax
on *every* request, ~2.8 minutes of pure removable overhead across 562 requests, even when
every request succeeds instantly. This — not device stalls — is why the original editor felt
much faster. Fixed with `SerialTransport.read_one_frame()` / `MidiTransport.read_one_frame()`
(`lfeditor/comms/transport.py`), which return the instant a complete frame is seen; mirrored in
`web/serial.js` as `WebSerialLink.drainOneFrame()`. (2) A device that stops answering per-record
requests entirely (older firmware, a wedged link) would otherwise burn the full per-request
timeout on every remaining slot — up to ~28 minutes with zero UI feedback. Fixed with a bounded
consecutive-miss bail-out (`MAX_CONSECUTIVE_MISSES = 30` in protocol.py, mirrored in serial.js)
plus live "(done/total)" progress on both desktop and web, so a genuinely slow/failing pull is
now visible and bounded instead of indistinguishable from a hang.

### Bulk Page/Song/Setlist/IASwitch (0x06/0x07/0x08/0x09) — found + hardware-verified 2026-07-16

A JR+ tester reported that v0.0.7 refused to write Songs and never pulled Pages, while the
*original* v6.31 macOS editor does both routinely. Disassembling that original editor (installed
locally, Xojo compiler, full symbol table intact) found `Window1.Get_All_Pages`,
`Window1.Get_All_Songs`, and `Window1.Get_All_SetLists` — each builds exactly the bulk frame
`F0 00 00 7C 0F 0F <X> F7` with **X = 0x07 (Page), 0x08 (Song), 0x09 (Setlist)**. This is
trustworthy because the *same* disassembly's other `Get_All_*` methods reproduced every one of
our already-hardware-confirmed bulk cmd bytes exactly (Preset 0x05, Sysex 0x0A, Config 0x0B,
IASlotMapping 0x0C, IALabels 0x0D, MAPLabels 0x0F, SongPresetLabels(SongExt11) 0x10) plus
resolved 0x0E as `Get_All_Firmware_Data` — nothing in the method contradicted known behavior, so
there was no reason to doubt the three new ones (`Window1.Get_All_IASlots`' own command byte is
computed at runtime in that binary, so it didn't show up in the disassembly at all).

Two real backups from the tester (his most recent pull with the original editor, and a pull with
our own per-record-based v0.0.7) were compared offline: every shared record type — including
Setlists and IASwitches, both already per-record-only in our editor — matched byte-for-byte, and
the tester's JR+ reported the identical 384/254/128/180 record ceilings this codebase already
assumes. So the model differences (JR+ vs 12+ vs Mini vs Pro+) are **not** the cause of either
bug; both were this editor's own conservative gating. `_synth_frame`'s header template (already
used for the other bulk types) was verified to round-trip Page/Song/Setlist byte-identically
against both real backups (0 mismatches across 432 and 382 records respectively) using each
record's on-disk `(rec_num, values)` — the missing piece was purely the read/write commands.

**Confirmed on a real LF+ 12+ the same day**, via `scripts/probe_bulk_pages.py`
(read-only): 0x07/0x08/0x09 all answered with exactly the expected reply length (Page
50×210+1=10501 bytes, Song 254×125+1=31751, Setlist 128×90+1=11521), and a cross-check of bulk
Song's first record against the already-proven per-record path (0x0B, rec 0) was byte-identical.
The probe's exploratory scan of neighboring unmapped bytes (looking for a 4th undiscovered bulk
type) turned up a bonus: **0x06 also answers, with IASwitch (3) data** — 180×250+1=45001 bytes,
content matching real IA-slot effect names ("Sound Sculpture Fun", "Keeley Compress Comp") and
the Step Names field, byte-identical to per-record IASwitch rec 0. So all four previously
per-record-only types (Page/Song/Setlist/IASwitch) now have a confirmed bulk equivalent, and
`FOOT_READ_CMDS` includes all four (`0x06`/`0x07`/`0x08`/`0x09`).

**Writes.** The decompiled 2013 editor's `SetSong`/`Song.SetToSysex` (and the Preset/Setlist/
IASwitch/Page equivalents) write a record by sending its own `.syx` dump frame — exactly what
`send_record()` already does for Preset. So every type's write path is now enabled
(`_writable_types()` == `_read_types()`), with one addition: per-record types (Song/Setlist/
IASwitch) don't get the same degree of independent hardware confirmation the bulk-path write
does, since their write-frame format was inferred rather than captured from a live original-
editor write session — so `_send_all()` reads each per-record write back afterward and compares
bytes before calling it a success, rather than trusting the device's `F0 09 F7` ACK alone.

Both `pull_dump()` and `Device.pull()` (web) still keep the per-record fallback for defense in
depth: they automatically fall back to the per-record path for any of Song/Setlist/IASwitch the
bulk phase doesn't answer on a given device/firmware, so this degrades gracefully rather than
losing data even outside the one 12+ unit this was verified against.

### Live bidirectional MIDI on the UART — confirmed 2026-07-18

A DYLD serial-interposer capture of the original editor's **MIDI Pass Thru** utility identified
the missing gate. The earlier `scripts/probe_usb_midi.py` experiment listened on a raw port,
inside Editor Mode, and after `CC`, but never sent `CF`; its silence showed only that LF+ output
is not unsolicited in those states. It did **not** test the gated live-MIDI mode.

The captured start sequence is byte-exact:

```text
F0 00 00 7C 0F 0F C9 00 00 00 00 F7   C9 identification handshake (reply required)
F0 00 00 7C 0F 0F CA F7               CA session/pass-thru setup (no reply observed)
F0 00 00 7C 0F 0F CF F7               CF start live USB-MIDI stream
```

After `CF`, the LF+ leaves Editor Mode visually, returns to its normal preset/control display,
and keeps its physical switches active. Switch-generated MIDI appears as ordinary raw channel
bytes on the still-open FTDI connection, for example:

```text
B2 00 00   B2 20 00   C2 01   B2 45 00
```

The same serial connection accepts the already-proven computer→LF+ CC/PC route. That direction
still requires device global **"Allow MIDI in = YES"** (Config rec 0 `value[47]`) and the
matching global MIDI channel (`value[49]`). Editor record transfer and live bridge streaming stay
mutually exclusive owners of the link.

The captured stop command is:

```text
F0 00 00 7C 0F 0F CC F7               CC stop live USB-MIDI stream
```

`CC` stops LF+→computer transmission while leaving the hardware in its normal display. It is a
context-sensitive stop control: ordinary editor disconnect also uses it before close, and
expression-pedal live view uses it before re-entering its editor session. Bytes already buffered
or in flight after `CC` must be discarded.

The editor's **Hardware ▸ USB MIDI Bridge** (`lfeditor/ui/midi_bridge.py`) implements this mode in
place of the former one-way assumption. macOS/Linux get one virtual input/output endpoint pair
named **"LF+ IN PORT / LF+ OUT PORT"**; Windows retains user-selected existing loopback endpoints because
python-rtmidi cannot create native virtual ports there. Computer-originated SysEx is never put on
the UART. Computer→LF+ forwards CC/PC plus `F8` Clock, `FA` Start, `FB` Continue, and `FC` Stop;
`FE` Active Sensing and `FF` System Reset remain blocked. LF+-originated channel messages are
parsed across fragmented reads and running status, and safe realtime (`F8`, `FA`–`FC`, `FE`) is
republished without changing parser state. `FF` remains filtered.

LF+-originated SysEx is forwarded only when every payload byte is valid 7-bit MIDI and the frame
does not match a known FAMC shape (`F0 00 00 7C…`, `F0 05 00 7C…`, or `F0 09…`). Those FAMC-
looking frames remain blocked even if user-programmed because they are indistinguishable from
editor/control, device-reply, and ACK traffic on the shared carrier. Malformed/oversized frames
are bounded and filtered.

### The real editor's full record-editing session (DYLD-interposer capture)

A DYLD-interposer capture of the official LF+ Editor's serial traffic with a real Foot
(see `docs/HARDWARE_RE_CAPTURE.md` for the procedure) shows the complete ordinary
**record-editing** sequence. The separate MIDI Pass Thru capture above adds `CF`:

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
(**CC stops/leaves Editor Mode in this record-session context**) — then closes the port; the
device's LCD returns to normal. (An
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
