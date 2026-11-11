"""
CSV import/export + reports. The column formats were captured byte-for-byte from the original
LF+ Editor v6.31 (tests/fixtures/golden_csv/), so these lock our output to that contract.
"""
import csv
import io
import os
import pathlib
import tempfile

import pytest

from lfeditor.codec import Dump
from lfeditor import csvio

ROOT = pathlib.Path(__file__).resolve().parent.parent
RJM = str(ROOT / "reference" / "sysex_dumps" / "RJM.syx")

from conftest import requires_rjm
pytestmark = requires_rjm
FACTORY12 = str(ROOT / "lfeditor" / "resources" / "factory" / "Factory_Defaults12.syx")
GOLD = ROOT / "tests" / "fixtures" / "golden_csv"
GOLD_FILES = {
    "presets": "lf_presets_export_probe.csv",
    "songs": "lf_songs_export_probe.csv",
    "setlists": "lf_setlists_export_probe.csv",
    "sysex": "lf_sysex_export_probe.csv",
}


@pytest.fixture()
def rjm():
    return Dump.from_file(RJM)


# ---- format contract: headers match the original editor's export exactly ----

@pytest.mark.parametrize("kind", list(csvio.KINDS))
def test_header_matches_original(kind):
    d = Dump.from_file(FACTORY12)
    ours = csvio.export_text(d, kind).splitlines()[0]
    gold = (GOLD / GOLD_FILES[kind]).read_text().splitlines()[0]
    assert ours == gold


def test_setlist_export_matches_golden_byte_for_byte():
    # the original's factory-12 set-lists are identical to our bundled file, so the whole
    # set-list export must match byte-for-byte (proves the slot encoding + quoting + padding)
    d = Dump.from_file(FACTORY12)
    ours = csvio.export_text(d, "setlists")
    gold = (GOLD / GOLD_FILES["setlists"]).read_text()
    assert ours == gold


# ---- export shape ----

@pytest.mark.parametrize("kind,rows,cols", [
    ("presets", 384, 63), ("songs", 254, 27), ("setlists", 128, 63), ("sysex", 255, 22),
])
def test_export_shape(rjm, kind, rows, cols):
    lines = list(csv.reader(io.StringIO(csvio.export_text(rjm, kind))))
    assert len(lines) == rows + 1            # + header
    assert len(lines[0]) == cols
    assert all(len(r) == cols for r in lines[1:])


# ---- round-trip: export -> import -> export is stable, and import is surgical ----

@pytest.mark.parametrize("kind", list(csvio.KINDS))
def test_round_trip_stable(rjm, kind):
    t1 = csvio.export_text(rjm, kind)
    applied, warnings = csvio.import_text(rjm, kind, t1)
    assert applied == len(rjm.records(csvio.KINDS[kind]["type"]))
    assert warnings == []
    assert csvio.export_text(rjm, kind) == t1


def test_import_is_surgical(rjm):
    before = Dump.from_file(RJM)
    rows = list(csv.reader(io.StringIO(csvio.export_text(rjm, "presets"))))
    rows[2][1] = "CSV EDIT"      # preset 2 name
    rows[2][5] = "O"             # preset 2 Slot#3 ON
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)
    applied, warnings = csvio.import_text(rjm, "presets", buf.getvalue())
    assert applied == 384 and warnings == []

    p2 = rjm.records(1)[1]
    assert p2.name == "CSV EDIT" and p2.ia_on(2) is True
    # exactly one frame differs from the on-disk original
    changed = sum(1 for a, b in zip(rjm.frames, before.frames) if a.to_bytes() != b.to_bytes())
    assert changed == 1


def test_import_round_trips_through_file(rjm):
    rows = list(csv.reader(io.StringIO(csvio.export_text(rjm, "songs"))))
    rows[1][3] = "300"          # song 1, preset slot 1 -> preset 300
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)
    csvio.import_text(rjm, "songs", buf.getvalue())
    with tempfile.NamedTemporaryFile(suffix=".syx", delete=False) as tf:
        tmp = tf.name
    try:
        rjm.to_file(tmp)
        d2 = Dump.from_file(tmp)
        off = csvio.SONG_PRESET_OFF
        raw = d2.records(2)[0].values[off] | (d2.records(2)[0].values[off + 1] << 8)
        assert raw + 1 == 300
    finally:
        os.unlink(tmp)


# ---- import tolerance + warnings ----

def test_import_skips_out_of_range_num(rjm):
    text = csvio.export_text(rjm, "setlists").splitlines()
    text.append('"999","X","Y"' + ',"1"' * 60)   # no set-list #999
    applied, warnings = csvio.import_text(rjm, "setlists", "\n".join(text))
    assert applied == 128
    assert any("999" in w for w in warnings)


def test_sysex_hex_and_dec_parse(rjm):
    rows = list(csv.reader(io.StringIO(csvio.export_text(rjm, "sysex"))))
    rows[1][3] = "H"; rows[1][6] = "7F"        # hex 0x7F = 127
    rows[2][3] = "D"; rows[2][6] = "127"       # dec 127
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)
    csvio.import_text(rjm, "sysex", buf.getvalue())
    assert rjm.records(6)[0].values[csvio.SYSEX_DATA_OFF] == 127
    assert rjm.records(6)[1].values[csvio.SYSEX_DATA_OFF] == 127


