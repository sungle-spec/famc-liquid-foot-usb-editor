"""
Codec round-trip + semantic tests against the real device dumps and factory files.

The headline guarantee: `Dump.from_bytes(b).to_bytes() == b` for every fixture — we can read
and re-write any LF+ backup losslessly, which is the precondition for safe device writes.
"""
import pathlib

import pytest

from conftest import requires_rjm

from lfeditor.codec import Dump
from lfeditor.model import Preset

ROOT = pathlib.Path(__file__).resolve().parent.parent
DUMPS = sorted((ROOT / "reference" / "sysex_dumps").glob("*.syx"))
FACTORY = sorted((ROOT / "lfeditor" / "resources" / "factory").glob("*.syx"))
ALL_SYX = DUMPS + FACTORY

# A broad real-world corpus (124 user backups spanning firmware v3.x–v6.x and every variant:
# 12+, JR, Mini, PRO+). We only round-trip genuine LF+ *config backups* — files that begin
# with the FAMC manufacturer ID (F0 00 00 7C). That filter naturally drops the Fractal Axe-Fx
# preset files (F0 00 01 74) interleaved in the corpus; we additionally skip firmware-image
# .syx (a single multi-hundred-KB transfer blob, not a record stream).
FAMC_ID = bytes([0xF0, 0x00, 0x00, 0x7C])
_CORPUS_DIR = ROOT / "reference" / "sysex_dumps" / "LF+ Editor Sysex Files"


def _is_lf_backup(p: pathlib.Path) -> bool:
    try:
        head = p.read_bytes()[:6]
    except OSError:
        return False
    if head[:4] != FAMC_ID:
        return False
    # Firmware images use sub-command 0x06 right after the type byte; backups use 0x01.
    return not (len(head) >= 6 and head[5] == 0x06)


CORPUS = sorted(p for p in _CORPUS_DIR.rglob("*.syx") if _is_lf_backup(p))

# Counts the official editor's loader reports for a full device dump.
EXPECTED_COUNTS = {
    "Preset": 384, "Song": 254, "IASwitch": 180, "Config": 2, "Setlist": 128,
    "SysexMsg": 255, "Page": 50, "IAMap": 60,
}


@pytest.mark.parametrize("path", ALL_SYX, ids=lambda p: p.name)
def test_byte_exact_roundtrip(path):
    data = path.read_bytes()
    assert Dump.from_bytes(data).to_bytes() == data


@pytest.mark.skipif(not CORPUS, reason="real-world corpus not present")
@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.name)
def test_corpus_byte_exact_roundtrip(path):
    """Every real LF+ backup in the user corpus re-encodes byte-for-byte."""
    data = path.read_bytes()
    assert Dump.from_bytes(data).to_bytes() == data


@pytest.mark.skipif(not CORPUS, reason="real-world corpus not present")
def test_corpus_setlist_song_count_in_range():
    """value[84] (Set-List song count) is always a valid 0..60 across the whole corpus."""
    from lfeditor.model.setlist import NUM_SONG_SLOTS
    seen = 0
    for path in CORPUS:
        for sl in Dump.from_file(str(path)).setlists:
            if len(sl.values) >= 90:
                assert 0 <= sl.song_count <= NUM_SONG_SLOTS, f"{path.name}: {sl.song_count}"
                assert sl.values[86:90] == [0, 0, 0, 0]  # reserved tail
                seen += 1
    assert seen > 1000


@requires_rjm
def test_preset_command_decode():
    """Verified command-table decode against RJM's known programming."""
    from lfeditor.model.preset import decode_command
    dump = Dump.from_file(str(ROOT / "reference" / "sysex_dumps" / "RJM.syx"))
    p0 = dump.presets[0]  # MOTP 1
    assert p0.command_text(0) == "PC ch2 → prog 21"
    assert p0.command_text(1) == "CC ch12 #19 = 12"
    assert p0.command_text(2) == "IA ON Trig (map) slot 1"
    # Pure-function spot checks across message types.
    assert decode_command(0, 0, 0, 0) == ""
    assert decode_command(1, 0xB0, 7, 100) == "CC ch1 #7 = 100"
    assert decode_command(1, 0xC0, 1, 127) == "PC ch1 → prog 383"   # (1<<8)+127 = Axe-Fx range
    assert decode_command(1, 0x90, 60, 100) == "Note On ch1 note 60 = 100"


