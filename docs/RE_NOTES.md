# Reverse-Engineering Notes

## Sources

| Source | Location | Use |
|---|---|---|
| 2013 Java editor | `reference/jar_decompiled/liquidfoot/` (24 classes) | data model + sysex field math |
| v6.31 device dumps | `reference/sysex_dumps/{FAMC12plus_new,Mini,RJM}.syx` (626 KB) | on-wire ground truth, test fixtures |
| Factory `.syx` | `reference/factory_syx/` (12/JR/Mini/Pro/AxeFx/Kemper) | per-model defaults |
| Live editor | `/Applications/LF+ Editor.app` v6.31 (Xojo) | UI capture (P2), field oracle |
| Mac binary, static | same `LF+ Editor` Mach-O (x86_64, **unstripped, 21,981 symbols**) | menus, windows, sysex frames, effect tables — via `nm`/`llvm-objdump`/REA+Ghidra (below) |
| Windows install | `reference/Liquid Foot/LF+ Editor/SetupLF+Editor_64bit v6_31.exe` (Inno Setup 5.5.7 → `innoextract`) | Mac-vs-Windows feature diff, FTDI driver INF, bundled firmware |
| `config.dat` | `reference/config.dat` | every setting key + tooltip help text |
| Manual | `reference/Liquid Foot+ Series_410 - 2015.01.12.pdf` | feature/field reference |
| Firmware | `reference/Liquid Foot/Firmware/` (v3.34→v6.32 `.syx`) | version history |

## Tooling

- **Decompile the JAR** (needs a JDK — `brew install openjdk`, on PATH at
  `/opt/homebrew/opt/openjdk/bin`):
  ```bash
  java -jar /tmp/cfr.jar reference/Liquid\ Foot/Liquid-Foot-Java/Liquid-Foot.jar \
       --outputdir reference/jar_decompiled
  ```
  (CFR 0.152, the cleanest free decompiler for this code.)
- **Analyse a dump:** `python scripts/parse_dump.py <file.syx …>` — frame histogram by type +
  byte-exact round-trip check.

## Key findings (see LF_PROTOCOL.md for detail)

1. The Mac editor is **Xojo** (not Java) — `strings` shows `Xojo.Introspection`, MBS plugins; it
   speaks FTDI **`usbserial`**. We use the *Java* JAR for the model and the *live app* for the UI.
   *(Update 2026-11-09: the Mac binary is **not stripped** — Xojo method names are in the symbol
   table — so it **can** be analysed statically; see "Static analysis of the original editor".)*
2. Frame format `F0 00 00 <id> 00 <type> <sub> <num> <len> <nibble data> F7`. **Nibble-encoded**
   payload; **no checksum in v6** (the 2013 JAR had one).
3. 11 record types; counts identical across all three device dumps → the format is stable.
   Types 1–6 = 2013 model (grown); 7–11 = v6 additions.
4. Native transport is **MIDI sysex**; USB-serial is a v6 wrapper around the same bytes.
5. Device models share one format (12+/12/Mini/JR/Pro); model differences live in `GlobalConfig`
   and factory defaults, not the wire format.

## Open questions (tracked for P3/P5)

- Exact field map of v6 extension records (types 7–11) and Preset values 130–169.
- CMD→type mapping for "From LF+ / All From LF+" requests (`PartialDumpBox.java`, byte5 9–15).
- USB-serial handshake specifics for the Liquid Foot (reuse Router's; confirm on hardware later).

## Static analysis of the original editor (2026-11-09)

Findings are in [ORIGINAL_EDITOR_GAP_ANALYSIS.md](ORIGINAL_EDITOR_GAP_ANALYSIS.md). How to reproduce:

- **Symbols/strings (no extra tools):** `nm "<LF+ Editor binary>"`, `strings -a …`. Xojo method names
  look like `_Window1.Window1.MIDI_FORCE_ALL_RESET%%o<Window1.Window1>`.
- **Every sysex frame the editor builds:** `python3 -I scripts/extract_original_frames.py "<binary>"`
  (walks `llvm-objdump` output for the `callq *0x18(%reg)` array-set pattern; the device-ID byte is
  computed at runtime and prints stale — treat idx 3 as `<id>`).
- **Decompiling (REA + Ghidra):** `npx rea-agents@latest decompile <binary> 0x<addr> --snapshot s.snap`.
  Pitfalls hit: REA accepts **Ghidra 12.1.x only** (12.2 is rejected); the official Ghidra zip ships
  **no macOS decompiler** — build it from the bundled source (`make ghidra_opt ARCH_TYPE="-arch arm64"
  OSDIR=mac_arm_64` in `Ghidra/Features/Decompiler/src/decompile/cpp`, copy to `…/os/mac_arm_64/decompile`);
  first import of the 30 MB binary takes ~5 min, so set `REA_GHIDRA_STARTUP_TIMEOUT_MS` (default 330 s
  is too short). Xojo strings are `DAT_<addr>` objects: text pointer at +8, length at +0x18, first byte
  of the text is a length prefix. Menu handlers dispatch through vtables, so static caller tracing does
  not resolve who calls which `MIDI_*` routine — that needs a hardware capture.
- **Firmware:** PIC18 image; `python -m lffirmware --image X.syx --decode out.bin`, then Ghidra language
  `PIC-18:LE:24:PIC-18` (format in [FIRMWARE_NOTES.md](FIRMWARE_NOTES.md)).
- **Windows build:** `brew install innoextract`, `innoextract -d <empty dir> setup.exe`.
