# FAMC Liquid Foot+ Editor — Native Rewrite

A native, cross-platform rewrite of FAMC's official **LF+ Editor** (v6.31, 2020) for the
**Liquid Foot+** MIDI foot-controller family (12+, 12, Mini, JR). FAMC, LLC went out of
business; the original editor is a compiled **Xojo** macOS/Windows app that will eventually
stop running on modern systems. This project rebuilds it as a maintainable
**Python + PySide6 (Qt)** desktop app.

**New here? → [Getting started](docs/GETTING_STARTED.md)** — launch the desktop app or the web
editor and connect your LF+ in minutes.

[![Buy Me a Coffee](https://img.shields.io/badge/☕-Buy%20me%20a%20coffee-ffdd00)](https://buymeacoffee.com/sungle.spec)

> **Companion project:** a sibling editor for the FAMC **Liquid Router A-16**
> ([famc-liquid-router-usb-editor](https://github.com/sungle-spec/famc-liquid-router-usb-editor))
> first cracked the FAMC USB-serial protocol; this project reuses that comms work for the
> Liquid Foot+.
>
> **Companion project:** [famc-liquid-foot-legacy-editor](https://github.com/sungle-spec/famc-liquid-foot-legacy-editor)
> is the sibling editor for the older, pre-USB **Liquid Foot Pro and Junior** line
> (2009–2013, MIDI/DIN only). Its sysex protocol turned out to be the direct ancestor of this
> project's wire format, and it reuses this project's codec architecture, MIDI transport, and
> UI theme.

## Status

Feature-complete for offline editing and host-side workflow; **297 tests pass**. The remaining work
is device-side (gated resets) and firmware flashing. See `docs/` for the reverse-engineering
write-up.

| Phase | State |
|---|---|
| P0 — Repo & tooling | ✅ done |
| P1 — Protocol RE (decompile JAR, decode sysex dumps) | ✅ wire format cracked, byte-exact round-trip |
| P2 — UI capture of all 11 tabs | ✅ [docs/LF_UI_MAP.md](docs/LF_UI_MAP.md) + tab captures in [docs/ui/](docs/ui/) |
| P3 — Codec + model + round-trip tests | ✅ byte-exact round-trip on 118 real backups (fw v3.x–v6.x, all variants); 297 tests total |
| P4 — App shell + Presets tab | ✅ runnable (`python -m lfeditor`) |
| P5 — Remaining tabs | ✅ all 11 tabs; **data model complete** — every user-facing control mapped (extension records, command tables, full Config: LCD/Extender/Tap-Tempo/Combo, exp-pedals, colours) |
| P6 — Device comms (USB-serial + MIDI) | ✅ **record read/write + bidirectional live USB MIDI confirmed on real hardware**; see [docs/LF_USB_DIRECT.md](docs/LF_USB_DIRECT.md) |
| P7 — Packaging & docs | ✅ Standalone builds for **Windows / Linux / macOS** via a CI matrix (`.exe` zip · AppImage · `.app`); USER_GUIDE + [docs/BUILD.md](docs/BUILD.md) |
| P8 — Faithful UI rebuild | ✅ all 11 tabs rebuilt to the original v6.31 layout — dark FAMC theme, per-record transfer header, titled section panels, vertical rocker toggles, green LCD fields; **Midi/Groups** (two-col channel grid), **Pages** (graphical pedalboard + page-group navigator), **Global** (5-column, every mapped Config field surfaced), **IA-Maps** (6×10 name pickers), **Set-List** (5×12), **Colors** (4-col), and extension-record label panels on **Presets**/**Songs**, **Songs MTC** (enable + Hr/Min/Sec/Frame), and **Pages** button-function labels decoded to names. Build spec captured in [docs/ui/ORIGINAL_LAYOUT.md](docs/ui/ORIGINAL_LAYOUT.md). All 11 tabs match the original v6.31 layout |
| P9 — Host-side workflow parity | ✅ icon toolbar; whole-record **copy/paste/clear**; **CSV import/export** + **Reports** (format captured byte-for-byte from the original); **Find** search (name + MIDI-command queries); a left-side **Q-LIST** navigator dock that follows the current tab, with **drag-drop** onto slot pickers / command rows; **right-click multi-record** toggle edits; **MIDI Monitor / Pass-Thru**; **Quick Repeated Command Programmer**; **Re-order with Save/Sync** reference rewrite; **About / License** dialog; **EEPROM wizard**. See [docs/FIRMWARE_NOTES.md](docs/FIRMWARE_NOTES.md) for the original-vs-rebuild feature audit |
| P9b — Fidelity fixes (vs the live editor) | ✅ full **command-function table** RE'd (0–67, all 68 functions; fixed two mis-coded entries); **IA-Slot command** off-by-one corrected (was reading the MIDI status byte as the function); spin-box arrows, command-table columns, Pages-panel alignment |
| P10 — Device-side resets + firmware flash | ⛔ deferred (gated Phase 2 writes; Phase 3 flashing is brick-risk) |

**Working today:** open any LF+ `.syx` backup and edit, all **losslessly** (re-encodes
byte-for-byte; only changed records change):
- **Presets:** IA-state grid, default page, IA-slot map, 13 flags, step names, IA-Slot Defined
  Labels (Ext9), and the **Command Programming table** with the original's columns
  (`Function · MIDI device-name · Cmd · CC#/PC# · Data`; the MIDI column resolves the channel to
  its device name).
- **IA-Slot:** switch type, sync device/effect, group, colours, On + BYPASS command tables (the
  same 4-byte `[func,b1,b2,b3]` format as presets, side by side), step toggles.
- **IA-Maps:** 60-cell button→slot map (name pickers, 6×10). **Pages:** graphical footswitch
  pedalboard + page-group navigator; each button's Function-1/2 is a **Type + Value dropdown**
  (Empty / Preset / Function / IA Slot / Page Select, items listed by name); page parameters.
- **Songs:** name/nick + trigger + 24 preset slots (**name pickers**) + LCD Button Labels (Ext11)
  + **MTC** (enable + Hr/Min/Sec/Frame). **Set-Lists:** Last-Song-Slot (ALL/1–60) + end-cycle +
  60 song slots (5×12 name pickers).
  **Midi/Groups:** Exclusive Groups · Grouped-IA config · the 16-channel device grid (two columns
  of 8, rocker switches, Max Pre).
- **Colors:** all function- and preset-button colour assignments (4-column grid). **Sysex Msgs:**
  16 data cells with HEX/DEC read-outs, Pre/Post links, and an Auto-Create MMC generator.
- **Global:** power-up, guitar-tuner, tap-tempo, Sysex ID, MIDI channel, Physical-Btn start,
  2nd-func hold time, scroll delay, external-device override, preset-button colours, Exclusive
  Groups, the full per-channel MIDI device config (BANK +1 / send / msb grids + 16-bit Max Pre),
  Grouped-IA processing order, and behaviour toggles.
  **Exp Pedals:** per-pedal type, CC#, MIDI channel, auto-calibrate, block-reset, force-zipper,
  CC-sweep min/max, toe/heel trigger, sensitivity, Blk-Heel/Toe and Hi-Res flags — all 4 pedals
  (the per-pedal flag bits and calibration block were reverse-engineered on real hardware), plus a
  **Live Calibrate…** view (when connected) with live treadle bars that captures the swept min/max
  and writes the calibration back to the device. The save mirrors the original editor's exact
  protocol — captured on hardware: written *during* the live stream (a `0xFF` prelude, then both
  Config records, then the device's `F0 09 F7` ACK), not by stopping the stream first.

**Workflow tools (mirroring the original editor):**
- **Toolbar icons** — Open / Save / Backup, plus **Clear / Copy / Paste** of a whole record
  (copy carries the linked label records; paste is same-type only).
- **CSV Import/Export** (Presets / Songs / Set-Lists / Sysex) and **Reports** — column format
  captured byte-for-byte from the original (`tests/fixtures/golden_csv/`).
- **Find** (`Cmd/Ctrl+F`) — search by name (wildcards) or MIDI command (channel / type / CC#-PC#);
  double-click a result to jump; export the hit list; drag a result onto a slot picker / command row.
- **Q-LIST** — the left-side record navigator (replaces the per-tab lists). It follows the current
  tab (empty on tabs without records); single-click an item to jump, click a type button to switch
  tabs, or drag an item onto a slot picker / command row.
- **Right-click a toggle** → apply it across all records of that type, or a number range.
- **Utilities** — **Quick Repeated Command Programmer** (fill a command row across a record range,
  PC# auto-increment), **Re-order Records (Save/Sync)** (move a preset/song; references follow), and
  **MIDI Monitor / Pass-Thru**.
- **Hardware → Device Connection Setup** — the FTDI-EEPROM wizard that exposes the device's serial
  port on macOS (one-time; see [Getting started §4](docs/GETTING_STARTED.md#4-connect-your-lf-macos-one-time-setup)
  and the [illustrated walkthrough](docs/DESKTOP_GUIDE.md#first-time-setup-make-the-device-appear-as-a-serial-port)).
- **Hardware → USB MIDI Bridge** — starts the hardware-confirmed `C9 → CA → CF` live mode and
  exposes **LF+ IN PORT / LF+ OUT PORT** as a bidirectional virtual MIDI device on macOS/Linux. It preserves the
  proven DAW→LF+ CC/PC filter and republishes parsed LF+ channel MIDI to the computer; Windows
  uses two user-selected loopback endpoints because python-rtmidi cannot create native virtual
  ports there.
- **Firmware / bricked units** — a standalone **[LF+ Firmware Loader (beta)](docs/FIRMWARE_LOADER.md)**
  targets recovery of units bricked by failed firmware updates (community-tested; the editor's own
  *Load Firmware* stays disabled until it graduates).
- **Hover help** — every control shows the **original LF+ Editor's exact tooltip** on hover
  (recovered verbatim from the app and mapped to our controls): 131 field + 3 section tooltips
  across 10 tabs, scoped per tab, the Global/IA-Slot maps confirmed by a live hover pass against the
  original. Controls the original leaves without a tooltip stay blank, matching it.
  Built reproducibly by `scripts/extract_tooltips.py` (→ [docs/LF_TOOLTIPS.md](docs/LF_TOOLTIPS.md))
  + `scripts/gen_help_text.py` (the curated label→tooltip map → `lfeditor/ui/help_text.py`).

The live editor's numeric steppers reject synthetic input, so those Global fields were pinned by
static analysis (Sysex ID / MIDI channel) and a user-assisted single-variable diff (Physical-Btn
/ 2nd-func hold / scroll delay). The "Save Sync" / "Force changes" buttons are *actions* that
don't persist to a stored byte. Everything stays editable via the Raw-decoded-values table — see
[docs/LF_DATA_MODEL.md](docs/LF_DATA_MODEL.md).

**Device comms** (`lfeditor/comms/`): the USB-serial protocol is **confirmed on real hardware**
(2026-06-15) and **wired into the toolbar** — **Connect** handshakes into Editor Mode
(`F0 00 00 7C 0F 0F C9 …` then the `CA` session control), **From LF+** pulls the device's records
and overlays them onto the open backup, and **To LF+** writes the selected record back (the device
ACKs each write with `F0 09 F7`). The full read pulled all 384 presets + ext/song/sysex/config/
iamap records and they decode **byte-exact** against the on-disk backup (only live runtime counters
differ); writes are proven (preset write→read→restore, end-to-end through `send_record`). Writes
**stay disabled unless `allow_write=True` is passed explicitly**, and the UI confirms before each
one. See [docs/LF_USB_DIRECT.md](docs/LF_USB_DIRECT.md). Raw Song/Setlist/Page/IASwitch records
aren't exposed over this USB path (edit them offline); MIDI transport is built but the device
presents as USB-serial here.

The same USB-serial connection also has a distinct **live bidirectional MIDI mode**. The bridge
validates the normal `C9` identification reply, sends `CA` then `CF`, and pumps both directions
without sharing the port with Editor Mode record transfers. `CC` stops streaming before close.
Computer→LF+ forwards the proven CC/PC route plus MIDI Clock/Start/Continue/Stop for hardware
validation; Active Sensing, System Reset, and all computer SysEx remain blocked. LF+→computer
also forwards safe realtime and unambiguous 7-bit musical SysEx, while known FAMC frame shapes,
malformed SysEx, and System Reset remain filtered.

Deeper per-field offsets are mapped one at a time via `scripts/diff_dumps.py` (diff two
live-editor exports). See [docs/LF_DATA_MODEL.md](docs/LF_DATA_MODEL.md).

## How the reverse engineering works

Four independent sources cross-check each other:

1. **`Liquid-Foot.jar`** (2013) — an earlier *Java* version of the editor, fully decompilable.
   Its `liquidfoot` package exposes the data model (`Preset`, `Song`, `Setlist`, `IASwitch`,
   `GlobalConfig`) and the sysex protocol (`SysexMSG`, `SysexMsgTable`, `MidiFootController`).
2. **The live `LF+ Editor.app` v6.31** — driven via GUI automation to capture every screen and
   widget for faithful UI replication.
3. **Three full device sysex dumps** (`reference/sysex_dumps/`) — `F0 00 00 7C …`
   (FAMC manufacturer ID) — the on-wire ground truth and our round-trip test fixtures.
4. **Binary strings, `config.dat`, the manual PDF, and the firmware archive** — fill the gaps.

## Stack

- **Python 3.11+ / PySide6 (Qt)** — native desktop GUI, cross-platform.
- **pyserial / pyftdi** — USB-serial transport (FTDI VCP), ported from the Router project.
- **mido / python-rtmidi** — DIN / USB-MIDI sysex transport.
- **pytest** — codec round-trip tests.
- **PyInstaller** — standalone packaging, built per-OS by a GitHub Actions matrix → Windows `.zip`,
  Linux `.AppImage`, macOS `.app` (spec + workflow live in the
  [builds repo](https://github.com/sungle-spec/famc-liquid-foot-editor-builds)).

## Layout

| Path | What |
|---|---|
| `lfeditor/codec/` | sysex `bytes ↔ model` codec (pure, heavily tested) |
| `lfeditor/text.py` | shared fixed-width ASCII codec (`decode_ascii` / `encode_ascii`) for every name/label field |
| `lfeditor/model/` | dataclasses mirroring device structures |
| `lfeditor/comms/` | device I/O — USB-serial + MIDI transports |
| `lfeditor/ui/` | PySide6 app shell + one module per tab |
| `lfeditor/ui/help_text.py` | curated per-tab hover tooltips (the original editor's, generated by `scripts/gen_help_text.py`) |
| `lfeditor/ui/dnd.py` | record drag-and-drop glue: MIME codec + `RecordDropTarget` mixin (Find/Q-LIST → slot/command) |
| `lfeditor/csvio.py` | CSV import/export + reports (format matches the original editor) |
| `lfeditor/search.py` · `lfeditor/ui/qlist_dock.py` | Find search engine · Q-LIST navigator dock |
| `lfeditor/ui/midi_monitor.py` | MIDI monitor / pass-thru utility |
| `lfeditor/quickprog.py` · `lfeditor/reorder.py` | Quick Repeated Command Programmer · re-order with reference sync |
| `lffirmware/` | standalone **Firmware Loader (beta)** — bricked-unit recovery over MIDI ([docs](docs/FIRMWARE_LOADER.md)) |
| `docs/` | `LF_PROTOCOL.md`, `LF_DATA_MODEL.md`, `LF_UI_MAP.md`, `RE_NOTES.md`, `FIRMWARE_NOTES.md` |
| `reference/` *(not in this repo)* | the maintainer's local RE source material — device dumps, FAMC files; tests that need it skip cleanly |
| `tests/` | the full pytest suite — codec round-trips vs the factory files everywhere, plus reference-dump tests that run on the maintainer's checkout |
| `.github/workflows/tests.yml` | CI: the full pytest suite head-less on Windows/Linux/macOS |
| [`famc-liquid-foot-editor-builds`](https://github.com/sungle-spec/famc-liquid-foot-editor-builds) | **sibling repo**: PyInstaller spec, icons, AppImage tooling, the 3-OS build/release workflow, and the downloadable Releases |

## Run (dev)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m lfeditor          # launches the editor (offline; load a .syx)
pytest tests/
```

## Download / install (standalone builds)

Pre-built, no-Python-needed bundles are produced for **Windows, Linux and macOS** and published
as Releases on the **[builds repo](https://github.com/sungle-spec/famc-liquid-foot-editor-builds/releases)**
(this repo is the source; packaging + distribution live there):

| OS | Download | First-launch note |
|----|----------|-------------------|
| Windows | `…-windows-x64.zip` → run `LFPlusEditor.exe` | unsigned: SmartScreen → *More info → Run anyway*. Needs the FTDI VCP driver for USB-serial. |
| Linux | `…-x86_64.AppImage` → `chmod +x` and run | add yourself to `dialout` for serial: `sudo usermod -aG dialout $USER` |
| macOS | `…-macos-arm64.zip` → `LF+ Editor (native).app` | unsigned: right-click → **Open → Open** |

Every bundle is smoke-tested in CI on its own OS (`--selftest`) before it is packaged, and the
frozen app has been verified feature-for-feature against `python -m lfeditor` — see the
"Frozen (packaged) builds" section of [docs/UAT.md](docs/UAT.md). Between releases, freshly built
bundles for all three OSes can be produced on demand from the builds repo's workflow (any branch
or tag of this repo) and downloaded from that run's artifacts.

The builds are **unsigned** (no code-signing certificate yet), hence the first-launch warnings
above. Each release also ships a `SHA256SUMS.txt`; verify a download with all files in one folder:

```bash
sha256sum -c SHA256SUMS.txt      # macOS: shasum -a 256 -c SHA256SUMS.txt
```

Building it yourself (one OS at a time — PyInstaller can't cross-compile) is documented in
[docs/BUILD.md](docs/BUILD.md). The same pure-Python codebase targets all three OSes; no fork.

**User manual (screenshots + step-by-step scenarios, incl. the hardware workflows):
[docs/DESKTOP_GUIDE.md](docs/DESKTOP_GUIDE.md).**

## Web version (no install)

**→ Use it now: <https://sungle-spec.github.io/famc-liquid-foot-usb-editor/>**

There's also a **browser build** — a **pixel-for-pixel port of all 11 tabs** that runs entirely
client-side via [Pyodide](https://pyodide.org), reusing the *same* byte-exact codec and tools (no
second implementation). Open it, load a `.syx`, edit, download — offline, nothing to install. It has
the desktop's auxiliary tools too (Q-LIST/Find, copy/paste/clear, raw view, multi-apply, CSV,
reports, Quick Command Programmer, Re-order, drag-onto-slot). USB device I/O over WebSerial
(Chrome/Edge) is **verified on real hardware** — a browser pull is byte-identical to a desktop
pull, writes ACK and read back (and stay gated behind a confirm). Deployed to GitHub Pages by
[`.github/workflows/pages.yml`](.github/workflows/pages.yml).

**User manual (screenshots + step-by-step scenarios): [docs/WEB_GUIDE.md](docs/WEB_GUIDE.md).**
Technical details: [docs/WEB.md](docs/WEB.md), [docs/WEBSERIAL.md](docs/WEBSERIAL.md), desktop↔web
[docs/PARITY.md](docs/PARITY.md), and the [UAT plan + results](docs/UAT.md) run against both builds.

## Legal / safety

This is independent reverse-engineering work for **interoperability and preservation**, built so
owners of FAMC hardware (a long out-of-business company) can keep editing their devices on modern
OSes. **All code here is original and MIT-licensed** — the editor is a clean rebuild, not a port of
FAMC's code. FAMC firmware images, the original editor binaries, the manual, and captured device
dumps are **not redistributed** (git-ignored reference material).

Two small pieces of FAMC-origin *data* are included, solely so the editor is usable:

- the **factory-default backups** (`lfeditor/resources/factory/*.syx`) that *File → Load Factory
  Defaults* needs — the same files every hardware owner received with the original editor;
- the original editor's **hover-help text** (`lfeditor/ui/help_text.py`), preserved so owners keep
  the only documentation those settings ever had.

Both are included in good faith for preservation of discontinued, unsupported hardware. If you
hold rights to this material and want it removed, **open a GitHub issue** and it will be taken
down promptly. Writing to hardware is at your own risk; see `LICENSE`.

---

Free, open source, and it'll stay that way. If this saved your rig, [☕ buy me a coffee](https://buymeacoffee.com/sungle.spec) —
it funds testing on hardware I don't own and reverse-engineering the next piece of orphaned gear.
