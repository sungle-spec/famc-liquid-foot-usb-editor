# LF+ Editor (native) — User Guide

A native rewrite of FAMC's **LF+ Editor** for the **Liquid Foot+** MIDI foot-controller family
(12+, 12, Mini, JR, Pro). It opens, edits and saves the device's `.syx` backups **losslessly**,
and can talk to the hardware over USB-serial (read + write confirmed on a real Liquid Foot+).

> **📖 The screenshot-illustrated manuals:** [docs/DESKTOP_GUIDE.md](docs/DESKTOP_GUIDE.md)
> (the desktop app — every function + step-by-step scenarios, including the hardware workflows)
> and [docs/WEB_GUIDE.md](docs/WEB_GUIDE.md) (the browser version). This page covers install
> and reference details.

> FAMC is out of business; the original editor is a 2020 Xojo app that won't survive modern
> macOS. This rebuild keeps your rig editable. See [README](README.md) for the project status.

## Install & run (developer build)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m lfeditor                 # launches the editor
python -m lfeditor path/to/rig.syx # …or open a backup directly
pytest tests/                      # run the test suite
```

## Install & run (standalone download — no Python)

Grab the bundle for your OS from the latest release on the
[builds repo](https://github.com/sungle-spec/famc-liquid-foot-editor-builds/releases)
(packaging and distribution live there; this repo is the source):

- **Windows** — unzip `…-windows-x64.zip`, run `LFPlusEditor.exe`. It's unsigned, so SmartScreen
  shows *"Windows protected your PC"* → **More info → Run anyway**. The Liquid Foot+ needs the FTDI
  VCP driver for its USB-serial port to appear — [install steps](docs/GETTING_STARTED.md#3-windows-install-the-ftdi-vcp-driver-first).
- **Linux** — `chmod +x …-x86_64.AppImage` and run it. For serial access add yourself to the
  `dialout` group once: `sudo usermod -aG dialout $USER` (then log out/in).
- **macOS** — unzip and move `LF+ Editor (native).app` to Applications. It's un-notarised, so the
  first launch needs **right-click → Open → Open** (or
  `xattr -dr com.apple.quarantine "LF+ Editor (native).app"`).

**Verify your download** (optional): each release includes `SHA256SUMS.txt`. With it and the
bundle in the same folder, run `sha256sum -c SHA256SUMS.txt` (macOS: `shasum -a 256 -c
SHA256SUMS.txt`) — it should report `OK`.

Building the bundles yourself is covered in [docs/BUILD.md](docs/BUILD.md).

## Use it in a browser (no install)

A **web version** runs the same editor entirely in your browser — open it, load a `.syx`, edit, and
download the result, all offline. It's a **pixel-for-pixel port of all 11 tabs** plus the desktop's
tools: Q-LIST search, Find, copy/paste/clear, raw view, multi-apply, CSV import/export, reports,
the Quick Command Programmer and Re-order Records, and drag-a-record-onto-a-slot. Device read/write
over USB works too (WebSerial; Chrome/Edge only, verified on real hardware — still keep a backup:
writes have no undo).

**→ The full, screenshot-illustrated manual for the web version is
[docs/WEB_GUIDE.md](docs/WEB_GUIDE.md)** — a five-minute quick start plus step-by-step scenarios
(program a preset's commands, arrange a set-list by drag-and-drop, lay out a page, bulk-edit 60
presets at once, CSV round-trips, USB transfer, and more). Technical details: [docs/WEB.md](docs/WEB.md).

## Working with backups (offline)

1. **Open** a `.syx` backup (one you exported from the real LF+ Editor, or a factory file).
2. Pick a record on the left **rail** of any tab (type-to-filter by number or name).
3. Edit fields on the right. Every change is **surgical and lossless** — re-saving rewrites
   only the bytes you changed; untouched data (including fields not yet surfaced) round-trips
   byte-for-byte.
4. **Save** (over the same file) or **Backup** (save-as a new `.syx`).

## Toolbar (icons, like the original)

The toolbar carries the same icon buttons as the original LF+ Editor:

- **Open · Save · Backup** — open a `.syx`, save it, or save-as a new backup.
- **Clear · Copy · Paste** — whole-**record** operations on the record shown in the current tab:
  - **Copy** snapshots the *entire* current record — name, commands, IA-states, flags, and its
    linked label records — into an internal buffer (it does not touch the OS clipboard).
  - **Paste** overwrites the current record's content with the buffer. The record's slot number
    stays; everything else becomes the copied record's. Only a record of the **same type** can be
    pasted (copy a preset → paste onto another preset). Shortcut: `Ctrl/Cmd+Shift+V`
    (copy is `Ctrl/Cmd+Shift+C`).
  - **Clear** resets the current record to its default (e.g. "Preset #005" / "Pre #005", empty
    commands, IA-states off, IA-Map 1), after a confirm.
- **Find** (magnifier, `Cmd/Ctrl+F`) — opens the **Find / Q-LIST** window: search every record by
  name (wildcards) and/or by a MIDI command (channel, message type, CC#/PC#), restricted by record
  type and number range. Double-click a result to jump straight to that record; **Export results**
  writes the hit list to CSV. You can also **drag a result** onto a slot picker (a Song's preset
  slot, a Set-List's song slot, an IA-Map button) to assign it, or **drag an IA-Slot result onto a
  command row** to build an "IA ON Trig" command for it.
- **Q-LIST** (toggle, on by default) — the **left-side record navigator** (it replaces the old
  per-tab record list). It **follows the current tab**: on a record tab it lists that type, and on a
  tab with no records (Global, Midi/Groups, Exp Pedals, Colors) it's empty. **Single-click** an item
  to jump to it; click a **type button** (Preset / Songs / Set-List / IA-Slot / IA-Maps / Pages /
  Sysex) to switch to that tab; **filter** by name or number; or **drag** an item onto a slot picker
  / command row. The record spinner in each tab's header still steps through records too.
- **Connect · From LF+ · To LF+** — device I/O.

> To copy/paste plain **text** inside a field (a name, a label), use the normal `Cmd+C` / `Cmd+V`
> — the icon Copy/Paste are for whole records, exactly as in the original.

## Menus (mirroring the original editor)

- **File** — Open, Save, Backup (Save As); **Load Factory Defaults into Editor ▸** (Mini / JR+ /
  12+ / Pro+) and **Load Special Factory Programming ▸** (Axe-Fx II/III, Kemper). Loading a
  factory file opens it as a new **untitled** document, so you can't overwrite the bundled source —
  Save As to keep your own copy. **Import from CSV ▸** / **Export to CSV ▸** (Presets / Songs /
  Set-Lists / Sysex) round-trip those records through a spreadsheet — the column format matches the
  original LF+ Editor's export exactly, so old exported templates load too. **About / License**
  (in **File** and **Help**) opens a dialog with the version, the full MIT **License**, and a
  **Legal & Safety** notice.
- **Reports** — **Preset / Song / Set-List report**: write a read-only, human-readable CSV summary
  (cross-references resolved to names — e.g. each song's assigned presets by name).
- **Utilities** —
  - **Quick Repeated Command Programmer**: write one command (MIDI or IA-trigger) into a chosen
    programming **row** across a **range** of records (preset / song / IA-Slot ON / IA-Slot Bypass
    command tables), optionally **auto-incrementing the Program #** as it goes — e.g. PC 0,1,2,… into
    row 1 of presets 1–60.
  - **Re-order Records (Save / Sync)**: move a Preset or Song to a new position; with **Sync
    references** on, every Song preset-slot (and Set-List song-slot) that pointed to it is rewritten
    so it still points to the same record after the move.
  - **MIDI Monitor / Pass-Thru**: pick a MIDI input port and log every incoming message (timestamp +
    hex + decoded text); tick **Pass-thru** to relay it to an output port so the editor sits between
    the device and a DAW. Save the log to CSV. (The LF+ presents as USB-serial here, so this is a
    general MIDI tool that works with whatever ports the OS exposes.)

> **Multi-record quick edit:** right-click any toggle (a flag like "Resend IA-slot states") to set
> it the same way across **all** records of that type, or a **number range** — the original's
> right-click multi-preset programming.
- **Edit** — **Copy** / **Paste** the current record, **Clear Current Record**; plus
  **Clear Preset Labels**, **Clear Preset MAP Labels**, **Clear Song Preset Labels**:
  blank the text-label records in the open document (confirm first). They edit the file offline;
  use **Hardware → To LF+** to push the cleared labels to the device.
- **Hardware** — **Device Connection Setup…** (the EEPROM wizard), Connect/Disconnect, From LF+,
  To LF+, **USB MIDI Bridge…** (see below). *Reset Config / Reset to Factory / Load Firmware* are
  shown but disabled in this build (device-side resets and firmware flashing aren't enabled yet).
- **Complete Transfers** — Get-everything-from / Send-all-edits-to the device.
- **Settings** — **Show raw bytes** toggles the raw-decoded-values table on every tab (off by
  default).

### What each tab edits

| Tab | Edits |
|---|---|
| **Presets** | full/nick name, default page, IA-slot map, behavioural flags, step names, **IA-Slot Defined Labels**, **Preset MAP Labels** (1–20), initial IA-slot ON-states, and the **Command-Programming table** (`Function · MIDI device · Cmd · CC#/PC# · Data` — the MIDI column resolves the channel to its device name) |
| **IA-Slot** | switch type, sync device & effect, group, preset label, on/off/bypass/blocked colours, On- and Bypass-command tables (same `[func,b1,b2,b3]` format as presets, side by side), step toggles |
| **IA-Maps** | the 60-cell button → IA-slot map (name pickers, 6×10) |
| **Pages** | graphical footswitch pedalboard + page-group navigator; each button's Function-1 / Function-2 is a **Type + Value** picker (Empty / Preset / Function / IA Slot / Page Select, items listed by name) + page parameters |
| **Songs** | name/nick, trigger type, **MTC** (enable + Hr/Min/Sec/Frame), the 24-slot **preset list** (name pickers), and **LCD Button Labels** (1–12) |
| **Set-List** | name/nick, number of songs, end-of-list cycle, and the 60-slot **song list** — each slot a name picker |
| **Midi/Groups** | the 16 MIDI-channel device names (the per-channel BANK +1/send/msb grids, 16-bit Max Pre, Grouped-IA order + Exclusive Groups are on the Global tab — they live in a different record) |
| **Colors** | all 24 function- and preset-button colour assignments |
| **Sysex Msgs** | the 16 sysex data cells (with HEX/DEC read-outs), Pre/Post message links, and an Auto-Create MMC generator |
| **Global** | power-up, guitar-tuner & tap-tempo, Sysex ID, MIDI channel, Physical-Btn start, 2nd-func hold time, scroll delay, external-device override, preset-button colours, Exclusive Groups, the full per-channel MIDI device config (BANK +1/send/msb grids + 16-bit Max Pre), Grouped-IA processing order, and the LCD/MIDI behaviour toggles |
| **Exp Pedals** | per-pedal type, CC#, MIDI channel, auto-calibrate, block-reset, force-zipper, CC-sweep min/max, toe/heel trigger, sensitivity, Blk-Heel/Toe Sens, Hi-Res Mode — all 4 pedals. **Live Calibrate…** (when connected) shows live treadle bars; sweep each pedal heel→toe and Save Calibration writes the captured min/max to the device (see [Live pedal calibration](#live-pedal-calibration)) |

