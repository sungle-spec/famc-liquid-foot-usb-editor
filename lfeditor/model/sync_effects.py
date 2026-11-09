"""Per-device "Sync effect" tables for IA-Slots (index = the byte stored at iaswitch.SYNC_EFFECT_OFF).

Recovered 2026-11-09 from the original LF+ Editor v6.31 (Mac, unstripped Xojo binary) with REA +
Ghidra: ``Firmware_Effect_Labels.Create_KEMPER_ARRAYS`` / ``Create_AXE_ARRAYS`` /
``Load_AXEFX3_Data``. The same tables are what the original's "Update Internal Data" sends to the
unit (5 devices x 200 slots x [16-char name + 8-char nickname]); see
docs/ORIGINAL_EDITOR_GAP_ANALYSIS.md. Each entry is ``(full_name, nick_name)``.

Validated against the shipped factory templates (tests/test_sync_effects.py): every Kemper and
Axe-Fx III slot's stored effect index resolves to the slot's own name. Axe-Fx II/Ultra uses the
85-entry list (the 84-entry ``Load_AXEFX_Data`` variant lacks index 84 = SCENE 8, which the factory
template uses, and matches fewer slot names).

Device numbers are ``iaswitch.SYNC_DEVICES`` (2 = AXE-FX III, 3 = AXE-FX Ultra/II, 4 = KEMPER KPA).
"""
from __future__ import annotations

