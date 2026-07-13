# Reverse-Engineering Notes

## Sources

| Source | Location | Use |
|---|---|---|
| 2013 Java editor | `reference/jar_decompiled/liquidfoot/` (24 classes) | data model + sysex field math |
| v6.31 device dumps | `reference/sysex_dumps/{FAMC12plus_new,Mini,RJM}.syx` (626 KB) | on-wire ground truth, test fixtures |
| Factory `.syx` | `reference/factory_syx/` (12/JR/Mini/Pro/AxeFx/Kemper) | per-model defaults |
| Live editor | `/Applications/LF+ Editor.app` v6.31 (Xojo) | UI capture (P2), field oracle |
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
   speaks FTDI **`usbserial`**. Native binary, not directly decompilable → we use the *Java* JAR
   for the model and the *live app* for the UI.
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
