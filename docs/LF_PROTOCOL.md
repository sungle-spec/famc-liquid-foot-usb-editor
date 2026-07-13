# Liquid Foot+ Sysex Protocol

Reverse-engineered from three sources that agree: the decompiled 2013 `Liquid-Foot.jar`
(`reference/jar_decompiled/liquidfoot/`), three full v6.31 device dumps
(`reference/sysex_dumps/`), and the factory `.syx` shipped in the editor
(`reference/factory_syx/`). Verified by `scripts/parse_dump.py`, which segments every dump
into frames and **re-encodes them byte-for-byte** (round-trip: OK, 0 bad frames).

> **Transport.** The device's native link is **MIDI sysex** (DIN or USB-MIDI) — the 2013 Java
> editor used `javax.sound.midi` exclusively. The 2020 Xojo editor adds a **USB-serial** path
> (FTDI VCP, `usbserial`) that carries the *same* sysex bytes after a serial handshake — this is
> the path the sibling Router project cracked and that `lfeditor/comms/` will reuse. Either way,
> the payload below is identical.

## Frame format (v6.31 / 2020 firmware)

Every record is one MIDI System Exclusive message:

```
F0 00 00 <ID> 00 <TYPE> <SUB> <NUM…> <LEN…> <nibble-encoded data> F7
```

| Field | Bytes | Meaning |
|---|---|---|
| `F0` | 0 | sysex start |
| `00 00` | 1–2 | lead-in (FAMC uses `00 00 <ID>` as its manufacturer/device id prefix) |
| `<ID>` | 3 | device sysex id (dumps use `7C`; editor default `7F`/127). Not validated on read. |
| `00` | 4 | always 0 |
| `<TYPE>` | 5 | **record type** (see table) — the discriminator |
| `<SUB>` | 6 | `1` = data record, `2` = command/request message |
| `<NUM>` | 7–8 *or* 7–10 | record number, nibble-encoded (2 nibbles if type count ≤255, else 4) |
| `<LEN>` | 9–10 *or* 11–12 | value count, 2 nibbles, immediately before the data |
| data | … | each logical value → **two** bytes `(value>>4)&0xF, value&0xF` |
| `F7` | last | sysex end |

**Nibble encoding:** every payload byte is split into its high and low nibble, sent as two
bytes each 0x0–0xF. So a record of *N* values occupies `2N` sysex data bytes.

**No checksum in v6.** The 2013 JAR appended a 4-nibble checksum (sum of all data nibble-bytes)
before `F7`; the 2020 firmware **dropped it** — `frame_len == data_off + 2*LEN + 1`. Codecs must
not expect a trailing checksum. (`SysexMSG.SetToSysex` / `Preset.SetToSysex` in the JAR show the
old checksum; the dumps show it is gone.)

### Header layout depends on record count

Types whose record number can exceed 255 use a **4-nibble** `NUM` (bytes 7–10) with data starting
at byte **13**; all others use a **2-nibble** `NUM` (bytes 7–8) with data starting at byte **11**.

## Record types (byte 5)

Counts/sizes are identical across all three device dumps and the factory files (factory omits the
per-preset/song extension blocks 10–11 and sometimes 7–11).

| TYPE | Name | Count | NUM | data@ | values | frame len | Source |
|---:|---|---:|:--:|:--:|---:|---:|---|
| 1 | **Preset** | 384 | 4-nib | 13 | 170 | 354 | JAR `Preset` (was 130 vals in 2013) |
| 2 | **Song** | 254 | 2-nib | 11 | 125 | 262 | JAR `Song` |
| 3 | **IASwitch** | 180 | 2-nib | 11 | 250 | 512 | JAR `IASwitch` |
| 4 | **Config / Global** | 2 | 2-nib | 11 | 250 | 512 | JAR `Config` / `GlobalConfig` |
| 5 | **Setlist** | 128 | 2-nib | 11 | 90 | 192 | JAR `Setlist` |
| 6 | **SysexMSG** | 255 | 2-nib | 11 | 42 | 96 | JAR `SysexMSG` (was 34 vals in 2013) |
| 7 | **Pages** | 50 | 2-nib | 11 | 210 | 432 | v6 — confirmed by editor loader ("50 Pages") |
| 8 | **IA-Maps** | 60 | 2-nib | 11 | 100 | 212 | v6 — confirmed by editor loader ("60 IA Maps") |
| 9 | v6 per-preset ext | 384 | 4-nib | 13 | 80 | 174 | v6-only — per-preset extension |
| 10 | v6 per-preset ext | 384 | 4-nib | 13 | 160 | 334 | v6-only — per-preset extension 2 |
| 11 | v6 per-song ext | 254 | 2-nib | 11 | 96 | 204 | v6-only — per-song extension |

