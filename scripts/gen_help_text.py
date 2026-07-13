#!/usr/bin/env python3
"""
Generate lfeditor/ui/help_text.py from the curated maps + the extracted tooltips.

Curation is by a **distinctive tooltip substring** (not control id): the original's generic
control names — Label1/Label2/TextField1 — are reused across windows and ambiguous, and the
tooltip text is what the user actually sees. Maps are keyed **per tab** because generic field
labels (Type, CC#, Chan, Mode, Page…) recur across tabs with different meanings. Each entry maps
one of our field labels (or section titles) to a unique fragment of the desired tooltip; the
generator resolves it to the full verbatim text (from scripts/ARTIFACTS/lf_tooltips.json) and
errors if a fragment is missing or matches more than one distinct tooltip.

    python3 scripts/gen_help_text.py
"""
import json, pathlib, sys

JSON = pathlib.Path("scripts/ARTIFACTS/lf_tooltips.json")
OUT = pathlib.Path("lfeditor/ui/help_text.py")


def norm(s: str) -> str:
    return " ".join(s.split())


# tab title -> { our field label (or toggle caption) -> distinctive tooltip fragment }
FIELD_MAP: dict[str, dict[str, str]] = {
    "Preset": {
        "Default page": "Page to Load when Preset is activated",
        "IA-slot map": "IA-Map to use for the page used by this preset",
        "Resend IA-slot states": "send all IA-Slot commands (either ON or BYPASS) based on the initial states defined for this Preset",
        "Resend globals": "based on the current global state of that particular IA-Slot",
        "Replace global IAs w/ initial states": "replace the current state of all global IA-Slots with the values defined in the Initial States",
        "Act as IA-Slot (vs Preset)": "make the preset act like an IA-Slot is being pressed",
        "Allow multi-presses (process steps/reset)": "If you want this preset to allow multiple presses",
        "Reset button: non-preset function": "reset all Page button functions to the default function #1",
        "Reset button: preset function": "currently set for Function #2 active back to Function #1",
        "Process preset commands after IAs": "allow IA-Slots to process first, and then preset commands",
        "Sync preset name (IN)": "the Preset name will override and use the external devices current preset name",
        "Send as [bypass] for initial BLOCKED": "Blocked IA's will initially trigger BYPASSED commands",
        "Block exp pedal #1 until assigned": "Expression Pedals will remain in current state of programming",
        "Block exp pedal #2 until assigned": "Expression Pedals will remain in current state of programming",
        "Block exp pedal #3 until assigned": "Expression Pedals will remain in current state of programming",
        "Block exp pedal #4 until assigned": "Expression Pedals will remain in current state of programming",
        "Step 1": "Nick Name for Step #1",
        "Step 2": "Nick Name for Step #2",
        "Step 3": "Nick Name for Step #3",
        "Step 4": "Nick Name for Step #4",
    },
    "Set-List": {
        "Last Song Slot Used": "tell this set-list which Song Slot is the last used Song",
        "End of List Cycle Type": "Defines Type of Cycle when Song UP is pressed at the end of the set-list",
    },
    "IA-Slot": {
        "Switch type": "Defines the behavior of the IA-Slot",
        "Enabled": "Set to ON if this IA-Slot will be a global IA",
        "On colour": "active on a button and in the ON state",
        "Off colour": "active on a button and in the OFF state",
        "Bypass colour": "active on a button and in the BYPASS state",
        "Blocked colour": "active on a button and in the BLOCKED state",
        "Group ID": "Defines the Group this IA-Slot will be a part of",
        "Preset label": "can be assigned to IA-Slots using the Label Parameter",
        "Sync device": "Connect this IA-Slot to an external device that is Real-Time Sync compatible",
        "Sync effect": "Effect within a Sync'd device to connect to this IA-Slot",
        "Remember last step state": "remember the last step used before last power down. This IA will continue",
        "Force step #1 on preset change": "force the LF+ to process STEP #1 as soon as a preset is triggered",
    },
    "Song": {
        "Enable MTC Mode": "Enable MTC control as dedicated mode when using this SONG",
    },
    "Sysex Msg": {
        "Pre Sysex Link": "send the sysex message in this link prior to sending this current sysex message",
        "Post Sysex Link": "this link after this current sysex message is finished sending",
    },
    "Expression Pedals": {
        "Type": "Define the Type of Pedal Function for this expression pedal port",
        "CC#": "Either the CC#, IA-Slot# or Button # based on Expression Pedal Type",
        "Chan": "MIDI Chan used to transmit CC related expression pedal values",
        "Auto-calibrate": "calibrate upon power-up after the pedal",
        "Block reset": "all Expression Pedal Programming Parameters default back to Global Settings",
        "Force-zipper": "require sequential sweeps during changes to sound proper",
        "CC sweep min": "Min value when in heel position",
        "CC sweep max": "Max value when in toe position",
        "Toe trigger (0=none)": "IA Slot to Trigger when entering full TOE position",
        "Heel trigger (0=none)": "IA Slot to Trigger when entering full HEEL position",
        "Sensitivity": "pedals that have semiaccurate POT's installed",
        "Blk Heel/Toe Sens": "process all changes when between 0/1 and 126/127 midi values",
        "Hi-Res Mode": "process the pedal with twice the accuracy",
    },
    "Global Settings": {
        "Save sync preset name": "save the Preset Name loaded from an external device",
        "Save sync IA states": "save the Current IA-States from the external Sync into the current preset",
        "Tap Light ON Time": "Tap Tempo Status Light Blink Time",
        "Sync taps to MIDI Clock IN": "allow the tempo to sync to the timing derived from the midi clock IN data",
        "IA-Slot toggle (tap tempo)": "Tap Tempo IA-Slots (and Auto-tap commands) will toggle between ON/BYPASS",
        "MIDI Thru": "Allow incoming Data to be sent to the MIDI-OUT port",
        "Sysex device ID": "Sysex ID. Default is 124",
        "Expander via MIDI CHAN": "act like an expander for Page button",
        "Hub connection": "Hub device is to be used for Phantom Power",
        "Reverse main display lines": "swap what is displayed on lines #1 and #2",
        "Show 2nd function name": "button LCD screens will show info about the current active function on the button",
        "Show bypass as OFF on button": "IA-Slots in the Bypass State will show whatever is defined for the OFF state",
        "Clear button LCD when off": "Button LCD will display nothing when an IA-Slot is OFF and active for the button",
        "Bank change": "reset to original order when a Bank Change button is pressed",
        "Song/Set change": "reset to original order when a Song or Set-List Change button is pressed",
        "Page change": "reset to their original programmed order when a Page Change button is pressed",
        "Force 2nd function ASAP": "automatically trigger the 2nd function and DO NOT wait",
        # --- added via live hover-verification pass on the original editor ---
        "[OFF] IA's send [BYPASS] commands": "send IA-Slot programming Bypass commands when IA-Slot is in the OFF state",
        "Force IA Cmd send with Presets": "Will Resend IA-Slot initial States upon any preset change",
        "Block Multiple Preset Presses": "stop you from pressing the same Preset more then once",
        "Block Boot-Up MIDI Transmission": "will not transmit the intial song, preset and IA-Slot Initial States during start up",
        "Mode": "power-up in whatever the last used mode was",
        "Page": "Page the LF+ will default to upon POWER-UP",
        "Preset (0=ignore)": "power-up using whatever the last used Preset was",
        "Song (0=ignore)": "power-up with the last used Song",
        "Set-List (0=ignore)": "power-up with the last used Setlist",
        "Guitar tuner": "Guitar Tuner Source",
        "Blink display": "block the LF+ from changing all button LCD colors to GREEN when the Guitar is in TUNE",
        "Auto start": "If an external device enters Tuner on its own",
        "Name Src": "External Sync device used to sync Preset Name, Scene Name",
        "Ext. Model": "DO NOT use this unless problems exist with a sync device not being detected",
        "Source": "Guitar Tap-Tempo Beat Source",
        "Button": "No blink: USE Status Light only if source is selected",
        "Auto-Tap-Msgs": "this parameter will determine how many Taps of the IA-Slot will be generated",
        "MIDI Clock Out enable": "the LF+ will process Auto-Tap-Tempo and MIDI Clock programming commands",
        "Show / send MIDI Clock OUT": "transmit in real-time to the MIDI CLOCK output",
        "Allow MIDI in": "process incoming MIDI commands assigned to its MIDI channel. Otherwise",
        "MIDI channel": "MIDI channel assigned to this LF+. It will use this MIDI channel to receive acceptable commands",
        "Physical/Page Btn start": "button # of the active page should be triggered on the first physical button",
        "2nd-function hold time": "How long must pass until a 2 function button triggers the second function",
        "Scroll delay": "time in (ms) to wait between button presses",
        "MENU": "Block the MENU B2+B3 combo buttons from entering the Menu System",
        "PAGE": "Block the Page selection button combo sequence",
        "PRESET": "Block the B1 + B5 Preset change button combo sequence",
        "SAVE / COPY": "will not enter Save/Copy mode when a preset is held for 3+ seconds",
        "Line 2 state (UPPER/lower)": "2nd line will show the IA-Slot nick name as all LOWERCASE",
        "IA Display on Main LCD": "IA-Slot names will follow label definitions",
    },
    "Colours": {
        # all 20 function-colour pickers share one tooltip in the original
        **{fn: "color displayed on a button when the cooresponding function is the active function"
           for fn in ("Menu", "Enter / Select", "Change Page", "Context Up", "Context Down",
                      "Preset Up", "Preset Down", "Current Mode", "Bank Up", "Bank Down",
                      "Song Up", "Song Down", "SetList Up", "SetList Down", "Global Page",
                      "Page Up", "Page Down", "Last Preset", "Save Preset", "Last Page")},
        "Preset-btn Func 1 selected": "Color to display when a Preset on Function #1 is currently selected",
        "Preset-btn Func 1 not selected": "Color to display when a Preset on Function #1 is not selected",
        "Preset-btn Func 2 selected": "Color to display when a Preset on Function #2 is currently selected",
        "Preset-btn Func 2 not selected": "Color to display when a Preset on Function #2 is not selected",
    },
    "Pages": {
        "Menu button trigger (0=B2+B3)": "Button #2 + #3 held together turn on the menu system",
        "Force IA map (0=none)": "Pages will not alter the current IA-MAP (as set by presets)",
        "All buttons double-tap": "forces all buttons on this page to allow double-tap button presses",
        "Status #1 LED colour": "Set the Color of Status Led #1 when this page is active",
        "Enable Double-Tap": "current button will allow double-tap functionality to switch between Function #1 and Function #2",
        "Function-1 Trigger Scrolls": "BANK, PRESET, PAGE, SONG, SET-LIST UP or DOWN event was pressed prior",
        "Function-2 Trigger Scrolls": "BANK, PRESET, PAGE, SONG, SET-LIST UP or DOWN event was pressed prior",
    },
    "Midi/Groups": {
        "Channel Name": "Enter the name you want to use for the MIDI device set for this channel",
        "send": "the LF+ will handle all bank changes automatically",
        "Max Pre": "Defines the maximum preset # usable by this midi channel",
    },
}

