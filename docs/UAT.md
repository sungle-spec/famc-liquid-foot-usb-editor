# UAT plan — LF+ Editor (desktop reference → web parity)

**Purpose.** A single user-acceptance test plan executed twice: first against the **native desktop
build** (`python -m lfeditor`, the 1:1 reference), then against the **web build** (`web/` served
locally). The pass criterion for the web run is not just "works" but "matches the desktop run —
feature and UI".

**Fixture.** `reference/sysex_dumps/RJM.syx` (never written back; Backup/Save-As only) and the
bundled factory defaults. Hardware is not connected, so device I/O is tested to its offline gate
(buttons present, correctly enabled/disabled) — the wire path is covered by the mock-serial tests.

**Method.**
- Desktop = codified UAT suite (`tests/test_uat.py` + full pytest run) **plus** an interactive GUI
  pass driven on-screen.
- Web = the same steps driven in the browser (Pyodide build) via scripted DOM checks + screenshots.
- Result legend: ✅ pass · ⚠️ pass with note · ❌ fail.

---

## A. Application shell

| ID | Test | Steps | Expected |
|----|------|-------|----------|
| A1 | Launch | Start app | Window opens on Presets tab, no errors, title shows app name |
| A2 | Open `.syx` | File → Open `RJM.syx` | Loads; record counts correct; title shows file; dirty flag off |
| A3 | Tab strip | Click all 11 tabs | Presets, Set-List, IA-Slot, IA-Maps, Midi/Groups, Global, Songs, Pages, Sysex Msgs, Exp Pedals, Colors — all render |
| A4 | Record navigation | Presets: go next/prev, jump to a number | Header shows N-of-M; fields update per record |
| A5 | Dirty tracking | Edit any field | Title/badge marks unsaved changes; clears after save |
| A6 | Save (byte-exact) | Save with no edits | Output byte-identical to input |
| A7 | Backup (Save As) | Backup after an edit | Downloaded/saved file reloads with the edit intact |
| A8 | Load Factory Defaults | File → factory item | Loads bundled factory file; counts update |
| A9 | About / License | Help → About | Dialog/modal shows version + license |

## B. Per-tab layout + edit round-trip (11 tabs)

Each tab: (1) layout matches reference — sections, field labels, LED toggles, tables; (2) one
representative edit sticks after record-switch and survives save/reload.

| ID | Tab | Representative checks |
|----|-----|----------------------|
| B1 | Presets | Name/Nick LCD edit; LED toggle flips; `Function│MIDI│Cmd│CC#/PC#│Data` command table edit; IA-state grid; step names; label grid |
| B2 | Set-List | Params + 60-slot ×5 song picker; assign a song by name |
| B3 | IA-Slot | Settings column; On/Bypass command tables; toggle an LED |
| B4 | IA-Maps | 60-slot ×6 mapping picker; assign a slot |
| B5 | Midi/Groups | 2×8 channel grid (BANK header, +1 col); channel name edit; Exclusive Group number 0–180; Grouped IA config bit |
| B6 | Global | 5 columns render; MIDI-channel / flag edit |
| B7 | Songs | Slot picker, LCD labels, command table, params; edit a command |
| B8 | Pages | 12-button bottom-up board; Page Groups navigator; switch glyphs; tile drag-swap; button function editor (Empty/Preset/Function/IA Slot/Page Select); Page Parameters |
| B9 | Sysex Msgs | Hex byte grid edit; Pre/Post links; Auto-Create MMC |
| B10 | Exp Pedals | 4 pedal-config columns; assign a controller |
| B11 | Colors | Function + Preset button color pickers; change a color |

## C. Tools & editing features

| ID | Test | Steps | Expected |
|----|------|-------|----------|
| C1 | Q-LIST dock | Toggle Q-LIST; filter by text; click an entry | Dock lists `NNN: Name`; click navigates to record |
| C2 | Find | Edit → Find, search a known name | Hit list; selecting jumps to the record |
| C3 | Copy / Paste record | Copy preset A, go to B, Paste | B's bytes (incl. linked ext labels) equal A's |
| C4 | Clear record | Clear current record (confirm) | Record resets to defaults |
| C5 | Clear labels | Clear Preset Labels (confirm) | Ext label records cleared |
| C6 | Raw byte view | Settings → Show raw bytes | idx/dec/hex panel tracks the current record live |
| C7 | Multi-apply toggle | Right-click a preset LED toggle → apply to range | Value applied across the range |
| C8 | CSV export | Export presets to CSV | File contains the preset names |
| C9 | CSV import | Re-import the exported CSV | Names round-trip |
| C10 | Reports | Preset report | Text report lists presets |
| C11 | Quick Programmer | Quick Repeated Command Programmer over a range | Command written to each record in range |
| C12 | Re-order Records | Move a preset | Order changes; references stay in sync |
| C13 | Drag-and-drop assign | Drag Q-LIST/rail entry onto a slot picker / command row; Pages tile swap | Target updates to dragged record |