Types **1–6** carry the 2013 field semantics (grown by v6 — Preset 130→170 values, SysexMSG
34→42); types **7–11** are v6 additions and are field-mapped empirically (dumps + live editor +
`config.dat`). See `LF_DATA_MODEL.md`.

**Cross-check:** opening any dump in the real LF+ Editor v6.31 reports
`(384 Presets)(254 Songs)(128 Setlists)(50 Pages)(180 IA-Slots)(60 IA Maps)(255 Sysex msgs)
(Global Settings Found)` — every count matches the frame histogram above, which is how types 7
and 8 were positively identified as **Pages** and **IA-Maps** (types 9–11 are internal per-
preset/per-song extension blocks, not surfaced as separate items in the loader).

A full device dump is these records concatenated in type order (1,2,3,…,11), each numbered
`0..count-1`.

## Command / request messages

> **Superseded by hardware RE — see [LF_USB_DIRECT.md](LF_USB_DIRECT.md).** The 2013-JAR command
> frame below (`00 <CMD> 02 …`) is **not** what the modern device wants over USB-serial. The real
> Foot read/write protocol (confirmed 2026-06-15) is the Router-family framed-serial one:
> handshake `F0 00 00 7C 0F 0F C9 …` into Editor Mode, then get-commands `F0 00 00 7C 0F 0F <X> F7`
> that stream **decoded** records back, and writes that replay a record's `.syx` frame (silent,
> no ACK). The JAR frame is kept here only as historical context.

The 2013 Java editor sent a short command frame (from `MidiFootController.SendMsg`):

```
F0 00 00 <ID> 00 <CMD> 02 <param:4 nibbles> F7      (2013 MIDI path — historical)
```

`CMD` (byte 5) selected the operation; the device replied by streaming the matching `SUB=1`
records. Observed CMD codes: `9,10,11,12,13,14,15`. The live USB-serial command map is in
[LF_USB_DIRECT.md](LF_USB_DIRECT.md) (read `0x05/0D/0F/0A/0B/0C/10`).

**Preset selection** is plain MIDI, not sysex: Bank-Select `CC0 = (preset-1)/128` then
Program-Change `(preset-1)%128`, on the global MIDI channel.

## Verified Preset record (type 1) field map — 2013 base

Value indices into the decoded type-1 payload (each "value" = one decoded byte), from
`Preset.SetFromSysex`. Confirmed live: `values[0:16]` decode to real preset names
(the reference rig's real preset names decode cleanly).

| values | field | notes |
|---|---|---|
| 0–15 | `name[16]` | ASCII, space-padded |
| 16–23 | `greenInitButtons[8]` | bitfield, 1 bit/button → initial GREEN IA states (64 buttons) |
| 24–31 | `redInitButtons[8]` | bitfield → initial RED IA states |
| 32–39 | `expression[8]` | 4 exp pedals × (cmd/chan byte, CC byte) |
| 40–43 | `expressionMin[4]` | per-pedal min (0–127) |
| 44–47 | `expressionMax[4]` | per-pedal max (0–127) |
| 48–51 | `config[4]` | `[0]`=switchPresetOnSelect, `[1]`=tempo(31–250), `[2]`=guitarTuning(low nib), `[3]`=flags: bit2 presetType, bit3 globalIAOverride |
| 52–99 | `midiOn[48]` | 16 MIDI messages × 3 bytes (cmd/chan, data1, data2). cmd nibble: 7=off, 6+ = MIDI command |
| 100–129 | `iaoverride[30]` | up to ~7 IA-override entries × 4 bytes (switch#/on, cmd/chan, data1, data2) |
| 130–169 | **v6 extension** | 40 extra values added since 2013 — map from dump + editor |

The per-preset v6 blocks (types 9 & 10, numbered per preset) hold further v6 fields
(extra IA/MIDI messages, scenes, colors, etc.) — mapped during P3/P5.
