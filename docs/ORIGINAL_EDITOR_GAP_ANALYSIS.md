# Original LF+ Editor v6.31 (Mac/Windows) — gap analysis & firmware leads

Date: 2026-11-09. Method: static analysis of the shipped v6.31 **Mac** binary (x86_64 Xojo, 30 MB,
**unstripped**) and **Windows** installer (Inno Setup, unpacked with `innoextract`), the firmware images
(v3.34 → v6.32) and the bundled resources — compared with the rebuild's menus, windows, data model and
protocol. Tools: `strings`/`nm`/`llvm-objdump`, REA ([morluto/rea](https://github.com/morluto/rea)) with
Ghidra, and Ghidra's PIC-18 module. **Nothing here was run against a real unit.**

## Outcomes (what changed in the repo because of this audit)

| Result | Where |
|---|---|
| IA-Slot **Sync effect** list was Kemper-only for every device and lacked *Tuner* — fixed: per-device tables recovered from the original (Axe-Fx III 175 · Axe-Fx II 85 · Kemper 17 + 87 effect types), validated against the factory templates; the dropdown now follows *Sync device* on desktop and web | `lfeditor/model/sync_effects.py`, `DependentEnumField`, `web/render.js`, `tests/test_sync_effects.py` |
| **Firmware image format decoded** — PIC18 code, nibble-XOR 0x5, header (model letter + version + length), 16-bit nibble-sum trailer; byte-exact round trip on 332/332 images | `lffirmware/codec.py`, `tests/test_firmware_codec.py`, [FIRMWARE_NOTES.md](FIRMWARE_NOTES.md) |
| **Firmware loader hardened** — refuses images whose own header/length/checksum don't agree (even with the override); model read from the header, not the filename; `--decode` exports PIC18 memory | `lffirmware/images.py`, `cli.py`, [FIRMWARE_LOADER.md](FIRMWARE_LOADER.md) |
| **Every sysex frame the original builds** recovered (reset D0/D1, thru CB, simulator CF, Update-Internal-Data `72 0A`, bulk write = read + 0x64, Fractal/Kemper requests); pure builders added, **never sent by the app** | `scripts/extract_original_frames.py`, `lfeditor/comms/protocol.py`, `tests/test_protocol_original_frames.py`, [LF_PROTOCOL.md](LF_PROTOCOL.md) |
| Mac vs Windows compared (feature-identical); FTDI IDs and bundled firmware checked | §5f |
| Open items and the hardware captures that would unlock them | §4, [HARDWARE_RE_CAPTURE.md](HARDWARE_RE_CAPTURE.md) |

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

> **Verified live (2026-11-09):** this tree was recovered statically from the binary and then confirmed
> against the *running* v6.31 Mac editor through the macOS accessibility menu API (top-level menus and
> every item of File, Edit, Utilities, Hardware, Reports, Complete Transfers and Settings match).
> Findings from the live check: **File → "Filter / Export Data"** is the selective export window
> (`WindowExportData`); the original's **Complete Transfers** has only *Get ALL* / *Send ALL* — our
> *Send Edits* is an addition; the original's Hardware menu has no Connect/Get/Send items (those live in
> Complete Transfers and the window's CONNECT control). The window's own controls are **not**
> accessibility-visible (3 of 105 AX nodes), so REA's `observe-native-ui` / `capture-native-ui-scenario`
> can only add a screenshot, and they additionally need macOS Screen Recording granted to the REA host.

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
| Utilities | **Simulator Mode** (`MIDI_START_SIMULATOR_MODE`, Start/Stop/Clip/Clear All/Exit) | ❌ absent (frame `CF` known; the `CB`/`CF` question needs a capture) |
| Utilities | Quick Repeated Command Programmer | ✅ |
| Utilities | MIDI Device I/O Utility · MIDI Pass Thru Utility | ✅ (MIDI Monitor / Pass-Thru, USB bridge) |
| Hardware | Review/Install Latest Firmware · Load Firmware From File · Special Firmware Load (Forced) | ⛔ disabled in the editor; standalone `lffirmware` beta tool (now structurally verifying images) |
| Hardware | **Special – Update Internal Data** (`HardwareFirmwareDataUpdate`) | ⚠️ protocol + tables recovered, frame/checksum builders exist; send path **not enabled** (needs a capture — §5d) |
| Hardware | Reset Config in LF+ (`MIDI_FORCE_CONFIG_RESET`) · Reset to Factory (`MIDI_FORCE_ALL_RESET`) | ⛔ disabled (gated); opcodes D0/D1 known, builders exist, unverified and destructive |
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
   The on-disk format is still unrecovered (look for `*.def`/XML via the `XML.dylib` usage, or capture a saved file from the original).
3. **Simulator Mode** — host turns the unit into a button/expression simulator
   (`MIDI_START_SIMULATOR_MODE`). Useful for debugging a programmed rig without stepping on the
   unit. Capture with the existing `scripts/lf_interpose.c` + `capture_original.sh`.
4. **Undo/redo + Show Stats on open** — pure host-side, no hardware needed.
5. **Update Internal Data** — pushes the effect/label database to v6 units. The payload is **not** a
   resource file: the editor builds it at runtime from tables compiled into the binary (now recovered,
   §5d/§5e). What is missing is the wire encoding of those 24,000 bytes — capture-then-replay.
6. **Reset Config / Factory reset** — opcodes named in the binary; implement only behind the
   existing gated-write rules.

## 3. Firmware (v6.32 is the last release)

The firmware `.syx` format is fully decoded (§5g, [FIRMWARE_NOTES.md](FIRMWARE_NOTES.md), `lffirmware/codec.py`):
a 13-byte header (block count, major/minor version, **model letter** F/J/K/L/H), a PIC18 program image
sent as nibbles XORed with 0x5 (16-bit words, high byte first), and a trailer that is the 16-bit sum of
the payload nibbles. 332/332 images across v3.34 → v6.32 verify and re-encode byte-for-byte. Decoded
images start with PIC18 reset/interrupt `GOTO`s; the boot-loader region (above the image) is not in the
file. Ghidra's `PIC-18:LE:24:PIC-18` language loads them and finds ~335 LCD strings (the unit's menu text).

What this means for "new firmware features / debugging the controller":

- **Comparison done:** the firmware's menu text has no setting the editor lacks (§5h). New *features*
  would therefore have to come from new firmware code, not from exposing existing settings.
- **Patching is technically possible, not recommended yet.** There is no signature or encryption —
  only a 16-bit sum, and `codec.encode` can package a modified image. Whether the *boot loader*
  accepts such an image is untested, a bad image bricks the unit, the loader's own beta ladder is still
  unvalidated, and FAMC's firmware is copyrighted. Do not flash custom images except on a
  sacrificial/bricked unit.
- **Debugging tools available now (no firmware surgery):** `--decode` + Ghidra for reading the firmware;
  per-version diffing of the 332 images; the live USB-MIDI/Pass-Thru bridge and MIDI monitor; and, once
  captured, Simulator Mode and a record-level "device diff" (read device → compare to the open file).
- **Left for a human with a unit:** a bricked-unit volunteer to validate the loader path, and the
  captures in [HARDWARE_RE_CAPTURE.md](HARDWARE_RE_CAPTURE.md).

## 4. Status and next steps (updated 2026-11-09)

Done: REA/Ghidra analysis of the Mac binary, Windows build compared, sysex frame table, per-device
sync-effect tables (+ the Sync-effect dropdown fix), firmware format decoded, loader hardened, frame
builders added. Remaining, in value order:

1. **Hardware captures** ([HARDWARE_RE_CAPTURE.md](HARDWARE_RE_CAPTURE.md)): Simulator, `CB` vs `CF`,
   Update Internal Data, Axe-Fx/Kemper sync exchange. Nothing destructive is enabled without them.
2. **External Device Sync (Axe-Fx / Kemper import)** — option strings, modes and the external-device
   request frames are known (§5j). `WindowExtSyncParams.AXE_SYNC` / `KEMPER_SYNC` / `LoadExternalData_*`
   decompile to empty stubs; the logic sits in the window's button handlers and `AXE_SYNC_QuickProgram`.
   Needs an Axe-Fx or Kemper on the bench to build and test.
3. **External Device Definitions** file format; selective **Export Data** dialog; **Undo/Redo**; open-file
   stats; release-notes window — host-side, no hardware.
4. **Custom firmware** — technically possible (no signature, 16-bit sum only) but brick-risk and
   untested; see §5g. Not recommended before a bricked-unit volunteer validates the loader path.

**Windows menu overpaint (tester report, 2026-11-09).** On Windows the *Complete Transfers* popup was
overpainted by the Copy/Paste/Find toolbar buttons (the other menus were fine; not reproducible on
macOS). Likely cause: Qt >= 6.7's default "windows11" style draws translucent layered popups. Fix:
force Fusion on `win32` only (`lfeditor/ui/theme.py: apply_style`). **Unverified on Windows** — the
tester's build also predates the Send Edits restore, so confirm on a fresh build from `main`.

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

### 5c. Firmware entropy (REA)
REA's `inspect-byte-entropy` on the nibble-decoded 12+ v6.32 image: 6.51 bits overall, flat 6.0–6.5 per
4 KB block. That ruled out compression/strong encryption and was consistent with the XOR-5 + PIC18
result in §5g (the 55/AA "runs" are just `00`/`FF` flash filler after XOR). REA's `inspect-firmware-regions`
needs Linux + binwalk and was not usable here.

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

### 5j. External-device sync — request frames recovered (decompiled)
Sent over the LF+ serial link (`SerialPortLF`) by `Window1.AXE_*` / `KEMPER_*`; the LF+ editor drives
the external unit through the LF+ in "Editor Mode". Bytes are literal except where noted.

| Routine | Frame | Notes |
|---|---|---|
| `AXE_READ_EFFECTS_STATES_AXE3` | `F0 00 01 74 10 13 06 F7` | Fractal mfr `00 01 74`, model `10` = Axe-Fx III, fn `13`; the trailing `06` is the **Fractal checksum = XOR of all bytes before it, & 0x7F** (verified by hand). fn `13` matches the public III "status dump" request |
| `AXE_DEVICE_msg_SceneName` | `F0 00 01 74 <model> 0E <…computed…> F7` | fn `0E`; model byte and scene arguments/checksum are filled in at runtime |
| `AXE_DEVICE_msg_PresetName` / `_SceneTrigger` | fn `0D` / `0C` with the same envelope | from the frame table in §5a |
| `KEMPER_DEVICE_READ_PRESET` | `F0 00 20 33 02 7F 7E 00 40 02 3B 7F F7` | Kemper mfr `00 20 33`, product `02` (KPA), device `7F` (any), fn `7E`; remaining bytes are the address/request fields, taken as literal |
| `KEMPER_DEVICE_FOUND` | same envelope, `…40 00 3B 7F` and `…40 02 3B 7F` | two probes sent back-to-back to detect a KPA |

Caveats: model byte / scene number / checksum are computed, not literals (except the III status
dump, which is fully literal and checksum-verified). The external unit's *replies* and the full
import state machine are not recovered statically — capture them with the original editor and an
Axe-Fx III / Kemper (see [HARDWARE_RE_CAPTURE.md](HARDWARE_RE_CAPTURE.md)).
