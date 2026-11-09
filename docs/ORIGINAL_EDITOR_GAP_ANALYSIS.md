# Original LF+ Editor v6.31 (Mac/Windows) — gap analysis & firmware leads

Date: 2026-11-09. Method: static string extraction from the shipped v6.31 Mac binary
(`/Applications/LF+ Editor.app`, x86_64 Xojo, 30 MB, 108k strings), diffed against the rebuild's
menus/windows, plus local analysis of the v6.31/v6.32 firmware images.

> **Status of REA ([morluto/rea](https://github.com/morluto/rea) v6.8.0, CLI via `npx`, no agent
> config touched):** run after user approval. What worked: `inspect-macho` (confirmed the Mac
> binary is **unstripped — 21,981 symbols**, `__XOJO` segment, built vs SDK 10.14),
> `inspect-byte-entropy`; after downloading **Ghidra 12.1.4** (REA rejects 12.2) and building its
> arm64 decompiler from the bundled source (the release ships only Linux/Windows decompilers),
> `rea decompile` works against the Mac binary (first import ~5 min; set
> `REA_GHIDRA_STARTUP_TIMEOUT_MS`, default 330 s is too short). What did not work:
> `inspect-firmware-regions` needs Linux + binwalk, and REA could not unpack the Windows
> installer itself (root-only inventory) — it is Inno Setup 5.5.7, so it was unpacked with
> `innoextract` instead (section 5f). The
> frame table in section 5a was recovered with `llvm-objdump` + `nm` symbols — see
> `scripts/extract_original_frames.py`; sections 5d–5e come from REA/Ghidra decompiles.
>
> **Windows build:** analysed in section 5f — feature-identical to the Mac build (same Xojo
> project); the inventory below applies to both.

## 1. Original v6.31 menu tree (recovered from the binary) vs. the rebuild

| Menu | Original item | Rebuild |
|---|---|---|
| File | Open / Save / Load Factory Defaults (Mini, JR+, 12+, Pro+) | ✅ |
| File | Load Special: Sync'd AXE-FX I/II · AXE-FX III Basic · Kemper · **Kemper Remote Control (Performance)** | ✅ templates loaded (`Factory_*` resources) |
| File | IMPORT / EXPORT (Presets, Songs, Set Lists, Sysex) | ✅ CSV |
| File | **Current Release Notes / Download New Versions** (+ `WindowNewInVersion`, `WindowReleaseNotes`) | ❌ |
| Edit | Cut / Copy / Paste / Find Commands | ✅ |
| Edit | **Undo (⌘Z), Insert (⌘I), Delete, Select All** | ❌ no undo stack |
| Utilities | **External Device Definitions** (⌘D) — import/export multiple, drag-drop to/from command rows | ❌ menu stub (disabled); tooltips already captured in `LF_TOOLTIPS.md` |
| Utilities | **External Device Sync (Kemper/AXE-FX)** — `WindowExtSyncParams` | ❌ menu stub (disabled) |
| Utilities | **Simulator Mode** (`MIDI_START_SIMULATOR_MODE`, Start/Stop/Clip/Clear All/Exit) | ❌ absent |
| Utilities | Quick Repeated Command Programmer | ✅ |
| Utilities | MIDI Device I/O Utility · MIDI Pass Thru Utility | ✅ (MIDI Monitor / Pass-Thru, USB bridge) |
| Hardware | Review/Install Latest Firmware · Load Firmware From File · Special Firmware Load (Forced) | ⛔ disabled; standalone `lffirmware` beta tool |
| Hardware | **Special – Update Internal Data** (`HardwareFirmwareDataUpdate`) | ❌ (already flagged in FIRMWARE_NOTES) |
| Hardware | Reset Config in LF+ (`MIDI_FORCE_CONFIG_RESET`) · Reset to Factory (`MIDI_FORCE_ALL_RESET`) | ⛔ disabled (gated Phase 2) |
| Hardware | Special – Clear Preset Labels / MAP Labels / Song Preset Labels | ✅ (Edit menu) |
| Reports | Filter / Report / Save (⌘⇧P) | ✅ |
| Complete Transfers | Get ALL from LF+ / Send ALL to LF+ | ✅ |
| Settings | Options/Preferences window (user/backup directories) | ⚠️ recent files + geometry only |
| Settings | AutoConnect on startup · AutoOpen Device Definitions | ❌ |
| Settings | Help pop-ups 30 s / 6 s | ❌ (rebuild has always-on tooltips) |
| Settings | **Show Stats When Opening Editor File** | ❌ (original shows the "384 Presets, 254 Songs…" summary) |
| Settings | Force default sizes · Restrict to one open editor · Reset positions/sizes · Display size presets (1400×900, 1195×670, 1024×768, 800×600) | ❌ (n/a for a resizable Qt app, except the stats/one-editor items) |

Other original windows found by class name: `WindowFindCommands` ✅, `WindowQuickProgram` ✅,
`WindowMIDI` / `WindowMIDI_Passthrough` ✅, `WindowOpenParams` (File-Filtering dialog on open) ⚠️,
`WindowPageView` ❌, `WindowIASlotList` ❌, `WindowExportData` ⚠️, `WindowPickSerialPort` ✅.

## 2. Ranked opportunities

1. **External Device Sync (Kemper / AXE-FX import)** — highest user value. The original reads
   presets/scenes/names *from* the Axe-Fx or Kemper and writes LF+ presets (modes: Preset→Preset,
   Preset→IA-Labels, Preset→Map Labels, Preset→Songs + Scene→Presets; Kemper Browser vs.
   Performance; options: import name / states / PC messages / auto IA setup / modify CC; ranges
   limited to 384 presets). All option strings and tooltips are in the binary. Needs a capture of
   the external-device MIDI exchange (Axe-Fx III / KPA) — or Axe-Fx/Kemper MIDI docs.
2. **External Device Definitions** — the data model behind the "drag a device effect onto a
   command row" feature. Tooltips are captured; file format and the definitions DB are not.
   **[needs RE]** for the on-disk format (look for `*.def`/XML via the `XML.dylib` usage).
3. **Simulator Mode** — host turns the unit into a button/expression simulator
   (`MIDI_START_SIMULATOR_MODE`). Useful for debugging a programmed rig without stepping on the
   unit. Capture with the existing `scripts/lf_interpose.c` + `capture_original.sh`.
4. **Undo/redo + Show Stats on open** — pure host-side, no hardware needed.
5. **Update Internal Data** — pushes the effect/label database to v6 units. Capture-then-replay
   (the payload ships inside the original app bundle; locate it in `Resources/`).
6. **Reset Config / Factory reset** — opcodes named in the binary; implement only behind the
   existing gated-write rules.

## 3. Firmware (v6.32 is the last release)

Facts established locally (all five models, v6.31 and v6.32):

- Single sysex frame `F0 00 00 7C 08 06 …`; the 13-byte pre-payload is `01 00 00 03 xx xx 00 00 00 00 06 20 yy`
  where `20 yy` is the only non-nibble pair and differs per model (`46` Mini, `48` Pro+, `4A` 12,
  `4B` 12+, `4C` JR+); the nibble pair just before it (frame offsets 10–11: `0e 0a` 12+, `0c 06` 12,
  `0e 03` JR+, `0b 0b` Mini, `0e 0b` Pro+) also varies per model. Bytes 4–9 are still identical across
  models as `FIRMWARE_NOTES.md` says, so the model marker (or a length/ID field) sits just after them.
- The last 4 payload nibbles are a trailer (differs per model → likely checksum/length).
- **The payload is not a plain nibble→byte packing.** Pairing nibbles yields long runs of `0x55`
  and `0xAA`, and the tail padding is a repeating 16-byte pattern
  (`55 AA BB 44 99 EE FF 88 DD 22 33 CC 11 66 77 00`) — i.e. the image is passed through a
  scrambler/encoder (zero/0xFF flash filler maps to `55`/`AA`). Entropy of the paired bytes is
  6.5 bits, so it is **not compressed or strongly encrypted**.
- v6.31 → v6.32 (12+): the first ~17.7 KB of wire bytes are identical, everything after differs
  (~80 % of bytes) — consistent with code shifting; a position-dependent cipher would show the same
  signature, so this alone does not settle it.
- The 2013 Java editor just streams the `.syx` untouched, so the encoder lives in FAMC's build
  tooling and the decoder in the unit's bootloader — **neither is in the repo**.

What this means for "new firmware features / debugging the controller":

- **Do not attempt patched firmware yet.** Producing a valid image needs the scrambler, the
  trailer algorithm, and the MCU architecture, none of which are recovered. A wrong image bricks
  the unit; the loader's own beta ladder is still unvalidated.
- **[needs RE]** First step is cracking the transform: (a) try Manchester/Gray/nibble-permutation
  models against the 55/AA structure on the five images, (b) once the plaintext is plausible,
  identify the MCU (reset vectors / instruction patterns) and load it in Ghidra. This is the
  right job for REA + Ghidra (installed, 12.2).
- **Achievable now without firmware surgery:** (a) surface v6.x parameter bits that
  `FIRMWARE_NOTES.md` says exist but aren't yet friendly controls; (b) add Simulator Mode and a
  record-level "device diff" (read device → compare to open file) as debug tooling; (c) use the
  decoded firmware release notes as a checklist for the IA-Slot sync-effect enumerations.

## 4. Status and next steps (updated 2026-11-09)

Done: REA/Ghidra analysis of the Mac binary, Windows build compared, sysex frame table, per-device
sync-effect tables (+ the Sync-effect dropdown fix), firmware format decoded, loader hardened, frame
builders added. Remaining, in value order:

1. **Hardware captures** ([HARDWARE_RE_CAPTURE.md](HARDWARE_RE_CAPTURE.md)): Simulator, `CB` vs `CF`,
   Update Internal Data, Axe-Fx/Kemper sync exchange. Nothing destructive is enabled without them.
2. **External Device Sync (Axe-Fx / Kemper import)** — option strings, modes and routines are known
   (`WindowExtSyncParams`: `AXE_SYNC`/`KEMPER_SYNC` are empty stubs; the work is in
   `LoadExternalData_*` / `AXE_SYNC_QuickProgram`, decompiles still pending) — needs an external unit to test.
3. **External Device Definitions** file format; selective **Export Data** dialog; **Undo/Redo**; open-file
   stats; release-notes window — host-side, no hardware.
4. **Custom firmware** — technically possible (no signature, 16-bit sum only) but brick-risk and
   untested; see §5g. Not recommended before a bricked-unit volunteer validates the loader path.

## 5. REA/disassembly findings (2026-11-09)

### 5a. Every sysex frame the original builds (`scripts/extract_original_frames.py`)
`<id>` = device-ID byte (0x7C on the LF+; computed at runtime, so idx 3 prints stale in the raw
extraction). All Foot frames use the `0F 0F` prefix + a control/command byte.

| Routine | Frame | In rebuild? |
|---|---|---|
| `LF_DEVICE_CONNECT` | `F0 00 00 <id> 0F 0F CA F7` | ✅ (SESSION_CTRL) |
| `Get_All_{Presets,Songs,SetLists,Pages,Sysex,Config,IAMapping,IALabels,MAPLabels,SongPresetLabels,FirmwareData}` | `… 0F 0F 05/08/09/07/0A/0B/0C/0D/0F/10/0E F7` | ✅ |
| `Set_All_Presets … SongPresetLabels` (bulk write) | `… 0F 0F 69 Presets · 6A IASlots · 6B Pages · 6C Songs · 6D SetLists · 6E Sysex · 70 IAMapping · 71 IALabels · 73 MAPLabels · 74 SongPresetLabels` (Config's opcode is computed, not literal) | ⚠️ rebuild writes per-record; bulk **Set_All** opcodes unused |
| `Set_All_Firmware_Data_effects` | `… 0F 0F 72 0A F7` — **this is "Update Internal Data"** (write side of Get-0x0E) | ❌ |
| `MIDI_FORCE_CONFIG_RESET` | `… 0F 0F D0 00 00 00 00 F7` | ❌ (new opcode **D0**) |
| `MIDI_FORCE_ALL_RESET` | `… 0F 0F D1 00 00 00 00 F7` | ❌ (new opcode **D1**) |
| `MIDI_START_SIMULATOR_MODE` | `… 0F 0F CF F7` | ⚠️ same byte the rebuild calls USB-MIDI stream start |
| `MIDI_Start_MIDI_THRU_MODE` | `… 0F 0F CB F7` | ❌ **CB never seen by the rebuild** |
| Fractal (Axe-Fx) | mfr `00 01 74`; preset-name (fn 0D), scene-name (0E), scene-trigger (0C), Axe-III effect-states (fn 13), Axe-II states (0E) — model byte + checksum computed | ❌ |
| Kemper | mfr `00 20 33 02 7F 7E 00 40`; "device found" (`…40 00 3B`) and read-preset (`…40 02 3B`) | ❌ |

**Open question (needs a hardware capture, not more static work):** the July 2026 capture of the
original's *MIDI Pass Thru utility* saw `CF`, yet the binary labels `CF` as Simulator Mode and `CB`
as MIDI-Thru start. Either Pass-Thru and Simulator share `CF`, or `CB` is the real thru opcode and
`CF` is what the rebuild has been using for "Simulator". Menu handlers dispatch through Xojo
vtables, so static caller tracing could not resolve it. Do **not** send `CB`/`D0`/`D1` to a unit
without a backup; D0/D1 are destructive.

### 5b. New windows/options found in symbols
- **`WindowExportData`** — selective export with checkboxes: Preset IA-states, Preset labels,
  Programming, Set-list songs, Settings, Song presets, plus record-range text fields. The rebuild
  only has whole-type CSV export. (Easy host-side win.)
- **`WindowExtSyncParams`** methods: `AXE_SYNC`, `AXE_SYNC_QuickProgram`, `KEMPER_SYNC`,
  `LoadExternalData_AXE/KEMPER`, `LoadCurrentNames_*`, `AXE_XY_EFF_NUM_ASSIGNMENTS`.
- Data model hints: `LF_Config.AllowExtSyncPreset / …IAState / …Save`, `LF_Preset.ExtSyncDeviceType /
  ExtSyncPresetValue`.

### 5c. Firmware (REA entropy + local decode)
REA entropy on the decoded 12+ v6.32 image: 6.51 bits overall, flat 6.0–6.5 per 4 KB block, no
low-entropy "code vs. data" regions — scrambled/encoded but **not** compressed or strongly
encrypted. Cracking the scrambler is the blocker; it needs a disassembler on a plausible
plaintext, i.e. REA with **Ghidra 12.1.4** (download not yet approved).

### 5d. "Update Internal Data" — protocol and payload (decompiled)
`Window1.Set_All_Firmware_Data_effects(MemoryBlock)` (called from the Hardware menu handler with
`Firmware_Effect_Labels.RawData`):

1. Compute a **16-bit sum of every payload byte**.
2. Send `F0 00 00 <id> 0F 0F 72 0A F7`; wait 0.1 s.
3. Stream the payload (progress dialog; Esc / ⌘. cancels).
4. Wait up to 6 s; read **2 bytes, big-endian**, from the unit and compare to the sum.
   Mismatch -> error dialog.

Payload = `RawData`, built at runtime: **5 devices x 200 slots x [16-char name + 8-char nick]**
= 24,000 bytes (names padded to width). Still unknown without a capture: whether the payload goes
on the wire raw or nibble-encoded, the padding byte, and what devices 0/1 hold. (The existing Get
side is opcode `0F 0F 0E`.)

### 5e. Recovered effect tables (now in `lfeditor/model/sync_effects.py`)
| Device | Table | Source routine |
|---|---|---|
| 2 AXE-FX III | 175 effects (full + nick), e.g. 21 = AMP 1, 165-172 = SCENE 1-8, 173 TAP TEMPO, 174 TUNER | `Load_AXEFX3_Data` |
| 3 AXE-FX Ultra/II | 85 (list used by the IA-slot picker; index 84 = SCENE 8) | `Create_AXE_ARRAYS` (the DB variant `Load_AXEFX_Data` has 84, labels differ) |
| 4 KEMPER | 17 stomp/rig/tap/tuner slots (0-16) + an 87-entry sparse **effect-type** DB (ids 0-199) | `Create_KEMPER_ARRAYS`, `Load_Kemper_Data` |

**Bug found in the rebuild:** `iaswitch.SYNC_EFFECTS` is a single **Kemper-only** list of 16 used
for every sync device, and it was missing **16 = Tuner**. Validated against the shipped factory
templates: every Axe-Fx III slot's stored index resolves to its own name (e.g. SCENE 1 -> 165);
Kemper indices match, with TUNER = 16. `SYNC_EFFECTS` now has 16 = "Tuner", and
`sync_effects.SYNC_EFFECTS_BY_DEVICE` / `sync_effect_name()` hold the per-device tables
(`tests/test_sync_effects.py`). **Wired up (2026-11-09):** the IA-Slot "Sync effect" dropdown is now a
`DependentEnumField` that follows "Sync device" on desktop (`EnumField.add_listener`) and web
(`options_by` in the schema + an `lf-set` event from `App.set`). Changing the device never rewrites
the effect byte; a stored value missing from the current list shows as `(unknown: N)`. Verified in
the desktop widget tests and in a real browser against the Axe-Fx III factory template.

### 5f. Windows build (v6.31 x64, unpacked with `innoextract`)
`SetupLF+Editor_64bit v6_31.exe` is Inno Setup 5.5.7; `LF+Editor.exe` is a PE32+ Xojo app.
- **Feature set is identical to the Mac build.** Diffing window classes, the whole menu-caption block
  and ~1,200 user-visible captions (after stripping Xojo property suffixes) leaves only platform
  plumbing. The one user-visible difference: the Mac build exposes virtual CoreMIDI ports
  (`LF+ IN PORT` / `LF+ OUT PORT`); Windows uses WinUSB (`WinUSBDeviceMBS`) instead. The rebuild's
  USB-MIDI Bridge already covers that role.
- **FTDI IDs:** FAMC's driver INF lists VID `0x0403` with PIDs `6001`, `6015` and the custom
  **`87C0`–`87C6`**. The rebuild matches FTDI by vendor ID, so these are already covered.
- The install bundles 8 firmware zips (v4.73 … v6.31 → 41 images): **all 41 are already in the loader's
  241-image SHA-256 allowlist** — nothing new.

### 5g. Firmware image format — decoded
The "scrambled" `.syx` payload is **PIC18 machine code, nibble-XOR 0x5**. 332/332 images (v3.34 → v6.32)
satisfy: 13-byte header (model letter + version), `blocks × 128` = length, trailer = 16-bit nibble
sum; decode → encode is byte-exact. Full layout in [FIRMWARE_NOTES.md](FIRMWARE_NOTES.md#decoded-format-lffirmwarecodecpy);
code in `lffirmware/codec.py` (+ `tests/test_firmware_codec.py`). Consequences:
- The loader now verifies each image's own header, length and checksum (refusing corrupt/truncated
  files even with the unverified override) and takes the **model from the header**, not the filename.
- `--decode` + Ghidra's PIC-18 language gives a real disassembly path for the firmware (vectors,
  ~335 LCD strings). There is **no signature** — only a 16-bit sum — so a modified image can be made
  well-formed (`codec.encode`); whether the *boot loader* accepts it is untested. Don't flash custom
  images except on a sacrificial/bricked unit, and note FAMC's firmware is copyrighted.

### 5h. Firmware menu text vs. editor coverage
The v6.32 12+ image's 335 LCD strings (the unit's settings/menu table, `0x1E083…`) were compared with
every label/tooltip the editor ships: only ten had no keyword counterpart, and checking those against
the original editor shows **no firmware setting the editor is missing**:
- `System SnapShot Store/Restore`, `Page LOCK/UNLOCK` are programming-*command functions* (already
  in the rebuild's 0-67 function table).
- `MAIN LCD Contrast` / `BTN LCD Contrast`, `FULL MIDI DUMP` (send everything out MIDI DIN),
  `Call Support`, `Firmware Waiting/Failed` are **device-menu-only** — absent from the original
  editor and from the Config record too.
- The firmware also names sibling products: `Liquid Router`, `Liquid Tracks`, `Hub Device`,
  `Expander Mode`, `Editor Mode+` (a "Liquid Tracks" product is not in this project).

### 5i. Frame builders added (no UI, never sent)
`lfeditor/comms/protocol.py` now builds the recovered frames: `reset_config_frame` (D0),
`reset_factory_frame` (D1), `thru_mode_start_frame` (CB), `simulator_start_frame` (CF),
`internal_data_update_frame` (`72 0A`) + `internal_data_checksum` / `internal_data_ack_ok`, and
`bulk_set_cmd` (**every bulk-write opcode = its read opcode + 0x64**, e.g. Presets 05→69).
Tests pin the exact bytes and assert no app module references the destructive builders
(`tests/test_protocol_original_frames.py`). These are **static-analysis results, not
hardware-confirmed**; enabling any of them still needs a capture of the original editor on a unit.