AXE3_EFFECTS = (
    ('INPUT 1', 'INPUT 1'),  # 0
    ('INPUT 2', 'INPUT 2'),  # 1
    ('INPUT 3', 'INPUT 3'),  # 2
    ('INPUT 4', 'INPUT 4'),  # 3
    ('INPUT 5/USB', 'IN 5/USB'),  # 4
    ('OUTPUT 1', 'OUTPUT 1'),  # 5
    ('OUTPUT 2', 'OUTPUT 2'),  # 6
    ('OUTPUT 3', 'OUTPUT 3'),  # 7
    ('OUTPUT 4', 'OUTPUT 4'),  # 8
    ('COMPRESSOR 1', 'COMP 1'),  # 9
    ('COMPRESSOR 2', 'COMP 2'),  # 10
    ('COMPRESSOR 3', 'COMP 3'),  # 11
    ('COMPRESSOR 4', 'COMP 4'),  # 12
    ('GRAPH EQ 1', 'G. EQ 1'),  # 13
    ('GRAPH EQ 2', 'G. EQ 2'),  # 14
    ('GRAPH EQ 3', 'G. EQ 3'),  # 15
    ('GRAPH EQ 4', 'G. EQ 4'),  # 16
    ('PARA EQ 1', 'PARA EQ1'),  # 17
    ('PARA EQ 2', 'PARA EQ2'),  # 18
    ('PARA EQ 3', 'PARA EQ3'),  # 19
    ('PARA EQ 4', 'PARA EQ4'),  # 20
    ('AMP 1', 'AMP 1'),  # 21
    ('AMP 2', 'AMP 2'),  # 22
    ('*AMP 3*', '*AMP 3*'),  # 23
    ('*AMP 4*', '*AMP 4*'),  # 24
    ('CAB 1', 'CAB 1'),  # 25
    ('CAB 2', 'CAB 2'),  # 26
    ('*CAB 3*', '*CAB 3*'),  # 27
    ('*CAB 4*', '*CAB 4*'),  # 28
    ('REVERB 1', 'REVERB 1'),  # 29
    ('REVERB 2', 'REVERB 2'),  # 30
    ('*REVERB 3*', '*REV 3'),  # 31
    ('*REVERB 4*', '*REV 4'),  # 32
    ('DELAY 1', 'DELAY 1'),  # 33
    ('DELAY 2', 'DELAY 2'),  # 34
    ('DELAY 3', 'DELAY 3'),  # 35
    ('DELAY 4', 'DELAY 4'),  # 36
    ('MULTITAP DLY 1', 'MU.TAP 1'),  # 37
    ('MULTITAP DLY 2', 'MU.TAP 2'),  # 38
    ('*MULTITAP DLY 3*', '*M.TAP 3'),  # 39
    ('*MULTITAP DLY 4*', '*M.TAP 4'),  # 40
    ('CHORUS 1', 'CHORUS 1'),  # 41
    ('CHORUS 2', 'CHORUS 2'),  # 42
    ('*CHORUS 3*', '*CHORUS3'),  # 43
    ('*CHORUS 4*', '*CHORUS4'),  # 44
    ('FLANGER 1', 'FLANGER 1'),  # 45
    ('FLANGER 2', 'FLANGER 2'),  # 46
    ('*FLANGER 3*', '*FLANGER3'),  # 47
    ('*FLANGER 4*', '*FLANGER 4'),  # 48
    ('ROTARY 1', 'ROTARY 1'),  # 49
    ('ROTARY 2', 'ROTARY 2'),  # 50
    ('*ROTARY 3*', '*ROT 3*'),  # 51
    ('*ROTARY 4*', '*ROT 4*'),  # 52
    ('PHASER 1', 'PHASER 1'),  # 53
    ('PHASER 2', 'PHASER 2'),  # 54
    ('*PHASER 3*', '*PHASER3'),  # 55
    ('*PHASER 4*', '*PHASER4'),  # 56
    ('WAH 1', 'WAH 1'),  # 57
    ('WAH 2', 'WAH 2'),  # 58
    ('*WAH 3*', '*WAH 3*'),  # 59
    ('*WAH 4*', '*WAH 4*'),  # 60
    ('FORMANT 1', 'FORMNT 1'),  # 61
    ('FORMANT 2', 'FORMNT 2'),  # 62
    ('FORMANT 3*', 'FORMNT 3*'),  # 63
    ('FORMANT 4*', 'FORMNT 4*'),  # 64
    ('VOLUME 1', 'VOLUME 1'),  # 65
    ('VOLUME 2', 'VOLUME 2'),  # 66
    ('VOLUME 3', 'VOLUME 3'),  # 67
    ('VOLUME 4', 'VOLUME 4'),  # 68
    ('TREMOLO 1', 'TREM 1'),  # 69
    ('TREMOLO 2', 'TREM 2'),  # 70
    ('*TREMOLO 3*', '*TREM 3*'),  # 71
    ('*TREMOLO 4*', '*TREM 4*'),  # 72
    ('PITCH 1', 'PITCH 1'),  # 73
    ('PITCH 2', 'PITCH 2'),  # 74
    ('*PITCH 3*', '*PITCH 3'),  # 75
    ('*PITCH 4*', '*PITCH 4'),  # 76
    ('FILTER 1', 'FILTER 1'),  # 77
    ('FILTER 2', 'FILTER 2'),  # 78
    ('FILTER 3', 'FILTER 3'),  # 79
    ('FILTER 4', 'FILTER 4'),  # 80
    ('DRIVE 1', 'DRIVE 1'),  # 81
    ('DRIVE 2', 'DRIVE 2'),  # 82
    ('DRIVE 3', 'DRIVE 3'),  # 83
    ('DRIVE 4', 'DRIVE 4'),  # 84
    ('ENHANCER 1', 'ENHNCR 1'),  # 85
    ('ENHANCER 2', 'ENHNCR 2'),  # 86
    ('*ENHANCER 3*', '*ENHAN 3'),  # 87
    ('*ENHANCER 4*', '*ENHAN 4'),  # 88
    ('MIXER 1', 'MIXER 1'),  # 89
    ('MIXER 2', 'MIXER 2'),  # 90
    ('MIXER 3', 'MIXER 3'),  # 91
    ('MIXER 4', 'MIXER 4'),  # 92
    ('SYNTH 1', 'SYNTH 1'),  # 93
    ('SYNTH 2', 'SYNTH 2'),  # 94
    ('*SYNTH 3*', '*SYNTH 3'),  # 95
    ('*SYNTH 4*', '*SYNTH 4'),  # 96
    ('VOCODER 1', 'VOCODR 1'),  # 97
    ('*VOCODER 2*', '*VOCODR 2'),  # 98
    ('*VOCODER 3*', '*VOCODR 3'),  # 99
    ('*VOCODER 4*', '*VOCODR 4'),  # 100
    ('MEGATAP 1', 'MEGATAP 1'),  # 101
    ('MEGATAP 2', 'MEGATAP 2'),  # 102
    ('*MEGATAP 3*', '*ME.TAP3'),  # 103
    ('*MEGATAP 4*', '*ME.TAP4'),  # 104
    ('CROSSOVER 1', 'X OVER 1'),  # 105
    ('CROSSOVER 2', 'X OVER 2'),  # 106
    ('CROSSOVER 3*', '*X OVER3'),  # 107
    ('CROSSOVER 4*', '*X OVER4'),  # 108
    ('GATE 1', 'GATE 1'),  # 109
    ('GATE 2', 'GATE 2'),  # 110
    ('GATE 3', 'GATE 3'),  # 111
    ('GATE 4', 'GATE 4'),  # 112
    ('RING MOD 1', 'RING M 1'),  # 113
    ('*RING MOD 2*', '*RING M 2'),  # 114
    ('*RING MOD 3*', '*RING M 3'),  # 115
    ('*RING MOD 4*', '*RING M 4'),  # 116
    ('MULTICOMP 1', 'M.COMP 1'),  # 117
    ('MULTICOMP 2', 'M.COMP 2'),  # 118
    ('*MULTICOMP 3*', '*M.COMP 3'),  # 119
    ('*MULTICOMP 4*', '*M.COMP 4'),  # 120
    ('10 TAP DELAY 1', '10TAP DLY1'),  # 121
    ('10 TAP DELAY 2', '10TAP DLY2'),  # 122
    ('*10 TAP DELAY 3*', '*10TAPDLY3'),  # 123
    ('*10 TAP DELAY 4*', '*10TAPDLY4'),  # 124
    ('RESONATOR 1', 'RESON 1'),  # 125
    ('RESONATOR 2', 'RESON 2'),  # 126
    ('*RESONATOR 3*', '*RESO 3'),  # 127
    ('*RESONATOR 4*', '*RESO 4'),  # 128
    ('LOOPER 1', 'LOOPER 1'),  # 129
    ('*LOOPER 2*', '*LOOPER2'),  # 130
    ('*LOOPER 3*', '*LOOPER3'),  # 131
    ('*LOOPER 4*', '*LOOPER4'),  # 132
    ('TONE MATCH 1', 'TONE M 1'),  # 133
    ('*TONE MATCH 2*', '*TONE M 2'),  # 134
    ('*TONE MATCH 3*', '*TONE M 3'),  # 135
    ('*TONE MATCH 4*', '*TONE M 4'),  # 136
    ('Analyser 1', 'Analysr1'),  # 137
    ('Analyser 2*', '*Anlysr2'),  # 138
    ('*Analyser 3*', '*Anlysr 3'),  # 139
    ('*Analyser 4*', '*Anlysr 4'),  # 140
    ('PLEX DLY 1', 'PLEX DLY 1'),  # 141
    ('PLEX DLY 2', 'PLEX DLY 2'),  # 142
    ('*PLEX DLY 3*', '*PLEX D3'),  # 143
    ('*PLEX DLY 4*', '*PLEX D4'),  # 144
    ('SEND 1', 'SEND 1'),  # 145
    ('SEND 2', 'SEND 2'),  # 146
    ('*SEND 3*', '*SEND 3*'),  # 147
    ('*SEND 4*', '*SEND 4*'),  # 148
    ('RETURN 1', 'RETURN 1'),  # 149
    ('RETURN 2', 'RETURN 2'),  # 150
    ('*RETURN 3*', '*RETRN 3'),  # 151
    ('*RETURN 4*', '*RETRN 4'),  # 152
    ('MIDI BLK', 'MIDI BLK'),  # 153
    ('MULTIPLEXER 1', 'M.PLEX 1'),  # 154
    ('MULTIPLEXER 2', 'M.PLEX 2'),  # 155
    ('*MULTIPLEXER 3*', '*M.PLEX3'),  # 156
    ('*MULTIPLEXER 4*', '*M.PLEX4'),  # 157
    ('LOOP RECORD', 'RECORD'),  # 158
    ('LOOP PLAY', 'PLAY'),  # 159
    ('LOOP UNDO', 'UNDO'),  # 160
    ('LOOP ONCE', 'ONCE'),  # 161
    ('LOOP REV', 'REV'),  # 162
    ('LOOP HALF', 'HALF'),  # 163
    ('*LOOP DUB*', '*DUB*'),  # 164
    ('SCENE 1', 'SCENE 1'),  # 165
    ('SCENE 2', 'SCENE 2'),  # 166
    ('SCENE 3', 'SCENE 3'),  # 167
    ('SCENE 4', 'SCENE 4'),  # 168
    ('SCENE 5', 'SCENE 5'),  # 169
    ('SCENE 6', 'SCENE 6'),  # 170
    ('SCENE 7', 'SCENE 7'),  # 171
    ('SCENE 8', 'SCENE 8'),  # 172
    ('TAP TEMPO', 'T. TEMPO'),  # 173
    ('TUNER', 'TUNER'),  # 174
)