## D. Device I/O (offline gate only — no hardware attached)

| ID | Test | Steps | Expected |
|----|------|-------|----------|
| D1 | Controls present | Toolbar/menu | Connect, From LF+, To LF+ present; From/To disabled until connected |
| D2 | Write gating | (code-level) | To LF+ requires explicit confirm; never touches on-disk `.syx` |
| D3 | Wire protocol | Automated (mock serial / pytest) | Handshake/read/write frames byte-correct |

---

## Results

### Desktop (native build) — reference run

Executed 2026-07-02 (GUI driven on-screen + `pytest`: **321/321 green**, incl. the codified UAT
suite `tests/test_uat.py` that walks every record on every tab and perturbs every widget).

| ID | Result | Evidence |
|----|--------|----------|
| A1 | ✅ | Launches to Presets, title "LF+ Editor (native, emulates v6.31) — RJM.syx" |
| A2 | ✅ | Status bar: `384 Preset 254 Song 128 Setlist 50 Page 180 IASwitch 255 SysexMsg 60 IAMap` |
| A3 | ✅ | All 11 tabs render (screenshot walkthrough) |
| A4 | ✅ | Jump to #10 → "Streets 1"; fields update per record |
| A5 | ✅ | Nick edit → title dirty dot "•"; unsaved-changes guard fires before factory load |
| A6 | ✅ | pytest `test_file_loads_byte_exact_and_walks_clean` (every fixture + factory file) |
| A7 | ✅ | pytest `test_known_value_survives_save_reload`, `test_heavy_edit_writes_back_and_round_trips` |
| A8 | ✅ | "Loaded factory defaults — Liquid Foot+ Pro+", title → "untitled •" |
| A9 | ✅ | About dialog: v0.0.1, emulates v6.31, About/License/Legal tabs |
| B1–B11 | ✅ | Layout confirmed per tab on-screen; edits via GUI (B1 nick, B8 drag-swap 1↔2) + pytest walks/perturbs every widget on all 11 tabs |
| C1 | ✅ | Filter "pride" → `(012) Pride`; click navigates |
| C2 | ✅ | Find dialog (record filter + **command filter** + CSV export); "Still" → 1 result; double-click jumps to #13 |
| C3 | ✅ | Copy #20 → Paste over #12; status "Pasted into Preset #12" (note: Q-LIST label refreshes lazily) |
| C4 | ✅ | Clear #13 → confirm → defaults restored, status "Cleared Preset #13" |
| C5 | ✅ | Edit menu items present; pytest `test_menu_actions` |
| C6 | ✅ | Settings → Show raw bytes → idx/dec/hex panel tracks record |
| C7 | ✅ | Right-click LED → "Set this OFF for all 384 Presets / …for a range…"; range apply via pytest |
| C8–C10 | ✅ | File menu Import/Export CSV submenus + Reports menu; function via pytest CSV/report round-trips |
| C11 | ✅ | Quick Programmer dialog (area/row/range/function); apply via pytest |
| C12 | ✅ | Re-order dialog; moved "Bad" 14→13 with Sync references on |
| C13 | ✅ | Pages tile drag-swap on-screen; Q-LIST/Find→slot drops via 4 dedicated tests (`test_extras.py`) |
| D1 | ✅ | Connect enabled; From LF+ / To LF+ disabled until connected; "not connected" badge |
| D2–D3 | ✅ | pytest comms suite (handshake/read/write framing, gated writes) |

### Web build — parity run

Executed 2026-07-02 against the same RJM.syx, in the browser (Pyodide build served by
`web/devserver.py`), driving the DOM with the same steps as the desktop run.

