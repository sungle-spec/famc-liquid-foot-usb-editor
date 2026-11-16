"""Report regressions using bundled factory files; runs in public CI."""
from lfeditor import csvio

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


def test_reports_resolve_references_by_record_number_in_sparse_files():
    from lfeditor.model.song import SLOT_OFF, SLOT_UNUSED
    from lfeditor.model.iamap import MAP_OFF
    d = _factory()
    preset = d.presets[4]
    ia = d.ia_switches[4]
    # Partial backups may omit the preceding four records, but references keep their numbers.
    d.frames[:] = [f for f in d.frames if f.type not in (1, 3) or f.rec_num == 4]
    song = d.songs[0]
    for i in range(24):
        song.values[SLOT_OFF + 2 * i:SLOT_OFF + 2 * i + 2] = [255, 255]
    song.values[SLOT_OFF:SLOT_OFF + 2] = [4, 0]
    d.ia_maps[0].values[MAP_OFF] = 4
    songs = _rows(csvio.report_text(d, 'songs'))
    maps = _rows(csvio.report_text(d, 'iamaps'))
    assert songs[1][-1] == f'5: {preset.name.strip()}'
    assert maps[1][4] == f'5: {ia.name.strip()}'


def test_reports_do_not_modify_the_document():
    d = _factory()
    before = d.to_bytes()
    for kind in ('presets', 'songs', 'setlists', 'iaslots', 'iamaps'):
        csvio.report_text(d, kind)
    assert d.to_bytes() == before
