# LF+ Editor v6.31 — original per-tab layout (build spec for the faithful rebuild)

Captured from the live `com.famcmusic.lf-plus-editor` v6.31 on 2026-06-15 (the 384-preset reference rig loaded).
This is the **target** for the native rewrite's GUI. All toggles in the original are **vertical
red/green rocker switches** (green = on); name fields are **green LCD**; section panels are
bordered with a cyan title. Every data tab has the per-record header:
`eye · link · TabName · 🔍 · spinner NNN ▲▼ · Full Name (green) · Nick Name (green) · To LF+ · From LF+ · All To LF+ · All From LF+`.

## Presets — 3 columns
1. **Initial IA States**: `ACT AS: IA-Slot / MOMENTARY / Preset` (rocker); `RESEND INITIAL IA
   STATES/VALUES` → IA_Slots · EXP PDL Val · Globals (3 rockers); `Replace Global IA's w/Initial
   States` (rocker); `BLOCK EXP PEDAL UNTIL ASSIGNED VALUES` #1–#4 (rockers); `RESET BUTTON
   FUNCTION #1/#2 PAGE SETT` → Non-Preset Funct · Preset Funct (rockers); `Allow multi presses`,
   `Process Preset Commands After IA's`, `Send as [bypass] for initial BLOCKED`, `(IN) SYNCPreset
   Name`, `IA Effects` (rockers); `Default Page` (combo), `IA-Slot Map` (combo), `Page Button
   Start Value` (combo).
2. **Command Programming**: table `Function | MIDI | Cmd | PC#/CC# | Data` (selected row editable
   via dropdowns); below: **Step Names** (STEP #1–4 green fields + Remember Last Step · Use Map
   Labels rockers) and **IA-Slot Defined Labels** (1–10 green fields, 2 cols).
3. **MAP Label / Initial IA-Slot States**: 60-row table `MAP BTN L… | IA [#] Name | State`
   (State = On green / Off grey).

## Set-List — params row + grid  ✅ REBUILT (5×12)
- **Set-List Parameters**: `Last Song Slot Used` (combo, e.g. ALL), `End of List Cycle Type` (combo, STOP).
- **Song Definitions for the Set-List**: 60 song slots in **5 columns × 12 rows**; each = song
  name combo `(001) Song #001` + round remove button.

## IA-Slot — settings + two side-by-side command tables
1. **IA Slot Settings**: Switch Type (combo STOMP); Enable (rocker) + On State (icon); Preset
   Label (combo); Off/On/Bypass/Blocked Color (combos); Group ID (combo); Group Post Trigger
   (combo); Sync Device box (combo NONE).
2. **On Command Programming** + 3. **BYPASS (OFF) Command Programming** — two identical tables
   `Function | MIDI | Cmd | CC# | Data`, **side by side**.
- Bottom: Force Step#1 on Preset Chg (rocker), Remember Step State (rocker), STEP #1–4 (green buttons).

## IA-Maps — one grid  ✅ REBUILT (6×10 name pickers)
- **IA Slot Mapping**: 60 slots in **6 columns × 10 rows**; each = IA-slot name combo
  `(001) Sound Sculpture` (red text) + remove button.

## Midi/Groups — 3 columns  ✅ REBUILT
- **Exclusive Group Trigger IA's**: 7 rows (IA-slot combo + "Always" rocker).
- **Grouped IA config**: 7 rows (combo Make,then Break / Break,then Make).
- **MIDI Channel Device Configuration**: **two columns × 8**; row = `# · green name (sync icon) ·
  +1 · BANK send · BANK msb · Max Pre` (rockers + green Max Pre).

## Global — 5 columns  ✅ REBUILT
1. **Preset Parameters**: [OFF] IA's send [BYPASS] cmds, Force IA Cmd send with Presets, Block
   Multiple Preset Presses (rockers); Power-Up: Block Boot-Up MIDI Transmission (rocker), Mode /
   Page / Preset / Song / Set-List (combos).