**Hover help:** hold the pointer over any control to see the **original LF+ Editor's exact
explanation** — the same tooltips the old software showed, recovered verbatim and mapped 1:1 to our
controls (131 across Presets, Set-List, IA-Slot, Songs, Sysex, Exp Pedals, Global, Colours, Pages
and Midi/Groups; the Global/IA-Slot/Pages/Colours mappings were confirmed by hovering the original
side-by-side). The full text shows on any part of a control, including its toggle switch. Controls
that had no tooltip in the original stay blank here too, so nothing is invented. (The full extracted
set is in [docs/LF_TOOLTIPS.md](docs/LF_TOOLTIPS.md).)

Toggling **Settings → Show raw bytes** adds a **Raw decoded values** table beneath the editors
(off by default). With the data model now fully mapped, this mostly covers confirmed-reserved tail
bytes — it stays as a safety net so nothing is ever hidden, and edits there remain lossless.

## Talking to hardware

The toolbar's **Connect / From LF+ / To LF+** buttons drive the device over USB-serial (protocol
confirmed on a real Liquid Foot+ — see [docs/LF_USB_DIRECT.md](docs/LF_USB_DIRECT.md)):

1. **Connect** — opens the FTDI serial port and handshakes the device into *Editor Mode* (its LCD
   shows "Editor Mode [sel] to exit"). The status bar turns green.
