# UAT — USB MIDI Bridge Setup Wizard (Windows), v0.0.11

**Purpose.** Windows is the one platform the bridge/wizard logic can't be exercised on from the
dev machine (macOS) — real hardware, a real loopback MIDI driver, and the WinMM-specific port
naming behavior all only exist on Windows. This plan verifies the Setup wizard and the bridge's
Windows-specific paths on real hardware. macOS/Linux paths and all non-hardware logic are already
covered by the automated suite (`tests/test_midi_bridge.py`, `tests/test_midi_bridge_wizard.py` —
430 tests, all green) and a live desktop pass on macOS; this plan does **not** repeat those.

**Background for context.** A contributor validated the bridge on Windows 11 but had to
reverse-engineer that Windows needs manually-created MIDI loopback ports, and guessed at naming
them to match the macOS convention (`LF+ IN PORT` / `LF+ OUT PORT`). v0.0.10 added a guided Setup
wizard for this. Testing it live surfaced a real bug: python-rtmidi's WinMM backend appends a
numeric index to *every* MIDI port name on Windows (`LF+ IN PORT` is reported as `LF+ IN PORT 0`),
so the wizard's exact-name match never turned green even with correctly-named ports. **v0.0.11**
fixes this (`base_port_name()` in `lfeditor/ui/midi_bridge.py` strips the suffix before
comparing). Test case **W3** below is the direct regression check for that bug — it's the one
that must not fail again.

**Result legend:** ✅ pass · ⚠️ pass with note · ❌ fail.

---

## Prerequisites

1. Windows 10/11 PC.
2. A Liquid Foot+ (or JR+) connected via its USB editor cable, already able to reach Editor Mode
   (FTDI driver present; if the device has never been set up on this machine, run
   **Hardware ▸ Device Connection Setup…** first).
3. **v0.0.11** build:
   [`LFPlusEditor-0.0.11-windows-x64.zip`](https://github.com/sungle-spec/famc-liquid-foot-editor-builds/releases/tag/v0.0.11)
   — unzip and run `LFPlusEditor.exe`. (Or, if running from source: `git pull`, confirm
   `lfeditor/__init__.py` says `0.0.11`, `python -m lfeditor`.)
4. [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) (free) — or any other Windows
   MIDI loopback driver, but loopMIDI is what the wizard names explicitly.
5. Something that can see MIDI traffic on the loopback ports for W11/W12 — a DAW's MIDI
   input/output port selectors, MIDI-OX, or (weaker but zero-setup) loopMIDI's own **Total
   data / Throughput** counters, which tick up when bytes cross a port.

---

## Test cases

| ID | Test | Steps | Expected |
|----|------|-------|----------|
| W1 | Wizard, no loopback ports yet | Don't open loopMIDI. **Hardware ▸ USB MIDI Bridge Setup…** | MIDI-endpoints row: red dot, *"No usable loopback ports found yet — follow the steps below."* Windows instructions block visible (loopMIDI link + naming steps). |
| W2 | loopMIDI ports with generic names | In loopMIDI, `+` twice → name them e.g. `Foo In` / `Foo Out`. Click **Refresh** in the wizard | MIDI-endpoints row: amber dot, *"Loopback ports found, but not named to match — the bridge can still use them if you pick them manually. Rename them to "LF+ IN PORT" / "LF+ OUT PORT" so they're picked automatically."* |
| **W3** | **Recommended names — the regression case** | In loopMIDI, rename the two ports to exactly `LF+ IN PORT` and `LF+ OUT PORT`. Click **Refresh** | MIDI-endpoints row turns **green**: *""LF+ IN PORT" / "LF+ OUT PORT" detected — the bridge will select them automatically."* This must go green even though Windows internally reports them with a numeric suffix (e.g. `LF+ IN PORT 0`) — that's exactly the bug fixed in v0.0.11. |
| W4 | Detected-ports list | With W3's ports in place, look at the port list under the instructions | Lists the actual Windows-reported names (may show a trailing index, e.g. `LF+ IN PORT 0`) — cosmetic only, not a fail. |
| W5 | Device-detected row | With LF+ plugged in vs. unplugged, Refresh each time | Plugged in: green, *"LF+ detected on COM<N>"*. Unplugged: amber, *"LF+ not detected — plug it in (Hardware ▸ Device Connection Setup… enables the serial port id)."* |
| W6 | "Allow MIDI in" row | Load a `.syx` (or connect + From LF+) with the Global "Allow MIDI in" toggle OFF, Refresh; then set it YES (Global tab, To LF+), reconnect/reload, Refresh again | OFF: amber, *""Allow MIDI in" is OFF in the loaded data — DAW → LF+ commands will be ignored until it's set to YES (Global tab, then To LF+)."* YES: green, *""Allow MIDI in" is YES — computer → LF+ control will work."* |
| W7 | Bridge dialog — Windows radio | Open **Hardware ▸ USB MIDI Bridge…** directly (not via wizard) | "Create virtual ports" radio is disabled but reads *"Create virtual ports (not available on Windows)"* — not just greyed out with no explanation. A **Setup…** button sits next to a one-line hint below the port row. |
| W8 | Setup… button → wizard | Click **Setup…** in the bridge dialog | Opens the same Setup wizard (singleton — if already open, it's raised/refreshed, not duplicated). |
| **W9** | **Wizard → bridge handoff + auto-select** | With W3's ports ready, in the wizard click **Open USB MIDI Bridge…** | Wizard closes; bridge dialog opens with **"MIDI to LF+"** already showing the `LF+ IN PORT…` entry and **"MIDI from LF+"** already showing `LF+ OUT PORT…` — no manual picking needed. This is the main point of the whole feature; if it's not auto-selected, that's the bug to report first. |
| W10 | Bridge start | With ports auto-selected (W9) and LF+ plugged in, click **Start** | Button becomes **Stop**; status label shows live counters (`DAW → LF+: 0 · LF+ → DAW: 0`, incrementing as traffic flows); LF+'s own display returns to normal preset/control view (not stuck in a handshake state); physical switches on the unit stay usable. |
| W11 | LF+ → DAW | Bridge running. Watch the `LF+ OUT PORT` side in your DAW/monitor (or loopMIDI's Throughput column for that port). Step on a physical switch on the LF+ | A MIDI message appears / throughput ticks up on `LF+ OUT PORT`; the wizard's counters (`LF+ → DAW`) increment too if you reopen the bridge dialog. |
| W12 | DAW → LF+ | With "Allow MIDI in = YES" (W6), send a Program Change or Control Change from your DAW into `LF+ IN PORT` | LF+ responds (preset/CC action fires); `DAW → LF+` counter increments. |
| W13 | Stop cleanly | Click **Stop** | State returns to `stopped`, with the final counters shown. **Connect** / **From LF+** work normally afterward (bridge doesn't leave the serial port or MIDI endpoints stuck open). |
| W14 | Repeat cycle | Start → Stop → Start → Stop, 2–3 times in a row | No crash, no leaked/duplicate MIDI ports accumulating in loopMIDI's port list, no growing memory/handle usage. |

---

## Results

*(Fill in after running — Result column ✅/⚠️/❌, Evidence = what you actually saw, screenshot
filename, or error text.)*

| ID | Result | Evidence |
|----|--------|----------|
| W1  | | |
| W2  | | |
| W3  | | |
| W4  | | |
| W5  | | |
| W6  | | |
| W7  | | |
| W8  | | |
| W9  | | |
| W10 | | |
| W11 | | |
| W12 | | |
| W13 | | |
| W14 | | |

### Verdict

*(Overall pass/fail once the table above is filled in, plus anything that needs a follow-up fix.)*