2. **External Device Sync Items**: Guitar Tuner (combo) + Blk Display · Auto Start (rockers) +
   MIDI Chan (num); Preset/Scene/Perf Name Src (combo) + Save Sync Preset Name (rocker); External
   Device Model (combo) + Force changes · Save Sync IA States (rockers). **TAP TEMPO**: Source ·
   Type · Button · Auto-Tap-Msgs · Tap Light ON Time (combos) + MIDI Clock Out Enable · Show/send
   MIDI Clock OUT · Sync Taps to MIDI Clock IN · IA-Slot Toggle (rockers).
3. **Hardware**: MIDI Thru (rocker)+Sysex(num), Allow MIDI (rocker)+MIDI Chan(num), Physical Btn
   Start Value(num), 2nd func hold time(combo), Scroll Delay(num), Force 2nd func ASAP (rocker);
   **Reset Page Button Function Order**: Bank Chg · Song/Set Chg · Page Chg (rockers); **Combo
   Button Press Blocking**: MENU · PAGE · PRESET · SAVE/COPY (rockers).
4. **Extender**: Type (combo); via Expansion Connector: Device ID(num) + Extender 'End' (rocker)
   + Hub Connection (combo); via Standard MIDI: Expander via MIDI CHAN (num).
5. **LCD Behavior**: Reverse Main Display Lines, Line 1 State, Show 2nd Function Name, Line 2
   State, Show Bypass as OFF on Button, Clear Button LCD when off (rockers); IA Display on Main
   LCD (combo Delay/Hide).

## Songs — preset slots + command + params  ✅ REBUILT (LCD labels + MTC: enable@118, H/M/S/F@114-117)
1. **Song Preset Definitions (and labels for 1-12)**: 24 preset slots in **2 cols × 12**; each =
   preset combo `-- NOT USED --` + remove button. Slots 1–12 also have an `LCD Button Label`
   green field; a `Use Labels` rocker sits at the top.
2. **Command Programming**: Function table + Resend Programming w/each preset trigger · w/each
   Re-trigger (rockers).
3. **Parameters**: Trigger Type (combo Immediately); Enable MTC Mode (rocker) + Hour/Min/Sec/Frame (nums).

## Pages — graphical pedalboard  ✅ REBUILT (+ function-byte → label decoder)
- Physical 4×3 switch tiles (number both sides + footswitch glyph + 2 function-name lines);
  page-group navigator (Start 1/13/25/37/49 blue boxes); Page Parameters; Page Button Definition.

## Sysex Msgs — data + links + MMC
- **Sysex Message Data**: 16 columns, each green `&hNN` hex entry + HEX/DEC read-outs (blue).
- **Pre and Post Sysex Message Send Links**: Pre / Post link combos.
- **Auto-Create MMC Messages**: HR/MN/SEC/FR/FF nums + Create MMC Locate / Play / Pause / Stop /
  Continue buttons.

## Exp Pedals — 4 pedal columns  (already close)
- 4 columns (Expression Pedal 1–4): Type combo, Type Chan combo, auto-calibrate · block reset ·
  force zipper (rockers) + CC#, Hi-Res Mode + 2nd Button, Blk Heel/Toe Sensitivity + Toe Trig,
  Sensitivity Level + Heel Trig, CC Sweep Min/Max. Bottom: live-calibration row (Reset / Min /
  Max / MIDI / B1 / B2 / Save ExpN Calibration / Stored Calibration State).

## Colors — function + preset button colours  ✅ REBUILT (4-col)
- **Function Button Colors**: 20 colour combos in **4 columns × 5** (Menu, Enter/Select, Change
  Page, Context Up/Down | Preset Up/Down, Current Mode, Bank Up/Down | Song Up/Down, SetList
  Up/Down, Global Page | Page Up/Down, Last Preset, Save Preset, Last Page).
- **Preset Button Colors**: Preset as Button Func #1 (selected / not selected) · Func #2
  (selected / not selected) colour combos.
