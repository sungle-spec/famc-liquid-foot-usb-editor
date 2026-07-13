# Liquid Foot+ Data Model

The device's editable state, as classes in the decompiled 2013 JAR
(`reference/jar_decompiled/liquidfoot/`). Each maps to one sysex record type (see
`LF_PROTOCOL.md`). The JAR is the **authority for field semantics**; v6.31 grew several records,
so on-wire **lengths come from the dump**, not the JAR constants.

| Model class | Record type | 2013 values | v6 values | Holds |
|---|---:|---:|---:|---|
| `Preset` | 1 | 130 | 170 (+ ext 9,10) | name, initial IA states, 4 exp pedals, 16 MIDI msgs, IA-overrides, tempo, tuning, flags |
| `Song` | 2 | 76 | 125 (+ ext 11) | name, ordered preset list, per-song settings |
| `IASwitch` | 3 | 131 | 250 | one IA-slot: label, type (momentary/toggle/step…), step list, MIDI/command payloads |
| `Config`/`GlobalConfig` | 4 | — | 250 | global device settings (MIDI chan, sysex id, hardware, LCD, external-device sync, tempo) |
| `Setlist` | 5 | 37 | 90 | name, ordered song list (`SETLIST_PRESETS_MAX=20`) |
| `SysexMSG` | 6 | 34 | 42 | a user sysex string (16 data + 16-char name + link) the controller can transmit |
| *(v6 table 7)* | 7 | — | 210 ×50 | likely **IA-Maps** (button→IA-slot maps; editor "IA-Maps" tab) |
| *(v6 table 8)* | 8 | — | 100 ×60 | likely **Pages / Groups / Exp-pedal** global tables |
| *(v6 preset ext)* | 9,10 | — | 80 / 160 ×384 | per-preset v6 additions (scenes, colors, extra messages) |
| *(v6 song ext)* | 11 | — | 96 ×254 | per-song v6 additions |

## Key counts (constants → v6 actuals)

- Presets: `presetMax=251` (2013) → **384** (v6, matches binary string "max # of presets is 384")
- Songs: **254**, Setlists: **128**, IA-Slots (`IASwitch`): **180**, SysexMSGs: **255**
- Buttons per preset: 64 (`maxButtons`), tracked as 8-byte green + 8-byte red bitfields
- Exp pedals: 4 per preset; MIDI messages: 16 per preset; IA-overrides: ~7 per preset

## v6 name layout (verified across all name-bearing types)

Every name-bearing record (Preset, Song, IASwitch, Setlist, SysexMsg, Page, IAMap) begins:

| values | field | notes |
|---|---|---|
| 0–15 | **full name** | 16 ASCII chars, space-padded |
| 16–23 | **nick name** | 8 ASCII chars (a v6 addition — the "Nick Name" box in every tab) |
| 24… | type-specific body | reorganised vs the 2013 JAR |

Verified by decoding all three dumps: e.g. IASwitch #0 full `Sound Sculpture` / nick `Fun`,
Page #0 `Skrydstrup` / `MR10`, IAMap #0 `IA-Map Default` / `MAIN MAP` — matching the live editor.
SysexMsg data bytes follow the names at **24–39** (16 bytes).

> **Offset caveat.** Because v6 inserted the 8-char nick (and extra blocks), the 2013 JAR byte
> offsets *past the names* no longer line up. The editor therefore surfaces only **verified**
> fields (names; sysex data) as widgets and shows the rest in a raw-value table. Deeper offsets
> (preset tempo / initial IA states / MIDI messages, IA-slot type & colours, song preset lists,
> page button maps) are pinned one at a time by **diffing live-editor exports** — change one
> field in the real LF+ Editor, re-backup, diff the `.syx`. All edits stay lossless meanwhile.

## Diff-RE results (deep v6 offsets, measured live)