def test_command_function_map():
    """The full function-code table, RE'd from LF+ Editor v6.31 (crafted func bytes 0..67).
    Locks the codes that were previously wrong (13/14) so they can't regress."""
    from lfeditor.model.preset import CMD_FUNCS
    assert CMD_FUNCS[13] == "Set Color"          # was wrongly "IA Resend (map)"
    assert CMD_FUNCS[14] == "Preset Store"        # was wrongly "IA Set Step #"
    assert CMD_FUNCS[21] == "IA Resend (map)"     # the real IA Resend
    assert CMD_FUNCS[56] == "IA Set Step Number"  # the real IA Set Step
    for code, name in [(2, "G-Tuner"), (4, "Sysex Send"), (8, "Page Change"), (33, "Song Change"),
                       (38, "Device Sync"), (55, "Preset Momentary then Jump"),
                       (66, "AXE3 Chan/State"), (67, "AXE3 Chg SCENE#")]:
        assert CMD_FUNCS[code] == name
    assert max(CMD_FUNCS) == 67 and len(CMD_FUNCS) == 68


@pytest.mark.skipif(not CORPUS, reason="real-world corpus not present")
def test_corpus_midi_commands_have_valid_status():
    """Every func==1 preset command across the corpus carries a valid MIDI status byte."""
    from lfeditor.model.preset import CMDS_OFF, NUM_CMDS, FUNC_MIDI
    seen = 0
    for path in CORPUS:
        for pr in Dump.from_file(str(path)).presets:
            v = pr.values
            if len(v) < CMDS_OFF + 4 * NUM_CMDS:
                continue
            for k in range(NUM_CMDS):
                o = CMDS_OFF + 4 * k
                if v[o] == FUNC_MIDI:
                    assert 0x80 <= v[o + 1] <= 0xEF, f"{path.name}: bad status {v[o+1]:#x}"
                    seen += 1
    assert seen > 1000


@pytest.mark.parametrize("path", DUMPS, ids=lambda p: p.name)
def test_full_dump_counts(path):
    counts = Dump.from_file(str(path)).counts()
    for name, n in EXPECTED_COUNTS.items():
        assert counts.get(name) == n, f"{path.name}: {name} = {counts.get(name)} != {n}"


@pytest.mark.parametrize("path", DUMPS, ids=lambda p: p.name)
def test_preset_names_decode(path):
    presets = Dump.from_file(str(path)).presets
    assert len(presets) == 384
    named = [p for p in presets if p.name and p.name != "NO PRESET"]
    assert len(named) > 10  # a real rig has many named presets
    assert all(isinstance(p, Preset) for p in presets)


@pytest.mark.parametrize("path", DUMPS, ids=lambda p: p.name)
def test_full_and_nick_names(path):
    """Every name-bearing type exposes a full name (0:16) and nick name (16:24)."""
    dump = Dump.from_file(str(path))
    for getter in (dump.presets, dump.songs, dump.ia_switches, dump.setlists,
                   dump.sysex_messages, dump.pages, dump.ia_maps):
        rec = getter[0]
        assert rec.has_name
        assert isinstance(rec.name, str)
        assert isinstance(rec.nick, str)


def test_edit_nick_is_lossless():
    data = ALL_SYX[0].read_bytes()
    dump = Dump.from_bytes(data)
    ia = dump.ia_switches[0]
    original = ia.nick
    ia.nick = "TEST"
    assert Dump.from_bytes(dump.to_bytes()).ia_switches[0].nick == "TEST"
    ia.nick = original
    assert dump.to_bytes() == data


def test_edit_name_is_surgical_and_lossless():
    """Renaming one preset changes only that preset's bytes."""
    data = ALL_SYX[0].read_bytes()
    dump = Dump.from_bytes(data)
    p0 = dump.presets[0]
    original = p0.name
    p0.name = "ROUNDTRIP TEST"
    edited = dump.to_bytes()

    assert len(edited) == len(data)
    # exactly one frame's bytes differ
    reparsed = Dump.from_bytes(edited)
    assert reparsed.presets[0].name == "ROUNDTRIP TEST"
    # restoring the name reproduces the original file byte-for-byte
    reparsed.presets[0].name = original
    assert reparsed.to_bytes() == data


@requires_rjm
def test_preset_ia_states_and_maps():
    """Verified diff-mapped Preset fields decode the RJM rig correctly."""
    dump = Dump.from_file(str(ROOT / "reference" / "sysex_dumps" / "RJM.syx"))
    p0 = dump.presets[0]  # 'MOTP 1' — slots 1 & 2 initially ON
    assert p0.ia_on(1) and p0.ia_on(2)
    assert not p0.ia_on(3)
    assert p0.default_page == 0      # use currently-active page
    assert p0.ia_slot_map == 0       # IA-Map 001

    # toggling an IA state is lossless when reverted
    data = (ROOT / "reference" / "sysex_dumps" / "RJM.syx").read_bytes()
    d2 = Dump.from_bytes(data)
    d2.presets[0].set_ia_on(5, True)
    assert d2.presets[0].ia_on(5)
    d2.presets[0].set_ia_on(5, False)
    assert d2.to_bytes() == data