2. **From LF+** — pulls the device's live records (presets + ext/song/sysex/config/IA-map) and
   **overlays them onto the backup you have open** (Song/Set-List/Page/IA-Slot aren't exposed over
   USB, so those stay as loaded from the file). Save a `.syx` afterwards to keep the pull.
3. **To LF+** — writes **every record you've edited** since the last Open or From LF+ (it tracks
   changes per record), after a confirm that lists what will be written. Each write is **surgical**
   and the device acknowledges it (`F0 09 F7`). Writable types are the ones the device can read back
   (Preset, Sysex Msg, IA-Map, and the Global/Config-backed tabs); Song/Set-List/Page/IA-Slot are
   blocked over USB (edit them offline). Device I/O runs on a background thread, so the window stays
   responsive (the status dot turns amber while it works).

> **Disconnect** sends the *leave Editor Mode* command (`CC`) and closes the port, so the unit's
> LCD returns to normal on its own — just like the official editor's CONNECT toggle. (The physical
> [sel] is only needed if a session is interrupted without a clean disconnect.) Don't reconnect too
> fast, and the link never drops DTR mid-session (doing so wedges the device).
>
> Writing to hardware is **off unless explicitly enabled** and always confirmed in the UI. The
> device also speaks MIDI sysex (DIN/USB-MIDI) — that transport is built — but it presents as
> USB-serial here.