Pinned by `scripts/diff_dumps.py` (change one control in the real LF+ Editor → re-export →
diff). **Global Config record #1** (the 2nd type-4 record) holds the colour assignments;
colour byte encoding (from the editor's combo): `0=Off, 1–7 = Green/Red/Yellow/Blue/Cyan/
Purple/White (Dim), 9–15 = same order (Bright)`.

**Global config (type 4)** — two records. **Record #1**: value[0:128] = the 16 MIDI-channel
**device names** (8 chars each — MR10, Kemper, Diezel, Whammy1, … referenced by every MIDI
command's channel), value[128+] = the colour block below. **Record #0**: numeric global / exp-
pedal settings. Tabs auto-select the right record.

**Expression pedals (Config record #0):** 4 pedals — **value[5+i] = pedal type** (Not Active /
Continuous / Latch / Momentary / 1-2 ignore / Trigger-IA / Toggle-IA / Page-Button-Press /
2-Page-Buttons), **value[9+2·i] = pedal CC#**. Two per-pedal toggles are packed as **bitfields,
one bit per pedal** (bit i = pedal i+1): **value[37] = auto-calibrate**, **value[69] = block-reset**,
**value[70] = force-zipper** (live-RE'd 2026-06-16).
Four more are **field-major arrays of 4 pedals (stride 1)**: **value[53+i] = CC-sweep min**,
**value[57+i] = CC-sweep max (stored inverted: byte = 127 − shown)**, **value[61+i] = toe trigger**,
**value[65+i] = heel trigger** (0 = none). Pinned by a user-assisted single-variable diff on
pedal 1 (Min 17, Max 113→byte 14, Toe 23, Heel 29) and corroborated by the baseline bytes —
e.g. the Max array [57..60] = [1,0,0,0] is exactly 127−{126,127,127,127}.

Two dropdowns (mapped by solo GUI clicks — dropdowns respond to automation, steppers don't):
**MIDI channel = low nibble of value[10+2·i]** (the cmd/chan byte that pairs with each CC byte;
high nibble = expression command, à la the 2013 JAR's `expression[2n]`); 0-based, 0 → channel 1.
Confirmed: pedal 2's byte 0xB7 → chan 7 = Whammy2. **Sensitivity = value[33+i]**, enum
{0 Default, 1 Ignore, 2 High, 3 Low}.

**Per-pedal flags byte value[71+i]** (live-RE'd on a real LF+ 12+, fw 6.32, 2026-06-16 — earlier
notes that these "write no byte" were wrong): **bit 0x01 = Blk Heel/Toe Sensitivity**, **bit 0x10 =
Hi-Res Mode**. Hi-Res additionally forces a re-calibration (it resets that pedal's calibration block).
The **2nd-Button** field stays disabled for the Continuous pedal type, so it's still unmapped.

**Calibration block value[17:33]** (confirmed by live pedal calibration, 2026-06-16): two 2-byte
little-endian arrays of 4 pedals — **value[17+2·i] = calibrated MAX (toe) ADC**, **value[25+2·i] =
calibrated MIN (heel) ADC**. Set by physically sweeping the pedal (pedal 1: 409/10 → **1023/84**);
raw ADC data, not typeable, round-trips losslessly. "Hi-Res Mode" resets it (hence the recal prompt).

**Global settings (Config record #0):**
- **Power-up block:** value[185] mode (Last/Preset/Song/Set-List), value[99] page (0-based),
  value[189] preset (0=ignore), value[186] song (0=ignore), value[187] set-list (0=ignore).
- value[104] guitar-tuner source (Liquid / Axe-FX / Kemper).
- value[194] external-device model override (0 = ignore; debug use).
- **Tap-tempo block:** value[121] beat source (Liquid / Axe-FX / Kemper), value[118] display
  type (Actual / Average BPM), value[181] blink button (0 = none, 1 = auto-detect, 2..61 =
  force button 1..60).
- **Hardware block (contiguous):** value[46] MIDI-Thru (editor on=0), value[47] Allow-MIDI-in,
  **value[48] Sysex device ID**, **value[49] global MIDI channel (0-based; 15 → editor "16")**.
- **Hardware steppers:** **value[44] Physical-Btn / Page-Btn start** (0-based; display = value+1),
  **value[106] 2nd-function hold time** (0.5 s units; value = seconds×2, so 5 = 2.5 s),
  **value[107] scroll delay** (raw).
- **Toggle bytes:** value[109] show-bypass-as-OFF, value[110] clear-button-LCD,
  value[117] show-2nd-function, value[180] bit1/bit0 = LCD line 1/2 state,
  value[182] force-2nd-function, value[192] reverse-main-display.
- **"Preset as Button" colours (in Config #0, not the #1 colour block):** value[113] Func1
  selected, value[114] Func1 not-selected, value[133] Func2 selected, value[134] Func2 not-selected.
- **Midi/Groups settings (Config #0; the channel *names* are in Config #1) — now fully mapped:**
  - value[122..128] = the 7 **Exclusive Group** trigger-IA slots (each = IA-slot #, 0 = none).
  - The **"MIDI Channel Device Configuration"** grid is four parallel per-channel fields. The three
    rocker toggles are bitfields, one **byte for ch 1–8** (bit i = channel i+1) and the **next byte
    for ch 9–16**: **BANK +1** = value[101]/[102], **BANK send** = value[144]/[145], **BANK msb** =
    value[146]/[147]. (Confirmed: +1 0x40→0x41 = ch7 baseline + ch1; send baseline 0x02 = ch2, ch3
    flip →0x06, ch12 flip → value[145]=0x08; msb baseline 0x42 = ch2+ch7, ch3 flip →0x46.)
  - **Max Pre** (max preset reachable per channel) = a **2-byte little-endian** value at
    value[148 + 2·ch], where the *displayed* number is `(low + high·256) + 1`. Verified against the
    full 16-channel fingerprint 120/753/128/128/128/124/100/128/128… (e.g. 753 → bytes 240,2 → 752+1).
  - **Grouped-IA config** = a single-byte bitfield at value[105]: **bit n = group #n** (n = 1…7),
    bit **set** = "Break, then Make", **clear** = "Make, then Break" (bit0 unused). Confirmed by
    baseline 0x54 = bits 2/4/6 (= groups #2/#4/#6 in "Break, then Make") and flipping #1+#7 → 0xD6.
    Semantics (from the editor tooltip): whether the group sends the selected IA-slot's ON commands
    before the others' BYPASS, or vice-versa.
  - These all live in Config #0, so — like the +1 grid and Exclusive Groups — they surface on the
    **Global** tab in our editor (a tab binds to one record; Midi/Groups binds to the #1 names record).

> **Sysex ID / MIDI channel were pinned by static analysis, not diff-RE.** The live editor's
> `NumericStepper` controls (Sysex ID, MIDI Ch, 2nd-func hold time, scroll delay, Physical-Btn)
> reject *all* synthetic input — verified exhaustively: arrow-click, deliberate mouse press/
> release, typing into the box, keyboard Up/Down, scroll-wheel, and click-drag, none of which
> move the value (checkbox/toggle controls in the same panel respond fine, and the window size
> makes no difference — a *real* human click would work; only synthesized events are dropped).
> So these two were located by their known values in the decoded Config and corroborated across
> all three device dumps. The match is **self-confirming**: value[48] = 124 = `0x7C`, exactly the
> device-ID byte in every sysex frame header (`F0 00 00 7C …`); value[49] = 15 matches "MIDI Chan 16".
>
> The other three steppers (2nd-func hold, scroll delay, Physical-Btn start) couldn't be pinned by
> *any* automated offline method — GUI diff-RE is blocked (synthetic input, above); all three
> dumps are identical except value[117] so cross-dump differential is useless; and the 2013
> `Config.java` order diverges right after the anchor (it reads `…Sysex, Midi, DefaultMode…` but
> v6 relocated DefaultMode from value[50] to value[185]). They were finally pinned by a
> **user-assisted clean pass**: the user changed only those three with real clicks, to spread-out
> values (Physical-Btn 49, scroll 30, hold max 2.5s), and one diff isolated value[44]/[106]/[107]
> unambiguously. (A first attempt where the user changed ~everything at once failed: 26 bytes all
> went 0→1, drowning scroll delay — single-variable changes are essential.)
>
> The "Save Sync"/"Force changes" controls are editor *actions* (they trigger a send, not a
> stored flag — clicking produced no byte delta).

Storage order ≠ the dense visual layout, so each remaining Hardware / External-Sync / Extender
setting is mapped one diff at a time. (Tiny ~3px toggles need precise clicks; all bytes remain
editable via each tab's Raw-decoded-values table regardless.)

**Function-button colours (Config #1, all measured):** Menu 128, Enter/Select 129, Change Page
147, Context Up 130, Context Down 131, Preset Up 132, Preset Down 133, Current Mode 146, Bank Up
134, Bank Down 135, Song Up 136, Song Down 137, SetList Up 138, SetList Down 139, Global Page 142,
Page Up 140, Page Down 141, Last Preset 144, Save Preset 145, Last Page 143. Storage order is **not**
the visual grid order (e.g. Current Mode at 146, Change Page at 147), so each was diff-measured.

**Preset record (type 1)** — verified offsets into the decoded values:

| value index | field | notes |
|---|---|---|
| 0–15 | full name | |
| 16–23 | nick name | |
| 24–31 | **initial IA-slot ON states** | 8-byte bitfield; slot N (1-based) → byte `24+(N-1)//8`, bit `(N-1)%8` |
| 44–75 | step names | 4 × 8-char ASCII (STEP # 1 …) |
| 76–139 | **command programming** | 16 entries × 4 bytes `[func, b1, b2, b3]`. func: 0 Empty, 1 MIDI Command (b1/b2/b3 = MIDI status/data1/data2), 10 IA-ON / 11 IA-OFF / 12 IA-Toggle / 13 IA-Resend Trig (map) / 14 IA-Set-Step (b1 = value) |
| 40 | **default page** | 0 = use currently-active page, else page number |
| 41 | **flags A** | bit0 resend IA-slots, bit1 resend globals, bit2 replace-global-IAs, bit4 act-as-IA-slot, bit5 allow-multi-press, bit7 reset-btn-non-preset-fn |
| 42 | **flags B** | bit0 IA-effects, bit1 process-preset-commands-after-IAs, bit2 sync-preset-name, bit3 reset-btn-preset-fn, bit4 exp-block master, bit5 send-as-bypass |
| 158 | **IA-slot map** | 0-based IA-map index for this preset's page |
| 160 | **block exp pedal** | bitfield: bit0..3 = block exp pedal #1..#4 until assigned |

Confirmed against the rig: preset #1 → value[24]=0x03 (slots 1 & 2 on), default page 0, map 0.

**Song record (type 2)** — verified offsets:

| value index | field | notes |
|---|---|---|
| 0–15 / 16–23 | full / nick name | |
| 64 | **trigger type** | 0 Immediately · 1 Arm only |

(The 24-slot song preset list is at value[65:113] — 2-byte LE, `0xFFFF` = unused — and is
surfaced as the Songs tab's name picker; see the membership section below.)

**Setlist record (type 5):** full/nick name at 0–23; **60-slot song list** at value[24:84],
**song count** at value[84], **end-of-list cycle** at value[85] (0 Stop · 1 Top→1st song ·
2 Bottom↔Top); value[86:90] reserved. Fully mapped — see the membership section below.

**IA-Map record (type 8):** full/nick name at 0–23; **value[24:84] = 60-cell button→IA-slot
map** (each cell = 0-based IA-slot index; "IA-Map Default" = identity 0..59). Tail **value[84:100]
is reserved** — all-zero across every one of the 3,993 IA-maps in the corpus (raw view starts at
100, i.e. empty).

**Page record (type 7):** full/nick name at 0–23; two parallel 60-entry button arrays —
**value[24:84] = button Function-1 assignments**, **value[84:144] = Function-2** (confirmed by
diffing Skrydstrup vs Kemper pages). **Entry encoding fully decoded** (2026-06-15, from the
v6.31 editor's own page-button Function dropdown, read directly (2026-06-16, inverted probe) —
`model/page.py::decode_button_function`): `0`=NOT DEFINED · `1–60`=PRESET B#NN (preset button in
the current bank) · `61–80`=SYSTEM FUNCTION 1–20 (byte = 60+fn: MENU=61, Enter/Select=62, Context
UP=63, Context DWN=64, Preset UP/DWN=65/66, Bank UP/DWN=67/68, Song UP/DWN=69/70, SetList
UP/DWN=71/72, Page UP/DWN=73/74, Global Page=75, Last Page=76, Last Preset=77, Save Preset=78,
**Current MODE=79** (the 2015 manual's older "MODE CYCLE" name), **Change PAGE=80**) · the v6.31
list ends at fn 20, so `81–127` are higher system fns with no defined name (shown generically) ·
`128–187`=IA-slot trigger (slot = byte−127) · `200+`=Page switch (page = byte−199). Names are the
exact editor strings. The editor's button editor is a Type dropdown (Empty/Preset/Function/IA
Slot/Page Select) + a value list of that type's items.
**Page-parameter block** — re-verified byte-for-byte by **live hardware diff** (LF+ 12+, fw 6.32,
2026-06-16), which corrected three earlier mis-maps: **value[204] Status #1 LED colour**
(COLOR_NAMES), **value[205] Force Mode Change** packed byte with **bit 0x02 = all-buttons-double-tap**
(0→2 on toggle), **value[206] = "menu button trigger"** (0 = "B2+B3=Menu", 1..60 = trigger button #;
tracked 1→60 exactly), **value[207] Force IA map** (map #; 0→7), **value[208] = preset-button
colours** packed — low nibble = SELECTED, high nibble = NOT-SELECTED (COLOR_NAMES nibble, 0 = "Use
Global Settings"; selected Green-Dim + not-sel Red-Dim → 0x21), **value[209] = "IA-Slot to Trigger"**
slot number (0=none, 1..60; 0→7). *(Earlier RE had double-tap on v[206], the menu-trigger and
colours as "no byte / display-only", and v[208] as an IA-slot "ref" — all wrong; the live diffs are
authoritative.)*
The **per-button flags** array `value[144 + button]` (button 0..59) is mapped: bits 0–1 =
trigger type (0 Toggle&Trigger / 1 Trigger Only / 2 Toggle Only), bit2 = Fn1 "Trigger Scrolls",
bit3 = Fn2 "Trigger Scrolls", bit6 = Enable Double-Tap, bit7 = Press action (Wait-for-Release).
The "IA Map to use for Display" dropdown writes no byte (display only). See the appendix.

**IASwitch record (type 3)** — verified offsets:

| value index | field | notes |
|---|---|---|
| 0–15 | full name | |
| 16–23 | nick name | |
| 24 | **switch type** | 0 Stomp · 1 Momentary · 2 Step · 3 Quick-Tap · 4 Tap-Tempo |
| 25 | **sync device** | 0 None · 1 Liquid Reserve 1 · 2 AXE-FX III · 3 AXE-FX Ultra/II · 4 Kemper KPA |
| 26 | **sync effect** | effect slot in the sync'd device (0–7 Stomp A..Reverb, 8–12 Perf Rig 1–5, 13/14 Perf Up/Down, 15 Tap Tempo) |
| 28 | **group ID** | 0 not grouped, else exclusive group number |
| 29–108 | **On Command Programming** | 20 entries × **4 bytes** `[func, b1, b2, b3]` — the SAME table format as the Preset command table (`decode_command`). func=1 MIDI Command: b1 = status (msgtype<<4 \| channel), b2/b3 = data. The editor's "MIDI" column resolves the channel to its Config#1 device name. **Offset corrected 2026-06-16 from 30→29** (was off by one): proven by func-validity across all 180 IA-slots of the reference rig — byte 0 of every entry is a valid function code only when the region starts at 29 (the old 30 read the MIDI *status* byte as the func, showing "Fn 176"). |
| 109–188 | **BYPASS (OFF) Command Programming** | 20 entries × 4 bytes, same `[func,b1,b2,b3]` layout (corrected 110→109) |
| 221 | **enabled** | bit0 = slot enabled |
| 222 | **remember step** | bit0 = remember last step state across power cycle |
| 225 | **on colour** | colour codes per `COLOR_NAMES` |
| 226 | **off colour** | |
| 227 | **bypass colour** | |
| 228 | **blocked colour** | |
| 230 | **preset label** | 0 = use nick name, else preset-defined label number |
| 231 | **force step #1** | bit0 = force step #1 on preset change |

Confirmed on the rig: slot 1 "Sound Sculpture" → Stomp, on=Green-Bright, bypass=Red-Bright.

> **Key insight:** the device's storage order is **not** the editor's visual grid order
> (Change Page sits at 147, away from its neighbours). So each field must be individually
> measured — there is no "infer the rest of the column" shortcut. Mapping the remaining colours,
> and the Preset / IA-Slot / Song / Global fields, is the same one-field-at-a-time process,
> tracked in `lfeditor/model/config.py` and the per-type specs.

## Field accessors to port (examples, from `Preset.java`)

The JAR exposes clean getters/setters that encode the exact bit math — port these verbatim into
`lfeditor/model/` / `lfeditor/codec/`:

- `GetGuitarTuning` = `config[2] & 0xF`; `GetTempo` = `config[1]` (valid 31–250)
- `GetPresetType` = bit 2 of `config[3]`; `GetGlobalIAOverride` = bit 3 of `config[3]`
- `GetExpressionCmd(n)` = `(expression[2n]>>4) - 7` (0 = off); `…Chan` = low nibble; `…CC` = `expression[2n+1]`
- `GetMidiCommand(n)` = `(midiOn[3n]>>4) - 6` (7 = off); `…Chan` = low nibble; data1/data2 = `midiOn[3n+1/2]`
- `GetIAOverrideSwitchNum(n)` = `iaoverride[4n] & 0x1F`; `…OnOff` = `iaoverride[4n] & 0x80`

`IASwitch`, `Song`, `Setlist`, `GlobalConfig`, `SysexMSG` follow the same accessor pattern — see
their `.java` for the byte math. The v6 extension fields (indices ≥130 in Preset, and types 7–11)
have no JAR accessors and are mapped by diffing dumps and reading the live editor.

## Song & Set-List membership tables (mapped 2026-06-15 by live-editor diff-RE)

Both "definition" tables were pinned by setting one slot in the live editor to a distinctive
value, re-exporting, and diffing:

- **Song "Preset Definitions" — 24 ordered slots.** `value[65 + 2·N]` for N = 0…23, each a
  **2-byte little-endian** preset reference storing `preset_number − 1`; **`0xFFFF` = unused**.
  Confirmed: slot 1 → Preset #300 wrote `value[65]=43, value[66]=1` (`43 + 1·256 = 299` → 300).
  The all-`0xFF` run at `[65:113]` in every default song is 24 empty slots. Surfaced as the Songs
  tab's "Preset slots" grid (`Int16GridField`, 0 = unused).
- **Set-List "Song Definitions" — 60 ordered slots.** `value[24 + N]` for N = 0…59, each a
  **single byte** storing `song_number − 1` (default 0 = Song #1). Confirmed: slot 1 → Song #200
  wrote `value[24]=199`. Surfaced as the Set-List tab's "Song slots" grid (`ByteGridField`).
- **Set-List song count — `value[84]` (0…60).** The number of song slots that are live; the
  device ignores slots at or beyond this index (so empty set-lists keep `value[84]=0` even with
  stale slot bytes). Corpus-validated across 9,984 set-lists — never exceeds 60, and real
  hand-built lists carry the exact count (v4.x PRO+ 3-song lists → `84`=3; Axe-Fx III 8-song
  templates → `84`=8). `value[85]` = end-of-list cycle; `value[86:90]` are reserved (always 0).
  Surfaced as the Set-List tab's "Number of songs" spin box (`IntField`); the record is now fully
  mapped, so its raw table starts at `[86]`.
- **Song MTC (MIDI Time Code) — `value[114:119]`** (mapped 2026-06-15 by a clean single-record
  live diff: enabling MTC + setting Hour=1/Min=2/Sec=3/Frame=4 on song 001 changed exactly these
  5 bytes, the only change in the whole dump). `value[118]` bit0 = **Enable MTC Mode**; `value[114]`
  Hour, `[115]` Min, `[116]` Sec, `[117]` Frame. Surfaced on the Songs tab's Parameters panel.
  (`value[113]` — the lone non-zero song-tail byte in the corpus — is a *different* flag, not MTC.)

### Page per-button flags — `value[144 + button]` (mapped 2026-06-15)

The Page record's third 60-entry array packs each button's parameters into one byte, pinned by
toggling one button-1 control at a time and watching `value[144]`:

| Bit(s) | Mask | Meaning |
|---|---|---|
| 0–1 | `0x03` | Button Pressed Trigger Type (0 = Toggle & Trigger, 1 = Trigger Only, 2 = Toggle Only) |
| 2 | `0x04` | Function-1 "Trigger Scrolls" |
| 3 | `0x08` | Function-2 "Trigger Scrolls" |
| 6 | `0x40` | Enable Double-Tap |
| 7 | `0x80` | Button Press action (1 = Wait for Release, else Immediate) |

Bits 4–5 are unused in the reference rigs. The "IA Map to use for Display" dropdown is **editor-
display-only** and writes no byte (confirmed by diff). This explains the reference `5,5,1,1,64,…`
run. Surfaced on the Pages tab as the "Per-button flags" grid.

### Preset Command Programming — `value[76:140]`, 16 rows × 4 bytes (decoded 2026-06-15)

Each row is `[func, b1, b2, b3]`. `func` (byte 0) selects the function; confirmed against the reference rig and
validated across the 31,504-preset corpus (504,064 rows):

| `func` | Meaning | b1 / b2 / b3 |
|---|---|---|
| 0 | Empty (94% of all rows) | — |
| 1 | **MIDI message** | b1 = status byte (`type<<4 \| channel`); b2/b3 = data |
| 2–67 | special functions (see full table below) | per-function |

**Full function-code table** — RE'd byte-for-byte from LF+ Editor v6.31 by loading crafted presets
with `func` bytes 0..67 and reading the names the editor displays (the dropdown *order* does **not**
match the codes, so this had to be probed). The earlier guess that 13/14 were "IA Resend"/"IA Set
Step" was **wrong** — the real codes are below (`lfeditor/model/preset.py::CMD_FUNCS`):

| | | | |
|---|---|---|---|
| 0 Empty | 17 Go Global | 34 Page Toggle Function #1/#2 | 51 Looper Turn On |
| 1 MIDI Command | 18 EXPR Mod CC# | 35 EXPR Slot 2 MIDI | 52 Looper Turn Off |
| 2 G-Tuner | 19 EXPR Send Value | 36 EXPR Slot 2 CC | 53 EXPR Slot 2 CLEAR |
| 3 Step | 20 EXPR Resend Current | 37 EXPR Slot 2 Invert | 54 Page Change to |
| 4 Sysex Send | 21 IA Resend (map) | 38 Device Sync | 55 Preset Momentary then Jump |
| 5 Delay ms | 22 EXPR Mod MIDI # | 39 IA-Map Change | 56 IA Set Step Number |
| 6 Preset last used | 23 System SnapShot | 40 IF IA is OFF, Stop | 57 PC# + |
| 7 Page last used | 24 System SnapShot 2 | 41 IF IA is ON, Stop | 58 PC# - |
| 8 Page Change | 25 EXPR Change IA trigger | 42 IF IA is OFF, Skip | 59 PC# Save |
| 9 Preset trigger | 26 IA Force Color Change | 43 IF IA is ON, Skip | 60 MIDI Clock (ms) |
| 10 IA ON Trig (map) | 27 Activate MTC | 44 IF Processing Trigger | 61 MIDI Clock (BPM) |
| 11 IA OFF Trig (map) | 28 Set Status#1 LED | 45 Stop | 62 IA Trigger |
| 12 IA Toggle (map) | 29 Auto-Tap-Tempo | 46 EXPR Min Send Value | 63 IA Resend |
| 13 Set Color | 30 Preset Resend IA | 47 EXPR Max Send Value | 64 EXPR Block Xmit |
| 14 Preset Store | 31 Song # Store Current | 48 Page Button Display | 65 EXPR unBlock Xmit |
| 15 Preset Recall Store | 32 Song # Recall Store | 49 Page LOCK to current | 66 AXE3 Chan/State |
| 16 Preset Trig 1st Button | 33 Song Change | 50 Page UNLOCK current | 67 AXE3 Chg SCENE# |

For the slot/map functions (10, 11, 12, 21, 39, 56, 62, 63) `b1` is the IA-slot / map number. Other
functions carry function-specific parameters in b1–b3; the editor surfaces them as raw Data fields
(byte-exact), so every function is selectable and editable even where its bespoke parameter UI
isn't replicated.

For a MIDI message (`func==1`) **every one of the 28,695 corpus rows carries a valid `0x80–0xEF`
status byte** (0 exceptions). Data layout by message type (high nibble of b1):

- **Control Change** (`0xB`): b2 = CC#, b3 = value.
- **Program Change** (`0xC`): program = `(b2<<8) + b3` — b2 is 0 for normal gear, non-zero for
  AXE-FX's 0–383 range (8,759 corpus rows use the high byte).
- **Note Off/On, Poly Pressure** (`0x8/0x9/0xA`): b2 = note, b3 = velocity/pressure.
- **Channel Pressure** (`0xD`): b3 = pressure. **Pitch Bend** (`0xE`): value = `(b3<<7) | b2`.

`model/preset.py::decode_command()` renders these (e.g. `PC ch2 → prog 21`, `CC ch12 #19 = 12`);
the Presets tab shows a read-only **Decoded** column beside the raw editable B1/B2/B3 cells.

### Extension records & more sections (RE 2026-06-15)

The three v6 **extension records** are flat arrays of 8-char ASCII labels, linked to their parent
by record number (1:1 in a full rig — verified on the 384-preset reference rig: 384 each of Preset/Ext9/Ext10, 254 each of
Song/SongExt11). See `model/ext.py`:

| Record | Len | Contents |
|---|---|---|
| **PresetExt9** (type 9) | 80B | **10 IA-Slot Defined Labels** (8 chars) — CONFIRMED by corpus content (`Basic`, `Delay`, `Driven`, `Solo`, …) |
| **SongExt11** (type 11) | 96B | **12 Song LCD Button Labels** (slots 1–12) — structure matches; space-filled in the corpus |
| **PresetExt10** (type 10) | 160B | 20×8 label store — space-filled in the corpus; purpose unconfirmed (likely per-button MAP labels). Surfaced editable on the Presets tab as "Preset MAP Labels"; round-trips losslessly |

Other sections pinned this pass:
- **Song Command Programming** = `value[24:56]` (8 entries × 4 bytes), identical `[func,b1,b2,b3]`
  encoding as the preset command table; `value[56:64]` reserved.
- **Sysex** Pre/Post message links at `value[40]`/`value[41]` (0 = no link). MMC is an editor
  *tool* that fills the 16 data bytes, not a stored field.
- **IA-Slot** Global-IA flag (`value[27]` bit 7). (The "Group Post Trigger" field previously mapped
  at `value[29]` was a mis-RE — that byte is the first On-command's func byte; the field was removed.)

**Config#0 — now fully mapped for every user-facing control** (live-diff campaign, 2026-06-15).
All Global-tab toggles, steppers and dropdowns are pinned (see `model/config.py`): Combo-Button
blocking `value[50]`, Reset-page-button order `value[132]`, guitar-tuner Blk-Display/Auto-Start
`value[183]`, external-sync flags `value[135]`, tap-tempo flags `value[196..198]`+`value[118].7`,
Force-2nd-ASAP `value[182]`, Extender-'End' `value[45]`, Preset-Parameters `value[100/111/112/184]`,
plus the selector offsets Name-Src `129`, Tap-Source `121`, Auto-Tap-Msgs `195`, Tap-Light `199`,
Extender Type `41` / Device-ID `42` / Hub `119` / Expander-CHAN `201`, IA-Display-on-LCD `188`.
Exp-pedal Blk-Heel/Toe-Sensitivity = `value[71+pedal]` (surfaced editable on the Exp-Pedals tab;
in the original this control also triggers a hardware calibration reset, but the stored byte is a
plain per-pedal value that round-trips).

What's left is **not user-editable**: `value[17:33]` is the per-pedal **calibration/range block**
(Hi-Res Mode rescales it; the live-calibration writes raw ADC ranges — "2nd Button" is disabled),
and a handful of device-internal bytes (`value[0,3,38,40,90,92:97,115,116,200,202]`) that no editor
control maps to (firmware/model/runtime data). All round-trip losslessly.

### Codec validated against a 124-file real-world corpus (2026-06-15)

A broad set of third-party user backups (`reference/sysex_dumps/LF+ Editor Sysex Files/`, local-
only, git-ignored) spanning firmware **v3.x → v6.x** and every variant (**12+, JR, Mini, PRO+**)
was run through the codec. **All 118 genuine LF+ config backups re-encode byte-for-byte** (the
other 6 files are correctly rejected: 5 Fractal Axe-Fx presets with the `00 01 74` manufacturer
ID, and 1 firmware-image `.syx`). This is the strongest available proof that read→edit→write is
lossless across the entire installed base, not just our three reference dumps. `tests/
test_roundtrip.py` runs the corpus automatically when present (and skips it when absent).

No raw/unmapped fields remain in the editor's surfaced records.