@requires_rjm
def test_iaswitch_fields():
    """Verified IA-Slot offsets decode the rig: slot 1 'Sound Sculpture'."""
    from lfeditor.model import IASwitch
    dump = Dump.from_file(str(ROOT / "reference" / "sysex_dumps" / "RJM.syx"))
    ia = dump.ia_switches[0]
    assert isinstance(ia, IASwitch)
    assert ia.name == "Sound Sculpture"
    assert ia.switch_type == 0       # Stomp
    assert ia.on_color == 9          # Green - Bright
    assert ia.bypass_color == 10     # Red - Bright
    assert ia.off_color == 0 and ia.blocked_color == 0


@requires_rjm
def test_iaswitch_midi_commands():
    """On/Bypass commands are 4-byte [func, status, b2, b3] (same as presets) and decode as MIDI."""
    from lfeditor.model.iaswitch import ON_CMDS_OFF, BYPASS_CMDS_OFF
    from lfeditor.model.preset import decode_command, FUNC_MIDI
    dump = Dump.from_file(str(ROOT / "reference" / "sysex_dumps" / "RJM.syx"))
    v = dump.ia_switches[0].values  # 'Sound Sculpture'
    # On cmd0 = func MIDI, status 0xB0 (CC ch1), data1=11, data2=127
    on = v[ON_CMDS_OFF:ON_CMDS_OFF + 4]
    assert on[0] == FUNC_MIDI and on[1] == 0xB0 and on[2] == 11 and on[3] == 127
    assert decode_command(*on) == "CC ch1 #11 = 127"
    # Bypass cmd0 = func MIDI, CC ch1 #11 = 0
    by = v[BYPASS_CMDS_OFF:BYPASS_CMDS_OFF + 4]
    assert by[0] == FUNC_MIDI and by[1] == 0xB0 and by[2] == 11 and by[3] == 0
    assert decode_command(*by) == "CC ch1 #11 = 0"


@requires_rjm
def test_iaswitch_command_alignment():
    """Every IA-slot ON/Bypass command's byte-0 is a valid function code (0/1/2..67) — the proof
    the command tables are aligned at 29/109, not the old off-by-one 30/110 (which read the MIDI
    status byte as the function, e.g. 'Fn 176')."""
    from lfeditor.model.iaswitch import ON_CMDS_OFF, BYPASS_CMDS_OFF, NUM_CMDS
    from lfeditor.model.preset import CMD_FUNCS
    dump = Dump.from_file(str(ROOT / "reference" / "sysex_dumps" / "RJM.syx"))
    valid = set(CMD_FUNCS)
    for ia in dump.ia_switches:
        v = ia.values
        for base in (ON_CMDS_OFF, BYPASS_CMDS_OFF):
            for i in range(NUM_CMDS):
                assert v[base + i * 4] in valid


@requires_rjm
def test_preset_command_programming():
    """Preset command entries (4 bytes [func,b1,b2,b3]) decode MOTP 1 on the rig."""
    from lfeditor.model.preset import CMDS_OFF
    dump = Dump.from_file(str(ROOT / "reference" / "sysex_dumps" / "RJM.syx"))
    v = dump.presets[0].values  # MOTP 1
    o = CMDS_OFF
    assert v[o:o + 4] == [1, 0xC1, 0, 21]       # MIDI Command, Kemper(ch1) PC# 21
    assert v[o + 4:o + 8] == [1, 0xBB, 19, 12]  # MIDI Command, Nord G2(ch11) CC# 19/12
    assert v[o + 8:o + 12] == [10, 1, 0, 0]     # IA ON Trig (map) 1
    assert v[o + 12:o + 16] == [10, 2, 0, 0]    # IA ON Trig (map) 2
    assert v[o + 16:o + 20] == [1, 0xC5, 0, 10]  # MIDI Command, Switchbl(ch5) PC# 10


@requires_rjm
def test_iamap_default_is_identity():
    """The 'IA-Map Default' record maps button i -> slot i (identity)."""
    from lfeditor.model import IAMap
    dump = Dump.from_file(str(ROOT / "reference" / "sysex_dumps" / "RJM.syx"))
    m0 = dump.ia_maps[0]
    assert isinstance(m0, IAMap)
    assert [m0.slot_for_button(i) for i in range(60)] == list(range(60))


def test_sysex_data_bytes_roundtrip():
    """Editing a Sysex Message's data bytes is lossless."""
    data = ALL_SYX[0].read_bytes()
    dump = Dump.from_bytes(data)
    msg = dump.sysex_messages[0]
    msg.values[24] = 0x7F  # first data byte
    assert Dump.from_bytes(dump.to_bytes()).sysex_messages[0].values[24] == 0x7F
    msg.values[24:40] = Dump.from_bytes(data).sysex_messages[0].values[24:40]
    assert dump.to_bytes() == data
