"""The web build's Qt-free layer: the UI schema and the Pyodide-facing Session API.

These run as normal pytest (PySide6 present), but everything under test imports without Qt — which
is what lets it run in the browser under Pyodide. `tests/test_uat.py` etc. still guard the desktop.
"""
import json
import pathlib

import pytest

from conftest import requires_rjm

from lfeditor.schema import tab_schema, schema_json, TAB_ORDER
from lfeditor.webapi import Session
from lfeditor.codec import Dump

ROOT = pathlib.Path(__file__).resolve().parent.parent
RJM = str(ROOT / "reference" / "sysex_dumps" / "RJM.syx")
FACTORY = str(ROOT / "lfeditor" / "resources" / "factory" / "Factory_Defaults12.syx")


# ---- schema ----

def test_schema_is_valid_json_covering_all_11_tabs():
    s = json.loads(schema_json())
    assert [t["name"] for t in s["tabs"]] == TAB_ORDER
    assert len(s["tabs"]) == 11
    kinds = {t["name"]: t["kind"] for t in s["tabs"]}
    assert kinds["Pages"] == "pages" and kinds["Midi/Groups"] == "midi_groups"
    assert kinds["Global"] == "global" and kinds["Presets"] == "record"


@requires_rjm
def test_every_field_offset_is_in_range_for_its_record():
    dump = Dump.from_file(RJM)
    vlen = {}
    for f in dump.frames:
        vlen.setdefault(f.type, len(f.values))
    for tab in tab_schema()["tabs"]:
        if "columns" not in tab:
            continue
        n = vlen.get(tab["type"])
        if n is None:
            continue
        for col in tab["columns"]:
            for sec in col:
                for fld in sec["fields"]:
                    off = fld.get("offset", fld.get("start"))
                    if off is None:
                        continue
                    assert 0 <= off < n, f"{tab['name']}/{fld.get('label')!r} offset {off} >= {n}"


def test_enum_fields_carry_options():
    for tab in tab_schema()["tabs"]:
        for col in tab.get("columns", []):
            for sec in col:
                for fld in sec["fields"]:
                    if fld["kind"] == "enum":
                        assert isinstance(fld.get("options"), dict) and fld["options"]


# ---- webapi (the browser session) ----

@pytest.mark.parametrize("path", [pytest.param(RJM, marks=requires_rjm), FACTORY])
def test_session_load_save_is_byte_exact(path):
    data = pathlib.Path(path).read_bytes()
    s = Session()
    s.load(data)
    assert s.save() == data, "web Session did not round-trip byte-exact"


def test_session_edit_persists_and_sets_dirty():
    s = Session()
    s.load(pathlib.Path(FACTORY).read_bytes())
    assert s.dirty is False
    s.set_str(1, 0, 0, 16, "WEBNAME")
    assert s.dirty is True
    s2 = Session()
    s2.load(s.save())
    assert s2.get_str(1, 0, 0, 16).strip() == "WEBNAME"


def test_session_scalar_get_set_and_names():
    s = Session()
    s.load(pathlib.Path(FACTORY).read_bytes())
    assert s.count(1) == 384
    off = 49  # any byte
    s.set(1, 0, off, 7)
    assert s.get(1, 0, off) == 7
    names = s.names(1)
    assert len(names) == 384 and names[0].startswith("001: ")


def test_session_decode_button_matches_model():
    from lfeditor.model.page import decode_button_function
    s = Session()
    assert s.decode_button(1) == decode_button_function(1)
    assert s.decode_button(61) == decode_button_function(61)


def test_session_copy_paste_clear_record():
    s = Session()
    s.load(pathlib.Path(FACTORY).read_bytes())
    s.set_str(1, 0, 0, 16, "SRCNAME")
    assert s.copy_record(1, 0) is True
    assert s.can_paste(1, 5) is True
    assert s.paste_record(1, 5) is True
    assert s.get_str(1, 5, 0, 16).strip() == "SRCNAME"
    assert s.clear_record(1, 5) is True
    assert s.get_str(1, 5, 0, 16).strip() == "Preset #006"
    # still byte-exact serialisable
    assert len(s.save()) == len(pathlib.Path(FACTORY).read_bytes())


def test_session_multi_apply_and_find():
    s = Session()
    s.load(pathlib.Path(FACTORY).read_bytes())
    # set a known flag bit OFF across presets 1..10, then back ON, counting changes
    s.multi_apply(1, 8, 0x01, False, 1, 10)
    assert s.multi_apply(1, 8, 0x01, True, 1, 10) == 10
    res = s.find(text="Preset", types=[1], num_min=1, num_max=3)
    assert len(res) == 3 and res[0]["type"] == 1 and "number" in res[0]
    # command filter + first_only mirror the desktop Find dialog's extra criteria
    all_hits = s.find(types=[1], msgtype=0xC)
    once = s.find(types=[1], msgtype=0xC, first_only=True)
    assert len(once) <= len(all_hits)
    assert len({(m["type"], m["number"]) for m in once}) == len(once)
    csv_text = s.find_csv(text="Preset", types=[1], num_min=1, num_max=3)
    lines = csv_text.splitlines()
    assert lines[0] == '"Type","#","Name","Where","Data"' and len(lines) == 4


def test_session_csv_and_reports_roundtrip():
    s = Session()
    s.load(pathlib.Path(FACTORY).read_bytes())
    csv_text = s.export_text("presets")
    assert csv_text.splitlines()[0].startswith('"Num"')
    # change a name via CSV import (row for preset #1)
    lines = csv_text.splitlines()
    cells = lines[1].split('","')
    cells[1] = "CSVNAME"
    lines[1] = '","'.join(cells)
    res = s.import_text("presets", "\n".join(lines))
    assert res["applied"] >= 1
    assert s.get_str(1, 0, 0, 16).strip() == "CSVNAME"
    assert s.report_text("presets").splitlines()[0].startswith("Num")


def test_session_quickprog_and_reorder():
    s = Session()
    s.load(pathlib.Path(FACTORY).read_bytes())
    from lfeditor.quickprog import empty_command
    assert s.quick_apply("preset_cmd", 1, 1, 3, empty_command()) == 3
    perm = s.move_record(1, 2, 5, True)
    assert isinstance(perm, dict) and perm
    assert len(s.save()) == len(pathlib.Path(FACTORY).read_bytes())
