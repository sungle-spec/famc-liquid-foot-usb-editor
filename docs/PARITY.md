# Desktop ↔ Web parity audit

A source-level comparison of the native PySide6 app (`lfeditor/ui/**`) against the web port
(`web/**` + `lfeditor/schema.py` + `lfeditor/webapi.py`). Both render from the **same** Qt-free
field/section specs (`lfeditor/ui/specs.py`, `lfeditor/ui/tabspec.py`) and the **same** byte-exact
codec/model, so the data layer is identical by construction. This doc tracks **UI layout** and
**feature** parity.

Legend: ✅ matches · ⚠️ partial · ❌ not yet ported · 🔌 deferred (needs WebSerial device I/O)

## Per-tab layout + fields (11/11 match)

| # | Tab | Native source | Web | Status |
|---|-----|---------------|-----|--------|
| 1 | Presets | `specs._preset_tab` (SectionedTab) | schema → `renderColumns` | ✅ same sections, fields, LED toggles, `Function│MIDI│Cmd` table, IA-state grid, step names, label grids |
| 2 | Set-List | `specs._setlist_tab` | schema | ✅ params + 60-slot ×5 song picker |
| 3 | IA-Slot | `specs._iaslot_tab` | schema | ✅ settings column + On/Bypass command tables |
| 4 | IA-Maps | `specs._iamap_tab` | schema | ✅ 60-slot ×6 mapping picker |
| 5 | Midi/Groups | `tabs/midi_groups_tab.py` (bespoke) | `renderMidiGroups` | ✅ 2×8 channel grid (BANK-spanning header, +1 col), Exclusive Group 0–180 numbers, Grouped IA config |
| 6 | Global | `specs._global_tab` (GlobalSpec) | schema | ✅ all 5 columns/sections · ⚠️ no "Send/Get Settings" buttons (🔌) |
| 7 | Songs | `specs._songs_tab` | schema | ✅ slot picker + LCD labels + command table + params |
| 8 | Pages | `tabs/pages_tab.py` (bespoke) | `renderPages` | ✅ 12-button bottom-up board, Page Groups navigator, switch glyphs, drag-swap (Shift=copy), Page Parameters + Button Definition |
| 9 | Sysex Msgs | `specs._sysex_tab` | schema | ✅ hex grid + Pre/Post links + Auto-Create MMC |
| 10 | Exp Pedals | `specs._exp_pedals_tab` (GlobalSpec) | schema | ✅ 4 pedal-config columns · ⚠️ no live-calibration strip (🔌) |
| 11 | Colors | `specs._colors_tab` | schema | ✅ 4-col Function Button Colors + Preset Button Colors |

Every `Field` subclass in `fields.py` has a web renderer (`schema.KIND` + `render.js` `buildField`):
name/nick/string, int, int16, flag, toggle, enum (incl. nibble), command_table/midi_table,
bitgrid, bytegrid, int16grid, slotpicker, hexbytes, iastate, labelgrid, mmc, channelname. **No field
kind is dropped.**

The web widgets replicate the native custom-painted controls 1:1 (2026-07-02 pass): the 22×30
vertical **rocker switches** with I/O glyphs (`components.RockerSwitch`), the 34×20 **pill toggles**
in the IA-state table (`ToggleSwitch`), the `IA [#] Name | State` **table** with 20px rows
(`IAStateGridField`), 88px LCD **label grids**, `&hNN` hex cells with blue HEX/DEC read-outs,
GroupBox-style **section panels** (title chip on the border), fixed 252px **Global columns** with
110px inputs, the Pages **board/navigator geometry** (150×84 tiles, 168×74 sky-blue group boxes in a
right-hand column), the native **record header** (title + spinner + Name/Nick + 4 transfer buttons),
and **hover tooltips** on every control from the same curated `ui/help_text.py` the desktop uses
(carried through `lfeditor/schema.py`).

## App-level features

| Feature | Native | Web | Notes |
|---|---|---|---|
| Open `.syx` | ✅ | ✅ | |
| Save / Backup (Save-As) | ✅ | ✅ | both Save + Backup download |
| Load Factory / Special | ✅ | ✅ | factory dropdown |
| Record navigation | ✅ rail + spinner | ✅ ‹ ›/N-of-M + Q-LIST | |
| Name / Nick edit | ✅ | ✅ | |
| Per-record edit, byte-exact save | ✅ | ✅ | verified round-trips |
| Pages drag-to-swap | ✅ | ✅ | |
| **Q-LIST** searchable record dock | ✅ | ✅ | filter by number/name, click to navigate |
| **Find** | ✅ | ✅ | full "Find / Q-LIST" dialog: wildcards, type checkboxes, number range, MIDI-command filter, once-per-record, results table (click = jump), CSV export |
| **Record Copy / Paste** | ✅ | ✅ | reuses `ui/record_ops.py` (incl. linked ext records) |
| **Clear record / labels** | ✅ | ✅ | confirm modal |
| **Raw byte view** toggle | ✅ | ✅ | bottom panel, idx/dec/hex |
| **Multi-apply toggle** (right-click → apply across N records) | ✅ | ✅ | right-click any record-tab LED |
| **CSV import / export** | ✅ | ✅ | reuses `csvio.py`; browser upload/download |
| **Reports** (preset/song/set-list) | ✅ | ✅ | reuses `csvio.report_text`; download |
| **Quick Repeated Command Programmer** | ✅ | ✅ | reuses `quickprog.py` |
| **Re-order Records** | ✅ | ✅ | reuses `reorder.py` (with ref-sync) |
| Drag-drop slot assign (Q-LIST → slot/command) | ✅ | ✅ | Q-LIST items drag onto slot pickers + command rows; Pages tile drag-swap |
| Device I/O: Connect + From/To LF+ | ✅ (USB-serial) | ✅ | WebSerial (`web/serial.js` + `webapi.dev_*`); hardware-verified 2026-07-13, write gated. See [WEBSERIAL.md](WEBSERIAL.md) |
| Device I/O: MIDI Monitor, EEPROM wizard, live-calibration, resets | ✅ | 🔌 | not yet ported to WebSerial |

## Summary

- **Layouts: 11/11 tabs match** the native build pixel-for-pixel (sections, fields, labels, ordering,
  LED toggles, bespoke Pages/Midi-Groups). Editing is byte-exact in both.
- **Functionality: full offline parity.** All of the native app's auxiliary tools — Q-LIST/Find,
  record copy/paste/clear, raw view, multi-apply, CSV import/export, reports, quick-programmer,
  reorder — are now ported to the web. They go through `webapi.py`, reusing the existing pure-Python
  modules (`record_ops`, `csvio`, `search`, `quickprog`, `reorder`) so there is no logic re-write and
  no drift. Q-LIST drag-onto-slot/command and the full Find / Q-LIST dialog (command filter + results
  CSV) are ported too. Both builds passed the same UAT plan — see [UAT.md](UAT.md).
- **Device I/O**: Connect / From-To LF+ work in both (web via WebSerial, hardware-verified
  2026-07-13). The MIDI monitor, EEPROM wizard, and live calibration remain desktop-only.
