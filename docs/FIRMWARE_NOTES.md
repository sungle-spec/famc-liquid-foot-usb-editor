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
   FAMC ID  │   upload sub-header (same across all 5 models)
            └─ 08 = FIRMWARE UPLOAD command
```

Key facts:
- `00 00 7C` is the FAMC manufacturer ID (same as backups).
- The **command byte is `08`** — distinct from `0F` (backup/dump + Editor-Mode handshake) and the
  per-record write opcodes the editor already speaks. This is the one new opcode a future flasher
  would use.
- The payload is **nibble-encoded** — every byte is `0x00–0x0F`, i.e. 4 bits of real data per
  transmitted byte. So ~250 KB on the wire ≈ ~125 KB of actual MCU image.
- **The model is implicit in the binary** (different size/content), not a header field — bytes
  4–9 are identical across all five models. A flasher must therefore pick the right file for the
  connected model; it cannot derive the model from the firmware header.

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

> **On the original "USB MIDI function"** (asked about on the forum): with FAMC's old macOS
> driver the LF+ appeared as a native **CoreMIDI port** over USB, and the 2013 editor drove it
> entirely through `javax.sound.midi`. That driver-level MIDI port is what people remember —
> but even then, realtime **MIDI clock was never carried over USB** (no clock/thru code exists
> in the decompiled editor); tempo-LED sync has always been a MIDI-DIN-IN feature of the device
> firmware.
>
> **Confirmed on hardware 2026-07-15** (`scripts/probe_usb_midi.py`, a real Liquid Foot+ 12+):
> streamed MIDI realtime clock (`0xF8`, 24 ppqn) down the USB-serial link at 120 BPM across three
> device states — no handshake at all, mid-handshake, and just after leaving Editor Mode — with
> the tempo LED watched directly. **No reaction in any state**, across two runs. The device also
> never emitted a single byte on the UART on its own (tested by pressing buttons/switching
> presets while listening), ruling out a bidirectional USB-MIDI bridge too. The serial link is
> confirmed strictly one-way and non-MIDI in practice, exactly as the wire-format docs above say.
>
> **The official LF+ manual backs this up independently.** Its "MIDI Implementation" chart (the
> very last page, PDF p.97) lists the *complete* set of MIDI commands the device accepts —
> Bank Change, Program Change, Trigger IA (ON/OFF/BYPASS/TOGGLE), Page-function press, and MTC
> Stop/Play/Cancel — eight commands total, all standard PC/CC messages. **MIDI Clock isn't in
> that list at all, on either DIN or USB.** "Tap Tempo" (manual p.72) is the device *calculating
> and displaying* a tempo from foot taps, not receiving external clock; "Sync"/"External Sync"
> throughout the manual means AXE-FX/Kemper effect-parameter mirroring, a different feature
> entirely. So DIN clock-sync (if it works at all, per the forum report) isn't an officially
> documented device feature either — the editor cannot add or bridge what the firmware's own
> published MIDI implementation never advertised as a receivable command. Our MIDI Monitor /
> Pass-Thru already relays clock to a device's DIN input via any USB-MIDI interface, which
> remains the practical path for users who want external clock into the unit.
>
> **But the chart's commands DO work over USB — recovered 2026-07-15.** With the global
> "Allow MIDI CMDS = YES", the LF+ processes Bank/PC/CC-trigger messages arriving raw on the
> USB-serial link (hardware-confirmed; Editor Mode blocks them, so it's an either/or with
> record transfers). The editor's **Hardware ▸ USB MIDI In Bridge** exposes this as a virtual
> MIDI port ("LF+ USB") — a DAW can switch presets and fire IA slots over the editor cable,
> which is more than the original editor ever wired up. Full tiered verdict in
> [LF_USB_DIRECT.md](LF_USB_DIRECT.md) ("Channel MIDI on the UART").

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
| **"UPDATE INTERNAL DATA / DATABASE"** push on first v6 connect (effect-name tables) | fw v6.00 / editor | ⛔ not modelled |
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
editor pushes an internal effect/label database (e.g. Kemper effect labels through KPA fw 7.3.2).
That payload isn't in our data model; if a user's device shows stale effect names, that's why. It's
a device-write feature (gated, Phase 2+) and not needed for offline `.syx` editing.