# tab title -> { our Section title -> fragment }  (for label-less sections: grids/tables)
SECTION_MAP: dict[str, dict[str, str]] = {
    "Preset": {
        "IA-Slot Defined Labels": "Use a Preset Defined Label instead of the IA-Slot Nick Name",
    },
    "Midi/Groups": {
        "Exclusive Group Trigger IA's": "Exclusive Post Trigger Group Assignment. By assigning an IA-Slot here",
        "Grouped IA config": "Groups can either send the ON programming of the selected IA-Slot before the BYPASS",
    },
}


def resolve(frag, texts):
    key = norm(frag).lower()
    hits = {t for t in texts if key in t.lower()}
    if len(hits) == 1:
        return next(iter(hits))
    raise KeyError(f"{frag!r}: matched {len(hits)} distinct tooltips")


def build(nested, texts):
    out, bad = {}, []
    for tab, mp in nested.items():
        for label, frag in mp.items():
            try:
                out.setdefault(tab, {})[label] = resolve(frag, texts)
            except KeyError as e:
                bad.append(f"[{tab}] {e}")
    return out, bad


def main():
    rows = json.load(open(JSON))
    texts = {norm(r["tooltip"]) for r in rows}
    fields, bad1 = build(FIELD_MAP, texts)
    sections, bad2 = build(SECTION_MAP, texts)
    if bad1 or bad2:
        print("ERRORS — fix the fragments:")
        for b in bad1 + bad2:
            print("  ", b)
        sys.exit(1)

    def emit(fh, name, data):
        fh.write(f"{name}: dict[str, dict[str, str]] = {{\n")
        for tab, mp in data.items():
            fh.write(f"    {tab!r}: {{\n")
            for label, tip in mp.items():
                fh.write(f"        {label!r}: {tip!r},\n")
            fh.write("    },\n")
        fh.write("}\n\n")

    with open(OUT, "w") as fh:
        fh.write('"""Curated control help text — the original LF+ Editor\'s hover tooltips.\n\n'
                 "The text is FAMC's, recovered verbatim from the original app (see\n"
                 "docs/LF_TOOLTIPS.md and scripts/extract_tooltips.py) and mapped to our controls,\n"
                 "keyed per tab (generic labels like 'Type'/'CC#' recur across tabs). Kept for\n"
                 "interoperability/preservation, like the bundled factory .syx — revisit before any\n"
                 "public release. GENERATED by scripts/gen_help_text.py — edit the maps there.\"\"\"\n\n")
        emit(fh, "FIELD_HELP", fields)
        emit(fh, "SECTION_HELP", sections)
        fh.write("\ndef tooltip_for(tab: str, label: str) -> str:\n")
        fh.write('    """Curated hover text for a field label/caption on `tab`, or "" if none."""\n')
        fh.write("    return FIELD_HELP.get(tab, {}).get((label or '').strip(), '')\n\n\n")
        fh.write("def section_tooltip(tab: str, title: str) -> str:\n")
        fh.write('    """Curated hover text for a section panel title on `tab`, or "" if none."""\n')
        fh.write("    return SECTION_HELP.get(tab, {}).get((title or '').strip(), '')\n")

    nf = sum(len(v) for v in fields.values())
    ns = sum(len(v) for v in sections.values())
    print(f"wrote {OUT}: {nf} field tooltips across {len(fields)} tabs, {ns} section tooltips")


if __name__ == "__main__":
    main()
