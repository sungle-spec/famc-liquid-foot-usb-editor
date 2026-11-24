# Firmware archive — what each version changes, and what it means for the editor

Analysis of the firmware files shipped in `reference/Liquid Foot/Firmware/` (v3.35 → **v6.32**,
the last release). This is **reference/RE only** — the native editor does **not** flash firmware
(see "Flashing" below). The goal here is to understand (a) the upload format, (b) what the firmware
changes that the editor must keep up with, and (c) whether anything reveals editor features we're
missing.

## File format & upload protocol

Firmware ships as **sysex `.syx` images**, one per hardware variant, in
`LF_PLUS_firmware_v6_32/`:

| File | Bytes | Model |
|---|---|---|
| `LF+MINI_FIRM.syx` | 244,504 | Mini |
| `LF+12_FIRM.syx`   | 247,320 | 12 |
| `LF+JR+_FIRM.syx`  | 254,744 | JR+ |
| `LF+12+_FIRM.syx`  | 256,536 | 12+ |
| `LF+PRO+_FIRM.syx` | 256,792 | Pro+ |

Each file is a **single** sysex frame (one `F0 … F7`), header:

```
F0 00 00 7C 08 06 01 00 00 03 …(nibble payload)… F7
   └──┬──┘  │  └──────┬──────┘
   FAMC ID  │   13-byte header incl. model + version (see "Decoded format")
            └─ 08 = FIRMWARE UPLOAD command
```

Key facts:
- `00 00 7C` is the FAMC manufacturer ID (same as backups).
- The **command byte is `08`** — distinct from `0F` (backup/dump + Editor-Mode handshake) and the
  per-record write opcodes the editor already speaks. This is the one new opcode a flasher uses.
- **The whole body is now decoded (2026-11-09, verified on 332/332 images, v3.34 → v6.32)** — see
  "Decoded format" below and `lffirmware/codec.py`. This supersedes the earlier notes that the
  payload was an opaque nibble stream and that "the model is implicit in the binary": the header
  carries the **model letter** and **version**, and the unit's MCU is a **PIC18**.

### Decoded format (`lffirmware/codec.py`)
```
F0 00 00 7C 08 06 | header (13) | payload (N nibbles) | trailer (4 nibbles) | F7
header  = 01 00 00 | blocks (3 nibbles) | 00 00 00 00 | major (nibble) | minor (raw, decimal) | model (ASCII)
payload = the PIC18 program image; every byte sent high nibble first, each nibble XOR 0x5;
          bytes are 16-bit words HIGH byte first (the MCU is little-endian → swap each pair)
trailer = 16-bit sum of the payload nibbles (raw), hi nibble first
```
- `blocks × 128` = image length in bytes (12+ v6.32: 1002 × 128 = 128,256).
- Model letters: **Mini `F`, 12 `J`, 12+ `K`, JR+ `L`, Pro+ `H`** (so the model *can* be read from the
  file; the loader now does, and refuses a filename that contradicts the header).
- Version: major in the header nibble, minor as a decimal byte (`0x20` = 32 → v6.32).
- **There is no signature and no encryption — only the 16-bit nibble sum.** That is what makes an
  image machine-readable *and* what makes patching technically possible; it is also why a
  corrupt-but-checksummed image is only stopped by the device's own bootloader. Treat custom images
  as brick-risk until a bricked-unit volunteer proves the path.
- The image starts with three PIC18 `GOTO`s (12+ v6.32): reset `0x0000` → `0x1F800`, i.e. the
  boot-loader region *above* the image, which is not part of the `.syx`; `0x0004` → `0x1D6AE`, the
  application start; `0x0008` → `0x1D4D0`, the interrupt handler. (An earlier note here called the
  last two "high/low interrupt"; that was wrong — see "Inside the image".)
- `python -m lffirmware --image X.syx --decode out.bin` writes the little-endian PIC18 memory image;
  Ghidra's `PIC-18:LE:24:PIC-18` language loads it and finds `Reset`, `HighInterrupt`, `LowInterrupt`
  and ~335 LCD strings (the unit's whole menu text table at `0x1E083…`, plus `Waiting`, `KEMPER`,
  `AXE-FX III`, `Reset Pre Pg Functions`, …).