AXE2_EFFECTS = (
    ('Compressor 1', 'Comp 1'),  # 0
    ('Compressor 2', 'Comp 2'),  # 1
    ('EQ1 Graphic', 'EQ 1'),  # 2
    ('EQ2 Graphic', 'EQ 2'),  # 3
    ('PEQ1 Parametric', 'PEQ 1'),  # 4
    ('Parametric EQ 2', 'PEQ 2'),  # 5
    ('Amp 1', 'Amp 1'),  # 6
    ('Amp 2', 'Amp 2'),  # 7
    ('Cab 1', 'Cab 1'),  # 8
    ('Cab 2', 'Cab 2'),  # 9
    ('Reverb 1', 'Reverb 1'),  # 10
    ('Reverb 2', 'Reverb 2'),  # 11
    ('Delay 1', 'Delay 1'),  # 12
    ('Delay 2', 'Delay 2'),  # 13
    ('Multi Delay 1', 'M-Dly 1'),  # 14
    ('Multi Delay 2', 'M-Dly 2'),  # 15
    ('Chorus 1', 'Chorus 1'),  # 16
    ('Chorus 2', 'Chorus 2'),  # 17
    ('Flanger 1', 'Flanger1'),  # 18
    ('Flanger 2', 'Flanger2'),  # 19
    ('Rotary 1', 'Rotary 1'),  # 20
    ('Rotary 2', 'Rotary 2'),  # 21
    ('Phaser 1', 'Phaser 1'),  # 22
    ('Phaser 2', 'Phaser 2'),  # 23
    ('Wahwah 1', 'Wahwah 1'),  # 24
    ('Wahwah 2', 'Wahwah 2'),  # 25
    ('Formant 1', 'Formant1'),  # 26
    ('Volume/Pan 1', 'Vol/Pan1'),  # 27
    ('Tremolo 1', 'Tremolo1'),  # 28
    ('Tremolo 2', 'Tremolo2'),  # 29
    ('Pitch Shifter 1', 'Pitch 1'),  # 30
    ('Filter 1', 'Filter 1'),  # 31
    ('Filter 2', 'Filter 2'),  # 32
    ('Drive 1', 'Drive 1'),  # 33
    ('Drive 2', 'Drive 2'),  # 34
    ('Enhancer', 'Enhancer'),  # 35
    ('FX Loop', 'FX Loop'),  # 36
    ('Out 1 Mixer', 'Out 1'),  # 37
    ('Out 2 Mixer', 'Out 2'),  # 38
    ('Noise Gate', 'Noise'),  # 39
    ('Output', 'Output'),  # 40
    ('Controllers', 'Cntrls'),  # 41
    ('Feedback Send', 'FeedSend'),  # 42
    ('Feedback Return', 'FeedRtn'),  # 43
    ('Synth 1', 'Synth 1'),  # 44
    ('Synth 2', 'Synth 2'),  # 45
    ('Vocoder', 'Vocoder'),  # 46
    ('Megatap Delay', 'Megatap'),  # 47
    ('Crossover 1', 'Cross 1'),  # 48
    ('Crossover 2', 'Cross 2'),  # 49
    ('Gate/Expander 1', 'Gate 1'),  # 50
    ('Gate/Expander 2', 'Gate 2'),  # 51
    ('Ring Modulator', 'Ring Mod'),  # 52
    ('Pitch Shifter 2', 'Pitch '),  # 53
    ('Multiband Comp 1', 'MulComp1'),  # 54
    ('Multiband Comp 2', 'MultComp2'),  # 55
    ('Quad Chorus 1', 'Q-Cho 1'),  # 56
    ('Quad Chorus 2', 'Q-Cho 2'),  # 57
    ('Resonator 1', 'Reson 1'),  # 58
    ('Resonator 2', 'Reson 2'),  # 59
    ('Graphic EQ 3', 'G-EQ 3'),  # 60
    ('Graphic EQ 4', 'G-EQ 4'),  # 61
    ('Parametric EQ 3', 'P-EQ 3'),  # 62
    ('Parametric EQ 4', 'P-EQ 4'),  # 63
    ('Filter 3', 'Filter 3'),  # 64
    ('Filter 4', 'Filter 4'),  # 65
    ('Volume/Pan 2', 'Vol/Pan2'),  # 66
    ('Volume/Pan 3', 'Vol/Pan3'),  # 67
    ('Volume/Pan 4', 'Vol/Pan4'),  # 68
    ('LOOPER', 'LOOPER'),  # 69
    ('LOOPER RECORD', 'LP REC'),  # 70
    ('LOOPER PLAY', 'LP PLAY'),  # 71
    ('LOOPER ONCE', 'LP ONCE'),  # 72
    ('LOOPER DUB', 'LP DUB'),  # 73
    ('LOOPER REV', 'LP REV'),  # 74
    ('LOOPER HALF', 'LP HALF'),  # 75
    ('LOOPER UNDO', 'LP UNDO'),  # 76
    ('SCENE 1', 'SCENE 1'),  # 77
    ('SCENE 2', 'SCENE 2'),  # 78
    ('SCENE 3', 'SCENE 3'),  # 79
    ('SCENE 4', 'SCENE 4'),  # 80
    ('SCENE 5', 'SCENE 5'),  # 81
    ('SCENE 6', 'SCENE 6'),  # 82
    ('SCENE 7', 'SCENE 7'),  # 83
    ('SCENE 8', 'SCENE 8'),  # 84
)