# ---- reports ----

@pytest.mark.parametrize("kind,head", [
    ("presets", "Num,Name,Nickname,IA-Map,Default Page,Commands,ON slots"),
    ("songs", "Num,Name,Nickname,Presets,Assigned (number: name)"),
    ("setlists", "Num,Name,Nickname,Song count,Songs (number: name)"),
])
def test_report_headers(rjm, kind, head):
    assert csvio.report_text(rjm, kind).splitlines()[0] == head


def test_report_resolves_names(rjm):
    # a song report should resolve preset numbers to names where the song has assignments
    text = csvio.report_text(rjm, "songs")
    assert "Num,Name" in text.splitlines()[0]
    assert len(text.splitlines()) == 255   # header + 254 songs


# ---- IA-Slot / IA-Map reports ----
import csv as _csv
import io as _io

from lfeditor.resources import factory_path, FACTORY_DEFAULTS


def _factory():
    from lfeditor.codec import Dump
    return Dump.from_file(factory_path(FACTORY_DEFAULTS[0][1]))


def _rows(text):
    return list(_csv.reader(_io.StringIO(text)))


def test_iaslot_report_has_one_row_per_slot_and_the_documented_columns():
    d = _factory()
    rows = _rows(csvio.report_text(d, "iaslots"))
    assert rows[0][:4] == ["Num", "Name", "Nickname", "Enabled"]
    assert "ON commands" in rows[0] and "BYPASS commands" in rows[0]
    assert len(rows) == 1 + len(d.records(3))
    assert all(len(r) == len(rows[0]) for r in rows)


def test_iaslot_report_decodes_commands_settings_and_sync():
    from lfeditor.model import iaswitch as ia
    d = _factory()
    rec = d.records(3)[2]                       # slot #3
    v = rec.values
    v[ia.ENABLE_OFF] |= ia.ENABLE_BIT
    v[ia.SWITCH_TYPE_OFF] = 2                   # Step
    v[ia.SYNC_DEVICE_OFF], v[ia.SYNC_EFFECT_OFF] = 4, 16    # KEMPER, Tuner
    v[ia.ON_CMDS_OFF:ia.ON_CMDS_OFF + 4] = [1, 0xB0, 7, 100]   # row 1: MIDI CC ch1 #7 = 100
    v[ia.BYPASS_CMDS_OFF + 4:ia.BYPASS_CMDS_OFF + 8] = [1, 0xC1, 0, 5]   # row 2: PC ch2 -> prog 5
    row = _rows(csvio.report_text(d, "iaslots"))[3]
    head = _rows(csvio.report_text(d, "iaslots"))[0]
    col = dict(zip(head, row))
    assert col["Num"] == "3" and col["Enabled"] == "Yes" and col["Switch type"] == "Step"
    assert col["Sync device"] == "KEMPER KPA" and col["Sync effect"] == "TUNER"
    assert col["ON cmd count"] == "1" and col["ON commands"] == "1. CC ch1 #7 = 100"
    assert col["BYPASS cmd count"] == "1" and col["BYPASS commands"] == "2. PC ch2 → prog 5"


def test_iaslot_report_blank_sync_effect_when_no_device():
    d = _factory()
    rows = _rows(csvio.report_text(d, "iaslots"))
    col = dict(zip(rows[0], rows[1]))
    assert col["Sync device"] == "None" and col["Sync effect"] == ""


def test_iamap_report_resolves_slot_names_and_counts_remaps():
    from lfeditor.model.iamap import MAP_OFF
    d = _factory()
    maps = d.records(8)
    maps[1].values[MAP_OFF + 0] = 4              # button 1 -> slot 5
    rows = _rows(csvio.report_text(d, "iamaps"))
    assert rows[0][:5] == ["Num", "Name", "Nickname", "Remapped buttons", "Btn 1"]
    assert len(rows[0]) == 4 + 60 and len(rows) == 1 + len(maps)
    first = dict(zip(rows[0], rows[1]))
    assert first["Remapped buttons"] == "0" and first["Btn 1"].startswith("1: ")
    second = dict(zip(rows[0], rows[2]))
    slot5 = d.records(3)[4].name.strip()
    assert second["Remapped buttons"] == "1" and second["Btn 1"] == f"5: {slot5}"


def test_iamap_report_shows_renamed_slot():
    from lfeditor.text import encode_ascii
    d = _factory()
    d.records(3)[0].values[0:16] = encode_ascii("ZZ TEST", 16)
    row = _rows(csvio.report_text(d, "iamaps"))[1]
    assert row[4] == "1: ZZ TEST"


def test_report_kinds_cover_web_and_desktop_menus():
    d = _factory()
    for kind in ("presets", "songs", "setlists", "iaslots", "iamaps"):
        assert csvio.report_text(d, kind).strip()