### Inside the image (`lffirmware/pic18.py`, 2026-11-16)

A small, read-only PIC18 disassembler lets us *read* the decoded image (it never runs or patches
it). A recursive trace from the vectors decodes about **95 %** of every v6.32 image as reachable
code with **zero decode failures** in all five models, and finds ~320 functions. `python -m
lffirmware --image X.syx --inspect` prints the summary below for any image.

Everything in this section was read from the v6.32 application images. The boot loader is **not**
in any `.syx`, so nothing here describes what it does — that is called out where it matters.

**Vectors.** `0x0000` reset → `GOTO 0x1F800` (boot loader, above the image). `0x0004` → the
application start; nothing inside the image jumps there, so it is the boot loader's hand-off point
(inferred). `0x0008` → the interrupt handler (PIC18 high-priority vector). `0x0018` (low-priority
vector) is `BRA 0x0000`, i.e. unused.

**How the unit takes an update.** One routine (`0x409C` in the 12+ image; same logic in all five)
receives firmware. It has four call sites: two in the start-up code (one behind a button check,
consistent with the manual's hold-B7-at-power-on), one that looks like the on-device menu
(inferred), and one for editor control byte **`C8`** (new — see below). It then:

1. shows `Firmware Waiting` and reads the frame from **whichever serial port has data** — the
   code checks both, including the port the editor protocol runs on. (The 2013 editor used MIDI IN;
   whether the editor cable also works is untested.)
2. checks the frame as it arrives and **stores the image in external memory** through the port
   latches. The application contains **no code that writes program flash** (no table-write
   instruction anywhere, tested for every model), so receiving cannot damage the running firmware;
3. after the last byte checks the `F7`, the checksum trailer and the model letter, then reads the
   stored copy back and compares a second checksum;
4. only if everything passes, writes an "update pending" record to EEPROM `0x3F5–0x3FD` (flag,
   marker `D9`, version digits, model letter, block count) and jumps to the boot loader, which does
   the actual flashing.

**Error numbers.** A failed check shows `Firmware Failed` / `Error N` (decimal) for a few seconds
and returns with the installed firmware unchanged. `python -m lffirmware --explain-error N`:

| N | Check that failed |
|---|---|
| 1 | header stopped arriving |
| 22 | frame byte 3 is not the unit's ID (`7C`) |
| 23 / 24 | command bytes are not `08` / `06` |
| 25 | second header byte (a flag) is not 0 or 1 |
| 26 | block count is 0 or above **1007** (`0x3EF`; 1007 × 128 = `0x1F780`, just under the boot loader) |
| 27 / 28 | data stopped arriving mid-image (per-byte timeout, roughly a tenth of a second on the MIDI port) |
| 29 | checksum trailer stopped arriving |
| 30 | no `F7` where the block count says the frame ends |
| 31 / 32 | data sum, or trailer, is zero |
| 33 | trailer ≠ 16-bit sum of the received nibbles |
| 34 | model letter ≠ this unit's model |
| 200 | stored copy failed read-back verification |

`tests/test_firmware_inspect.py` re-derives this list from each real image and fails if it drifts.
The 1007-block ceiling is v6.32's: one genuine old image (12+ v3.36) has 1008 blocks, so the host
reports the limit (check 26) but does not refuse the file. The `08 06 …` header also turns out to
be `01`, a 0/1 flag byte, then a **four**-nibble block count — the codec's "`01 00 00` + three
nibbles" reads the same bytes.

**What this means for safe loading.**
- The loader runs the same checks on the host (`lffirmware/inspect.py::device_preflight`), so a
  wrong-model, truncated or corrupt file is stopped before a byte is sent, and each check is shown
  with the number the unit would display.
- An interrupted or mangled *transfer* is caught by the unit (27–33) with nothing flashed.
- The model letter is enforced by the unit itself (34) — but it is a header byte, so it only
  protects against honest mix-ups, not a mislabelled image.
- **Not known:** what the boot loader does if its copy to flash is interrupted, and whether the
  power-on wait-for-firmware route still works when the application is damaged — the button check
  we can see lives in the application's start-up code. Treat "a bricked unit can always be rescued"
  as unproven.

**Editor control bytes the firmware handles.** Its dispatcher compares the control byte against
`C8`–`D2`. Known before: `C9` identify, `CA` session, `CB`/`CF` thru/stream start, `CC` stop, `D0`
reset config, `D1` factory reset. New from the image: **`C8` enters firmware-wait** from the
running application (no button hold needed; documented, not used by the loader). `D2` streams the four pedal values live. `CD`/`CE` load a serial baud-rate constant — `0x01FF`
(31250, MIDI) versus `0x0044` (about 230400, also the start-up default) — so they appear to switch the link
speed; that is an *inference* from the constants, not confirmed on hardware. See
[TROUBLESHOOTING_UNIT.md](TROUBLESHOOTING_UNIT.md).

`PIC-18:LE:24:PIC-18` in Ghidra loads the same `--decode` output for cross-checking.

### Flashing — now in a separate beta tool, still NOT in the editor
Writing this image to the device is the one genuinely **brick-risk** operation (an
interrupted/incorrect write kills the unit). The protocol turned out to be simpler than feared:
the decompiled 2013 editor streams the whole image as a **single MIDI sysex message** (no
app-level handshake), and the device has a firmware-independent rescue mode (hold **B7 at
power-on** → "wait for MIDI Firmware", manual p.15). A standalone **LF+ Firmware Loader
(beta)** implements exactly that plus image verification against a SHA-256 allowlist of 241
known FAMC releases — see [FIRMWARE_LOADER.md](FIRMWARE_LOADER.md) for the tool and its
community-testing ladder. The editor's own *Load Firmware* menu item stays disabled until that
validation completes.

## What the firmware changes (and the editor must track)

The firmware is where the **features** live; the editor is just a programmer for the bytes those
features read. The big jump is **v5.x → v6.x** (a new "V6 processing engine"). Almost everything
new is in three areas the editor already exposes as record fields:

### 1. External-device sync (AXE-FX III, Kemper) — the largest set of changes
- **AXE-FX III "Smart Sync"** (v6.00): once an IA-Slot's *Sync Effect* is chosen, the firmware
  handles all MIDI automatically — **no command programming needed**. New sync targets: per-effect
  **bypass**, **CHANNEL select** with a **`CHAN CYCLE RANGE`** parameter (A / A-B / A-B-C / all),
  **SCENE 1–8** (auto-named in real time), **TUNER**, **TAP-TEMPO**, **LOOPER** functions.
- **Kemper Performance mode** (v6.00): IA-Slots can sync to **Performance Rig Slots 1–5**, plus
  **PERF UP/DOWN**, TUNER, TAP — full "remote control" with no programming. Mode auto-detected.
- v6.20–6.32: many sync correctness fixes; v6.32 lets AXE-FX III *Sync-to-SCENE* process ON **and**
  BYPASS commands.

→ **Editor relevance:** these are the *Sync device* / *Sync effect* dropdowns on the **IA-Slot**
tab. The set of selectable effects/targets and the `CHAN CYCLE RANGE` / spillover parameters are
firmware-defined. We model the underlying bytes; the *enumerations* (effect lists, Kemper labels)
are the part most likely to need expanding to match v6.32. The original editor ships these as an
**internal database** pushed to the device ("UPDATE INTERNAL DATA" — see below).

### 2. New per-record parameters (all are editor fields)
- **Preset:** `SYNC IA STATE`, `RESEND INITIAL IA STATE`, and **Level-1 time Sync/Save** (capture
  effect states once, then fast-trigger).
- **IA-Slot:** `Allow Preset Resend` (v6.00, default OFF); spillover variant selection for
  Kemper delay/reverb.
- **Song:** *Resend Programming commands with each preset Retrigger* (v6.20).
- **Sysex messages:** **PRE** and **POST** message links (POST replaces the old single "Message
  Link"); a value **`FF` inside an `F0…F7` block = auto-checksum**, `FF` **outside** a block =
  stop-send. (We already surface Pre/Post links + the MMC generator.)
- **Expression pedals:** HEEL/TOE can trigger IA-Slots (STOMP / QUICK-TAP / TAP-TEMPO types).
- **Programming commands:** `PC_UP`/`PC_DOWN` gained a **MIDI-channel** parameter; `EXT DEV CHANGE
  CHANNEL` → `EXT DEV CHANGE BYPASS/CHANNEL`; new `CHANGE EXT DEVICE CHANNEL`; tap-tempo range
  widened to 50–300 BPM.

→ **Editor relevance:** we already expose Sync device/effect, Pre/Post Sysex links, MMC, Heel/Toe
triggers, Group-post-trigger, Combo-blocking, End-of-list cycle, MTC, etc. (verified in
`ui/specs.py`). The data model is **byte-exact and lossless**, so even parameters we don't yet
surface as named widgets round-trip safely. The gap, where any, is *naming* a few v6 parameter
bits as friendly controls — not missing storage.

### 3. Display / engine behaviour (no editor bytes)
2nd-function display rules, tuner "all buttons green when in tune", MIDI-clock 50–255 BPM,
double-tap latency, expander ("X-Series") going out of beta. These are runtime behaviours with no
stored field — nothing for the editor to add.

> **The original "USB MIDI function" is recovered bidirectionally.** A 2026-07-18 DYLD serial-
> interposer capture of the original editor's MIDI Pass Thru utility found the missing `CF`
> gate: normal identification handshake `C9`, setup `CA`, then `CF` starts live raw MIDI on the
> still-open FTDI UART. The LF+ returns to its normal display, physical switches work, and their
> channel MIDI is read by the editor and republished through its CoreMIDI source. `CC` stops that
> output stream before close.
>
> This supersedes the earlier negative inference from `scripts/probe_usb_midi.py`. That probe
> listened on a raw port, in Editor Mode, and after `CC`, but never issued `CF`; its silence only
> proved that LF+ output is not unsolicited in those states. It could not rule out the gated
> pass-thru mode.
>
> The opposite route is also hardware-confirmed: with global **"Allow MIDI in = YES"**, the LF+
> processes Bank/PC/CC-trigger messages received on the same serial connection. The manual's
> receive chart supports keeping that direction conservative: Bank Change, Program Change,
> Trigger IA (ON/OFF/BYPASS/TOGGLE), Page functions, and MTC Stop/Play/Cancel are PC/CC messages.
> This does not limit what user programming may emit in the LF+→computer direction.
>
> Realtime/clock reception was not re-verified inside the newly identified `CF` session. The
> bridge now forwards computer→LF+ Clock/Start/Continue/Stop for validation against the LF+'s
> known DIN-clock behaviour, but still blocks Active Sensing, System Reset, and all computer
> SysEx. LF+→computer forwards Clock/Start/Continue/Stop/Active Sensing without disturbing
> running status; System Reset remains filtered.
>
> Ordinary LF+-generated 7-bit SysEx is forwarded only when it does not match known FAMC
> control/reply/ACK frame shapes. FAMC-looking, malformed, and non-7-bit frames stay filtered
> because they cannot be distinguished safely from editor protocol traffic on this carrier.
> Full sequences and filtering details are in [LF_USB_DIRECT.md](LF_USB_DIRECT.md) ("Live
> bidirectional MIDI on the UART").

## Does the firmware reveal editor features we're missing?

The firmware itself mostly confirms fields we already model. The **editor** release notes
(`reference/EreleaseNotes.txt`) are where the missing-feature signal actually is — host-side
productivity features the original app had that our rebuild doesn't yet:

| Original-editor feature | Source (notes) | Have it? |
|---|---|---|
| **Copy / paste** a whole record or a text field | (standard Edit menu) | ✅ done |
| **CSV Import/Export** of Presets/Songs/Set-Lists/Sysex | Editor v4.66 | ✅ done (format matches original) |
| **Reports** (Preset/Song/Set-List → CSV) | v4.55/4.70 | ✅ done |
| **Find / Select / Reporting** ("Q-LIST": search by MIDI chan/CC#/PC#/command) | v4.55 | ✅ done |
| **Drag-drop from Quick-Pick list** into a command row (auto-builds the command) | v6.02/6.22 | ✅ done (Find result → slot picker / IA-Slot → command row) |
| **Right-click a toggle → apply across many presets** (multi-preset quick edit) | v6.22 | ✅ done |
| **Quick Repeated Command Programmer** (fill a row across a record range, auto-inc PC#) | v4.55 | ✅ done |
| **Re-order presets/songs → auto-rewrite references** (Save/Sync) | v4.62/6.22 | ✅ done (Song/Set-List slot refs; command-ref rewrite needs un-RE'd jump func codes) |
| **MIDI Monitor / MIDI Pass-Thru** utilities | v4.55 | ✅ done |
| Command **"helpers"** (type `129bpm`, `120ms`, or note name `C#4`) | v4.55 | ⛔ not yet |
| **"UPDATE INTERNAL DATA / DATABASE"** push on first v6 connect (effect-name tables) | fw v6.00 / editor | ⚠️ tables recovered (`model/sync_effects.py`), frame + checksum builders added; the send path is not enabled (needs a capture) |
| `DELETE` clears a command, `ESC` restores | v6.02/4.90 | ⛔ partial |

**Highest-value, lowest-risk to add next** (all offline, all on data we already decode):
1. ~~**Copy/paste** (record + field)~~ — done.
2. ~~**CSV Import/Export** and **Reports**~~ — done; the format was captured byte-for-byte from the
   original editor (`tests/fixtures/golden_csv/`) and our export matches it (headers exact;
   set-lists byte-for-byte). IA-state glyphs `O/-` (our model is on/off; the original's `B`/`X`
   bypass/block aren't modelled), song preset 0/1–384, set-list song 1–254, sysex hex/dec.
3. ~~**Find/Q-LIST search** across records by MIDI chan/CC#/PC#/command~~ — done (`lfeditor/search.py`
   + the Find/Q-LIST dialog): name (wildcard) and MIDI-command (channel / type / CC#-PC#) queries,
   type + number-range filters, double-click to jump, export results to CSV.

The host-side feature set is now essentially complete: copy/paste, CSV import/export, Reports,
Find/Q-LIST, drag-drop, right-click multi-preset edits, MIDI monitor/pass-thru, the Quick Repeated
Command Programmer, and re-order-with-Save/Sync are all done. The main remaining gaps are
device-side (Phase 2 gated writes: reset/factory) and firmware flashing (Phase 3, brick-risk),
plus the one data-model gap of MOMENTARY/JUMP-TO-PRESET command function codes (which would let
re-order also rewrite command-table preset references, not just Song/Set-List slots).

The **"UPDATE INTERNAL DATA"** item is worth a flag: on first connect to a v6 device the original
editor pushes an internal effect/label database. *(Update 2026-11-09: decompiled — it is
`Set_All_Firmware_Data_effects`: header `0F 0F 72 0A`, then 5 devices × 200 slots × (16-char name +
8-char nick) = 24,000 bytes built from `Firmware_Effect_Labels`, then the unit echoes a 16-bit
byte-sum. The Axe-Fx III (175), Axe-Fx II (85) and Kemper (17 + 87 effect types) tables are now in
`lfeditor/model/sync_effects.py` and drive the IA-Slot "Sync effect" list. Still unknown: raw vs
nibble-encoded payload, devices 0/1. See [ORIGINAL_EDITOR_GAP_ANALYSIS.md](ORIGINAL_EDITOR_GAP_ANALYSIS.md).)*
That is why a unit with stale effect names needs the original editor's push; it is a device-write feature
(gated) and not needed for offline `.syx` editing.