KEMPER_EFFECTS = (
    ('STOMP A', 'KPA  A'),  # 0
    ('STOMP B', 'KPA  B'),  # 1
    ('STOMP C', 'KPA  C'),  # 2
    ('STOMP D', 'KPA  D'),  # 3
    ('STOMP X', 'KPA  X'),  # 4
    ('STOMP MOD', 'KPA  MOD'),  # 5
    ('STOMP DELAY', 'KPA  DLY'),  # 6
    ('STOMP REVERB', 'KPA  RVB'),  # 7
    ('Perform RIG 1', 'P.Slot 1'),  # 8
    ('Perform RIG 2', 'P.Slot 2'),  # 9
    ('Perform RIG 3', 'P.Slot 3'),  # 10
    ('Perform RIG 4', 'P.Slot 4'),  # 11
    ('Perform RIG 5', 'P.Slot 5'),  # 12
    ('Perform UP', 'PERF UP'),  # 13
    ('Perform DOWN', 'PERF DWN'),  # 14
    ('Tap Tempo', 'T. TEMPO'),  # 15
    ('TUNER', 'TUNER'),  # 16
)

# Kemper EFFECT-TYPE database (device 4 of the internal-data block): sparse KPA effect-type id -> (name, nick).
# From Firmware_Effect_Labels.Load_Kemper_Data. Id 199 ('3', 'KEMPER') is as shipped (marker/placeholder).
KEMPER_EFFECT_TYPES = {
    0: ('Empty Stomp', '--------'),
    1: ('Wah Wah', 'WAH WAH'),
    2: ('Wah Low Pass', 'WAH LOp'),
    3: ('Wah High Pass', 'WAH HIp'),
    4: ('Wah Vowel Filter', 'WAH VOWL'),
    5: ('Wah Phaser', 'WAH PHAS'),
    6: ('Wah Phaser2', 'WAH PHAS'),
    7: ('Wah Flanger', 'WAH FLAN'),
    8: ('Wah Rate Reducer', 'WAH RDCR'),
    9: ('Wah Ring Modulator', 'WAH MOD'),
    10: ('Wah Freq Shifter', 'WA SHIFT'),
    11: ('Pedal Pitch', 'P PITCH'),
    12: ('Wah Formant Shift', 'WAH FORM'),
    13: ('Pedal Vinyl Stop', 'PV STOP'),
    17: ('Bit Shaper', 'B SHAPER'),
    18: ('Recti Shaper', 'R SHAPER'),
    19: ('Soft Shaper', 'S SHAPER'),
    20: ('Hard Shaper', 'H SHAPER'),
    21: ('Wave Shaper', 'W SHAPER'),
    33: ('Green Scream', 'GREEN SC'),
    34: ('Plus DS', 'PLUS DST'),
    35: ('One DS', 'ONE DIST'),
    36: ('Muffin', 'MUFFIN D'),
    37: ('Mouse', 'MOUSE DS'),
    38: ('Fuzz DS', 'FUZZ DS'),
    39: ('Metal DS', 'METAL DS'),
    49: ('Compressor', 'COMPRESS'),
    57: ('Gate 2:1', 'GATE 2:1'),
    58: ('Gate 4:1', 'GATE 4:1'),
    64: ('Space', 'SPACE'),
    65: ('Vintage Chorus', 'V CHORUS'),
    66: ('Hyper Chorus', 'H CHORUS'),
    67: ('Air Chorus', 'A CHORUS'),
    68: ('Vibrato', 'VIBRATO'),
    69: ('Rotary Speaker', 'ROTARY S'),
    70: ('Tremolo', 'TREMOLO'),
    71: ('Micro Pitch', 'M PITCH'),
    81: ('Phaser', 'PHASER'),
    82: ('Phaser Vibe', 'PHASER V'),
    83: ('Phaser Oneway', 'PHASER O'),
    89: ('Flanger', 'FLANGER'),
    91: ('Flanger Oneway', 'FLANGER'),
    97: ('Graphic Equalizer', 'GRAPH EQ'),
    98: ('Studio Equalizer', 'STUD EQ'),
    99: ('Metal Equalizer', 'METAL EQ'),
    101: ('(Stereo Widener)', 'ST. WIDE'),
    113: ('Treble Booster', 'R BOOSTR'),
    114: ('Lead Booster', 'L BOOSTR'),
    115: ('Pure Booster', 'P BOOSTR'),
    116: ('Wah Pedal Booster', 'W BOOSTR'),
    121: ('Loop Mono', 'LOOP MON'),
    122: ('(Loop Stereo)', 'LOOP ST'),
    123: ('Loop Distortion', 'LOOP DIS'),
    129: ('Transpose', 'TRANSPOS'),
    130: ('Chromatic Pitch', 'CHRO PIT'),
    131: ('Harmonic Pitch', 'HARM PIT'),
    132: ('Analog Octaver', 'OCTAVER'),
    137: ('2 Chromatic Dly', 'DLY 2CHR'),
    138: ('2 Harmonic Dly', 'DLY 2HAR'),
    139: ('2 Crystal Delay', 'DLY 2CRY'),
    140: ('2 Loop Pitch Delay', 'DLY 2PIT'),
    145: ('Legacy Delay', 'DELAY'),
    146: ('Single Delay', 'DELAY 1'),
    147: ('Dual Delay', 'DELAY 2'),
    148: ('TwoTap Delay', 'DLY 2TAP'),
    149: ('Serial 2-Tap Dly', 'DLY S 2T'),
    150: ('Crystal Delay', 'DLY CRSL'),
    151: ('Loop Pitch Dly', 'DLY PIT'),
    152: ('Freq Shifter Dly', 'DLY F SH'),
    161: ('Rhythm Delay', 'DLY RHYM'),
    162: ('Melody Chrmtic Dly', 'DLY M CH'),
    163: ('Melody Hrmnic Dly', 'DLY M HD'),
    164: ('Quad Delay', 'DELAY 4'),
    165: ('4 Chromatic Delay', 'DLY 4 CD'),
    166: ('4 Harmonic Delay', 'DLY 4 HD'),
    177: ('Legacy Reverbs', 'REVERB'),
    178: ('Natural Reverbs', 'REVERB'),
    179: ('Easy Reverbs', 'REVERB'),
    180: ('Echo Reverbs', 'REVERB'),
    181: ('Cirrus Reverbs', 'REVERB'),
    182: ('Formant Reverbs', 'REVERB'),
    183: ('Ionosphere Reverbs', 'REVERB'),
    193: ('Reverb Slot', '-REVERB-'),
    196: ('MOD STOMP', '- MOD -'),
    197: ('DELAY STOMP', '-DELAY-'),
    198: ('Reverb Stomp', '-REVERB-'),
    199: ('3', 'KEMPER'),
}

SYNC_EFFECTS_BY_DEVICE = {2: AXE3_EFFECTS, 3: AXE2_EFFECTS, 4: KEMPER_EFFECTS}


def sync_effect_name(device: int, effect: int, nick: bool = False) -> str | None:
    """Name of ``effect`` for sync ``device`` (None if device has no table or index is out of range)."""
    table = SYNC_EFFECTS_BY_DEVICE.get(device)
    if table is None or not 0 <= effect < len(table):
        return None
    return table[effect][1 if nick else 0]


def effect_options_by_device() -> dict[int, dict[int, str]]:
    """``{sync device: {effect index: full name}}`` for the IA-Slot "Sync effect" dropdown."""
    return {dev: {i: full for i, (full, _nick) in enumerate(table)}
            for dev, table in SYNC_EFFECTS_BY_DEVICE.items()}