### USB MIDI Bridge

**Hardware → USB MIDI Bridge…** turns the editor cable into a **bidirectional** live MIDI
connection (hardware-confirmed `C9 → CA → CF` handshake). It temporarily disconnects Editor Mode
and opens two virtual ports — **LF+ IN PORT** (computer → LF+: Program/Control Changes plus
Clock/Start/Continue/Stop, needs the device global **Allow MIDI in = YES**) and **LF+ OUT PORT**
(LF+ → computer: the controller's own channel MIDI, republished live). On Windows, where
python-rtmidi can't create virtual ports, pick two distinct existing loopback endpoints instead.
Stop the bridge (or reconnect the editor) to send `CC` and return the link to normal record
transfers. Full sequence and filtering details: [docs/DESKTOP_GUIDE.md — Bidirectional MIDI over
the editor cable](docs/DESKTOP_GUIDE.md#bidirectional-midi-over-the-editor-cable-usb-midi-bridge).

### Live pedal calibration

With the device connected, **Exp Pedals → Live Calibrate…** opens the live treadle view (the same
"Live View" the original editor has). The device streams each pedal's raw position in real time, so
each bar tracks the treadle and a red mark records the swept range.

1. Sweep each pedal you want to calibrate fully **heel → toe** so the bar captures its true range.
2. **Save Calibration** writes the swept min/max back to the device. (Only pedals you actually swept
   are written; the rest keep their stored calibration.)
3. Sweep more pedals and save again as needed, then **Close**.

This save uses the device's live-view write path — exactly the sequence the original editor uses,
captured from real hardware: the calibration is written **during** the live stream (it does not stop
the stream first), and the device acknowledges it. After saving you'll see *"Calibration written to
the device."*

> **Known device quirk:** right after a calibration save the unit may not respond to a software
> **Disconnect** — press the physical **[sel]** button to leave Editor Mode instead. This is the
> device's own firmware behaviour: **the original FAMC editor does the same thing** after a
> calibration save, so it is not a fault in this rebuild. A normal session (no calibration save)
> disconnects cleanly from the toolbar.

## For contributors: mapping more fields

Deeper field offsets are pinned with `scripts/diff_dumps.py`: change **one** control in the real
LF+ Editor, re-export a backup, and diff it against the previous export — the changed byte is the
field. Add the offset to the relevant `lfeditor/model/*.py` and a widget spec in
`lfeditor/ui/specs.py`. The full map lives in [docs/LF_DATA_MODEL.md](docs/LF_DATA_MODEL.md) and
[docs/LF_PROTOCOL.md](docs/LF_PROTOCOL.md).

A few shared helpers keep the field editors DRY — reuse them rather than re-implementing:
`lfeditor/text.py` (`decode_ascii` / `encode_ascii`) handles every fixed-width, space-padded
name/label; `lfeditor/model/config.py::channel_names(dump)` resolves the 16 MIDI-channel device
names; and `lfeditor/ui/dnd.py::RecordDropTarget` is the mixin for any widget that should accept a
dragged Find/Q-LIST record (declare `_accepts` and `_handle_drop`, no event boilerplate).