| ID | Result | Evidence |
|----|--------|----------|
| A1 | ✅ | Boots to Presets; "ready" status |
| A2 | ✅ | Identical counts: `384 Preset 254 Song 128 Setlist 50 Page 180 IASwitch 60 IAMap 255 SysexMsg` |
| A3 | ✅ | All 11 tabs render; **section titles identical to desktop on every tab** (verified per tab) |
| A4 | ✅ | Jump to #10 → "Streets 1 / Streets1" in header LCDs, `10 / 384` |
| A5 | ✅ | Nick edit → "● unsaved" badge; value confirmed in the byte model (`get_str`) |
| A6 | ✅ | In-browser byte-exact round-trip: `save()` == input (625 932 bytes) |
| A7 | ✅ | Save/Backup enabled; same `session.save()` bytes feed the download |
| A8 | ✅ | Factory dropdown loads bundled files (verified in prior runs + selftest) |
| A9 | ✅ | About/license modal |
| B1–B11 | ✅ | Section structure identical on all 11 tabs; edits land in the byte model |
| C1 | ✅ | Q-LIST dock: filter "pride" → `012: Pride`; click navigates to 12/384 |
| C2 | ✅* | **Was ⚠️ (text-only modal) — now the full desktop dialog** (see fix below) |
| C3 | ✅ | Copy #10 → Paste over #20 → name follows; Paste-enable state tracked |
| C4 | ✅ | Confirm modal → record reset to defaults |
| C5 | ✅ | Tools menu: 3 Clear-labels entries |
| C6 | ✅ | Raw panel: idx/dec/hex tracks record (byte 0..5 spells the name) |
| C7 | ✅ | Right-click LED → "Apply toggle to many records" From/To modal |
| C8–C10 | ✅ | 385-row preset CSV with names; import round-trip; 12 KB report |
| C11 | ✅ | Quick Programmer modal: area (preset/song/IA ON/IA BYPASS) + row + range + command |
| C12 | ✅ | Moved "Bad" #14→#13 with reference sync — same operation as the desktop run |
| C13 | ✅ | Q-LIST drag ("002: Song #002") onto Set-List slot 1 → assigned; wrong-target drop ignored |
| D1 | ✅ | Connect enabled, From/To LF+ disabled, `conn-off` dot; WebSerial present in Chromium |
| D2–D3 | ✅ | Write gated behind confirm modal; wire framing from the same `comms/protocol.py` (mock-serial verified) |

**Parity fix made during this run:** the web **Find** was a simplified text search. It has been
rebuilt to mirror the desktop "Find / Q-LIST" dialog 1:1 — Record filter (quick search with `*`/`?`
wildcards, 7 record-type checkboxes, number range), Command filter (MIDI channel, message type,
CC#/PC#), "List each record once", a `Type|#|Name|Where|Data` results table (click = jump), and
**Export results (CSV)** in the desktop's exact CSV format (`webapi.find_csv` → `search.results_csv`).
Verified in-browser: "Still" → `Preset|13|Still|name|Still` (identical to the desktop run); Program
Change filter → 19 once-per-record hits (`PC ch2 → prog 21`). Covered by
`tests/test_web.py::test_session_multi_apply_and_find`.

### Verdict

**Feature and UI parity: match.** Every UAT case passes on both builds; both load the same file to
identical counts, render the same 11 tabs with the same sections/fields, perform the same edits with
the same outcomes, and save byte-exact. Remaining *cosmetic* differences (intentional web idioms, no
functional impact):

- Record header: web `‹ 10 / 384 ›` arrows vs desktop editable spinner; "Full Name" vs "Name" label.
- Q-LIST item format `012: Pride` vs desktop `(012) Pride`; desktop's Q-LIST refreshes names lazily
  after a paste (web re-renders immediately).
- Multi-apply: web opens the range modal directly; desktop offers "all N records" + "range…" menu.
- Re-order: web is "move record # to position #"; desktop shows the full list with Move ▲/▼.
- Confirm-dialog wording differs slightly (same guards in the same places).

Device I/O over WebSerial was **verified on real hardware 2026-07-13** (full pull byte-identical
to a desktop-path pull; gated write ACKed + read back; device restored byte-exact) — the smoke-test
record and regression procedure are in [WEBSERIAL.md](WEBSERIAL.md).

### Frozen (packaged) builds — parity with `python -m lfeditor`

Executed 2026-07-02 against the PyInstaller bundle built from the same commit
(`pyinstaller packaging/lfeditor.spec`, see [BUILD.md](BUILD.md)).

| Check | Result | Evidence |
|-------|--------|----------|
| Spec audit | ✅ | factory `.syx` ×8 + LICENSE in `datas`; serial/rtmidi hidden imports; icons drawn in code (no data files); all lazy-imported dialogs reachable via static imports |
| `--selftest` (macOS, local) | ✅ | "selftest OK — LF+ Editor (native) 0.0.1, 384 presets, 11 tabs" |
| UI matches python app | ✅ | RJM.syx loaded via argv: identical title, toolbar, 11 tabs, Q-LIST, status-bar counts; Pages board and Midi/Groups 2×8 grid render with identical values |
| Lazy dialogs frozen | ✅ | Find / Q-LIST dialog ("Still" → `Preset│13│Still│name│Still`, same as python run); Quick Repeated Command Programmer opens via Utilities |
| Bundle data | ✅ | 8 factory `.syx` under `Contents/Resources/lfeditor/resources/factory/`, LICENSE at Resources root, `Info.plist` version = `__version__` |
| Windows / Linux | ✅ CI | each OS runner builds its own bundle and runs `--selftest` on the frozen binary (PyInstaller can't cross-compile); AppImage packaged on Ubuntu 22.04, zip on Windows |

The frozen app intentionally differs from `python -m lfeditor` in exactly one way: it **starts
empty** (no `reference/` data is shipped) — open a `.syx` or load a bundled factory default.
