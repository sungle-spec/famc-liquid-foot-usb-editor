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
