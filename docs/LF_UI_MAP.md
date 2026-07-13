# LF+ Editor v6.31 — UI Map

Captured by driving the live `/Applications/LF+ Editor.app` with the 384-preset reference rig loaded
(a real 384-preset rig). The editor's own loader confirmed our protocol counts exactly:

> Loaded: **384 Presets, 254 Songs, 128 Setlists, 50 Pages, 180 IA-Slots, 60 IA Maps,
> 255 Sysex msgs, Global Settings Found.**

This pins the record types: **7 = Pages (50)**, **8 = IA-Maps (60)**; 1–6 as in `LF_PROTOCOL.md`.

## Window chrome (all tabs)

- **Title bar:** `LF+ Editor   Version 6.31   <connection status>`
- **Toolbar (left):** open · save · backup · clear · copy · paste
- **Tab buttons (two rows):** row 1 — Presets · Set-List · IA-Slot · IA-Maps · Midi/Groups · Global;
  row 2 — Songs · Pages · Sysex Msgs · Exp Pedals · Colors
- **Right cluster:** `CONNECT` (red/green) · `Q-LIST` toggle · FAMC logo
- **Menus:** File · Edit · Utilities · Hardware · Reports · Complete Transfers · Settings
- **Per-record header (data tabs):** record selector (spinner + ◀▶), Full Name, Nick Name,
  and transfer buttons **To LF+ · From LF+ · All To LF+ · All From LF+**.

## Tabs → record type → contents

| Tab | Record | What the screen edits |
|---|---|---|
| **Presets** | 1 (×384) | Per-preset. **Initial IA States** (momentary/preset, resend, block exp pedal, reset-button function, multi-press, sync-preset, default page, IA-Slot Map, page-button start). **Command Programming** grid (Function / MIDI / Cmd / PC# — e.g. `MIDI Command Kemper PC# 021`, `Nord G2 CC#`, `IA ON Trig (map)`). **MAP Label / Initial IA-Slot States** (numbered list 01–60 of IA-slot labels + On/Off state). **Step Names** (Step #1–4) + **IA-Slot Defined Labels** (1–10). |
| **Set-List** | 5 (×128) | **Set-List Parameters** (Last Song Slot, End-of-List Cycle). **Song Definitions** — grid of ~58 song slots (`#001`) each with an enable toggle. |
| **IA-Slot** | 3 (×180) | One IA switch. **IA Slot Settings**: Switch Type (Step/Toggle/Momentary…), Enable/On State, Off/On/Bypass/Blocked **colors**, Group ID, Group Post Trigger, Sync Device, Global-IA flag. **On Command Programming** + **Bypass (OFF) Command** — MIDI message grids. **Force Step / Remember on Preset / State**, Steps #1–4. |
| **IA-Maps** | 8 (×60) | One IA-map = 60 button→IA-slot assignments shown as a 60-cell grid (named slots + `#041…#060` unassigned). Map has a name/nick. |
| **Midi/Groups** | 4 (global) | **Exclusive Groups**, **Grouped IA channels** (Make…), **MIDI Channel Device Configuration** — 16 channels, each: Channel Name, Bank ±1, sensitivity/instant/Pre, Max. `Send Globals` / `Get Settings`. |
| **Global** | 4 (global) | Sub-sections: **Preset Parameters**, **External Device Sync**, **Hardware**, **Extender**, **LCD Behaviour** — dozens of dropdowns/toggles (MIDI thru, sysex, guitar tuner, power-up mode, tap-tempo, page buttons, expander, LCD lines, etc.). |
| **Songs** | 2 (×254) | **Song Preset Definitions** — 24 preset slots, each with an LCD button label + Use toggle. **Command Programming** grid. **Parameters**: Trigger Type, **Enable MTC** (Hour/Min/Sec/Frame timecode). |
| **Pages** | 7 (×50) | A physical-layout editor: **60-Button Page** grid (each cell = an assigned IA-slot/preset), a **virtual-page navigator** (numbered button blocks), **Page Parameters** (status, dynamic IA, menu button, IA-Slot trigger, force IA), **Page Button Definition** (Function 1/2 = Preset/Empty, Enable, Tri-Button press, IA-Map for display). |
| **Sysex Msgs** | 6 (×255) | **Sysex Message Data** — 16 byte cells (HEX + DEC entry). **Pre/Post Sysex Message** selectors. **Auto-Create MMC** (HR/MN/SEC/FR/FF → Create MMC/P/S/C). |
| **Exp Pedals** | 4 (global) | 4 **Expression Pedal** columns: Type/Chan, auto-calib/reset/force, CC#, Hi-Res Mod 2nd button, Heel/Toe slice trigger, Sensitivity/Heel level, Min/Max CC sweep. Live-calibration row (Save Exp1–4, Start/Reset, Stop Live). |
| **Colors** | 4 (global) | **Global Command Color Assign** — a colour per function button (Menu, Enter/Sel, Change Pg, Content/Preset/Bank/SetList/Song/Page Up-Down, Global Page, Jst/Jack Preset, Last Page) + **Preset Button** colours (selected / not). |

## Transfer model (the Connect / To-LF+ / From-LF+ verbs)

- **From LF+ / All From LF+** = read one / all records of a type from the device.
- **To LF+ / All To LF+** = write one / all records back.
- **backup** = full dump to `.syx`; **open** = load `.syx` (via the *File Filtering* dialog that
  lets you choose which record ranges to import — Presets min/max, Songs, etc.).
- **Q-LIST** = quick-list mode (queue of pending transfers).

The native rewrite reproduces this: a left record-rail + these four transfer buttons per data
tab, backed by `lfeditor/comms` (file now; USB-serial/MIDI later).

## Panel sizing (for GUI-automated RE)

Each tab's Xojo panel is a **fixed-pixel** layout that sizes to its own content, independent of
the OS window. Two consequences for driving it via automation:

- **Global** renders wide and, with the window enlarged, its controls become comfortably
  clickable — this is the tab to keep maximised when diffing global settings.
- **Exp Pedals** renders in a fixed, *narrow* panel (left half) with very dense ~3px per-pedal
  controls; widening the OS window does **not** enlarge it. Its steppers reject synthetic input
  (see `LF_DATA_MODEL.md`), and its per-pedal toggles are mappable but fiddly.
- **Presets / IA-Slot** and the other data tabs render full-width and are comfortable to drive.

## Notes for replication

- The original is **extremely dense** (Xojo fixed-pixel layout). The PySide6 rewrite uses Qt
  layouts + `.ui` files; we reproduce *structure and field set* faithfully, not pixel positions.
- Heavy reuse of small repeated widgets: a **MIDI-command row** (Function/Cmd/Chan/Data1/Data2),
  a **colour dropdown**, an **IA-slot picker**, a **spinner+nick header**. Build these as shared
  Qt widgets and compose every tab from them.
