"""What each programming-command function does — hover help for the Command Programming tables.

Short descriptions written for this editor, informed by the original LF+ Editor's own per-function
help (its `Func_Types_Help` table). Keyed by function code (see `preset.CMD_FUNCS`). Qt-free so the
web editor gets the same text through the schema. A code with no entry simply has no hover help.
"""
from __future__ import annotations

_SNAPSHOT = ("Store or restore a snapshot of the LF+'s running state (mode, preset, song…) — for "
             "live use. The original editor names this pair \"System SnapShot Store\" and "
             "\"System SnapShot Restore\"; which of the two codes is which is not yet confirmed.")

CMD_FUNC_HELP: dict[int, str] = {
    0: "Does nothing, and stops processing: commands after an Empty row are not run.",
    1: "Send a MIDI message (Program Change, Control Change, note, pitch bend…).",
    2: "Turn on the LF+ guitar tuner (Kemper, or Axe-Fx before the III). With a valid CC# it also "
       "switches the effects unit's own tuner on.",
    3: "Marks where a step starts; the commands that follow belong to that step. Up to 4 steps per "
       "command block (Preset or IA-Slot).",
    4: "Send one of the stored Sysex messages.",
    5: "Pause processing for a time in milliseconds.",
    6: "Jump back to the preset used before the current one.",
    7: "Jump back to the page used before the current one.",
    8: "Change to the given Page.",
    9: "Jump to a specific preset.",
    10: "Send the ON programming of the given IA-Slot.",
    11: "Send the BYPASS (off) programming of the given IA-Slot.",
    12: "Toggle the given IA-Slot's state, then send its programming.",
    13: "Set the button colour for the current Preset / IA-Slot. The value is a colour number.",
    14: "Remember the current preset, so \"Preset Recall Stored\" can return to it.",
    15: "Jump to the preset remembered by \"Preset Store\".",
    16: "Jump to the first preset of the bank in use and trigger it.",
    18: "Change the CC# an expression pedal sends — e.g. switch one pedal between volume and wah.",
    19: "Force a specific value (0–127) to be sent, using the pedal's current programming.",
    20: "Send the expression pedal's current value again.",
    21: "Resend the current state of the given IA-Slot.",
    22: "Change the MIDI # an expression pedal transmits on.",
    23: _SNAPSHOT,
    24: _SNAPSHOT,
    25: "Change which IA-Slot an expression pedal triggers (the pedal must be an IA-trigger or "
        "IA-toggle type).",
    26: "Temporarily force the IA-Slot's button (if active) to a given colour. Useful with steps.",
    27: "Enter MIDI Time Code mode until cancelled (if the current song has MTC defined).",
    28: "Change the colour of the Status #1 LED. The value is a colour number.",
    29: "Automatically tap an IA-Slot's ON message (twice, unless set to 3 or 4 taps) at a given "
        "delay in milliseconds.",
    30: "Reset the current preset's IA-Slots to their initial states and resend them.",
    31: "Remember the song in use, so \"Song # Recall Stored\" can return to it.",
    32: "Jump to the song remembered by \"Song # Store Current\".",
    33: "Change to a specific song.",
    34: "Toggle every page button between its function #1 and function #2 immediately.",
    35: "Give an expression pedal a second MIDI channel to transmit on.",
    36: "Give an expression pedal a second CC# to transmit.",
    37: "Invert the pedal's second slot (full travel sends the minimum) — lets one pedal crossfade "
        "two effects.",
    38: "Ask a sync'd Axe-Fx I/II for its current state.",
    39: "Switch to the given IA-Map immediately.",
    40: "If the given IA-Slot is OFF, stop processing this command block.",
    41: "If the given IA-Slot is ON, stop processing this command block.",
    42: "If the given IA-Slot is OFF, skip the following commands up to the next IF… command.",
    43: "If the given IA-Slot is ON, skip the following commands up to the next IF… command.",
    44: "If this block is running for any reason other than the user pressing the button, skip the "
        "following commands up to the next IF… command.",
    45: "Stop processing this command block.",
    46: "Lowest value the expression pedal sends (default 0). Overrides the global setting.",
    47: "Highest value the expression pedal sends (default 127). Overrides the global setting.",
    48: "Sets WHICH button of the current Page appears on physical button #1 of the LF+. The value "
        "is a start index into the Page's buttons (the original editor documents 1–52) — not an "
        "on/off switch. Use it to show a different group of the Page's buttons on the controller, "
        "e.g. 1 for the first group and 25 for another.",
    49: "Block all page changes until a \"Page UNLOCK current\" command runs.",
    50: "Allow page changes again after a \"Page LOCK to current\".",
    51: "Turn on the LF+ looper mode (IA-Slots update automatically). Needs a compatible effects "
        "unit.",
    52: "Turn off the LF+ looper mode.",
    53: "Remove the expression pedal's second-slot programming.",
    54: "Change to the default Page of the currently active preset.",
    55: "Make the preset momentary; when the button is released, jump to a given preset (or a "
        "preset in a song slot).",
    56: "If the IA-Slot is active, switch it to the given step number.",
    57: "Increase the last Program Change number sent, and send it again.",
    58: "Decrease the last Program Change number sent, and send it again.",
    59: "Save the last sent Program Change into the first programming slot — useful after "
        "PC# + / PC# - changed it live.",
    60: "Set the MIDI clock by period: 200–1200 ms. Out of range turns the MIDI clock off.",
    61: "Set the MIDI clock in beats per minute: 50–255 BPM. Out of range turns the MIDI clock off.",
    62: "Set a specific IA-Slot to OFF, ON or BYPASS and trigger it.",
    63: "Resend the current state of a specific IA-Slot.",
    64: "Block the expression pedal port's transmission until it is unblocked.",
    65: "Unblock an expression pedal port blocked by \"EXPR Block Xmit\".",
    66: "Axe-Fx III: change an effect's channel, or its bypass state.",
    67: "Axe-Fx III: change to a specific scene.",
}


def func_help(code: int) -> str:
    return CMD_FUNC_HELP.get(code, "")
