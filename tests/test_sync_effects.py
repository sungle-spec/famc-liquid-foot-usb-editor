"""Per-device sync-effect tables (recovered from the original v6.31 editor) vs. factory templates."""
import re
from pathlib import Path

import pytest

from lfeditor.codec import Dump
from lfeditor.model import iaswitch as m, wrap
from lfeditor.model.sync_effects import (
    AXE2_EFFECTS, AXE3_EFFECTS, KEMPER_EFFECTS, SYNC_EFFECTS_BY_DEVICE, sync_effect_name,
)

FACTORY = Path(__file__).resolve().parent.parent / "reference" / "factory_syx"


def _factory(name):
    """reference/ is gitignored (not on CI runners): skip rather than fail when it's absent."""
    path = FACTORY / name
    if not path.exists():
        pytest.skip(f"{path} not present (reference/ is local-only)")
    return path


_norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731


def test_table_sizes_and_devices():
    assert (len(AXE3_EFFECTS), len(AXE2_EFFECTS), len(KEMPER_EFFECTS)) == (175, 85, 17)
    assert set(SYNC_EFFECTS_BY_DEVICE) == {2, 3, 4}
    assert all(set(m.SYNC_DEVICES) >= {d} for d in SYNC_EFFECTS_BY_DEVICE)


def test_kemper_legacy_dict_matches_table():
    assert len(m.SYNC_EFFECTS) == len(KEMPER_EFFECTS)
    assert m.SYNC_EFFECTS[16].lower() == KEMPER_EFFECTS[16][0].lower() == "tuner"


def test_out_of_range_is_none():
    assert sync_effect_name(4, 17) is None
    assert sync_effect_name(1, 0) is None


@pytest.mark.parametrize("fname,device,min_hit", [
    ("Factory_AXEFXIII_Basic", 2, 1.0),
    ("Factory_DefaultsAXEFX", 3, 0.8),
])
def test_factory_slots_resolve_to_their_own_names(fname, device, min_hit):
    d = Dump.from_file(_factory(f"{fname}.syx"))
    slots = []
    for fr in d.ia_switches:
        r = wrap(fr)
        if r.values[m.SYNC_DEVICE_OFF] == device:
            slots.append((r.name, r.values[m.SYNC_EFFECT_OFF]))
    assert slots
    hits = 0
    for name, eff in slots:
        full, nick = sync_effect_name(device, eff), sync_effect_name(device, eff, nick=True)
        assert full is not None, f"{fname}: effect index {eff} out of range for device {device}"
        if any(_norm(c) and (_norm(c) in _norm(name) or _norm(name) in _norm(c)) for c in (full, nick)):
            hits += 1
    assert hits / len(slots) >= min_hit, f"{fname}: only {hits}/{len(slots)} slot names matched"


def _kemper_slots(fname):
    d = Dump.from_file(_factory(f"{fname}.syx"))
    out = []
    for fr in d.ia_switches:
        r = wrap(fr)
        if r.values[m.SYNC_DEVICE_OFF] == 4:
            out.append((r.name, r.values[m.SYNC_EFFECT_OFF]))
    return out


def test_kemper_factory_defaults_cover_every_index_once():
    slots = _kemper_slots("Factory_DefaultsKEMPER")
    assert sorted(e for _, e in slots) == list(range(17))


@pytest.mark.parametrize("fname", ["Factory_DefaultsKEMPER", "Factory_Kemper_Perf_Template"])
def test_kemper_literal_name_slots_hit_the_right_index(fname):
    # Slots whose label *is* the effect name must point at that effect's index.
    expect = {"STOMP A": 0, "STOMP B": 1, "STOMP C": 2, "STOMP D": 3, "TAP TEMPO": 15, "TUNER": 16}
    seen = 0
    for name, eff in _kemper_slots(fname):
        if name.strip().upper() in expect:
            assert eff == expect[name.strip().upper()], (fname, name, eff)
            assert _norm(sync_effect_name(4, eff)) == _norm(name)
            seen += 1
    assert seen >= 5


def test_kemper_effect_type_table():
    from lfeditor.model.sync_effects import KEMPER_EFFECT_TYPES
    assert len(KEMPER_EFFECT_TYPES) == 87
    assert all(0 <= i < 200 for i in KEMPER_EFFECT_TYPES)
    assert KEMPER_EFFECT_TYPES[1][0] == "Wah Wah" and KEMPER_EFFECT_TYPES[49][0] == "Compressor"


# ---- IA-Slot "Sync effect" dropdown follows "Sync device" (schema + desktop widget) -------------

def _walk_fields(schema):
    def walk(o):
        if isinstance(o, dict):
            if "kind" in o and "label" in o:
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)
    return walk(schema)


def test_schema_exposes_options_by_device():
    import json
    from lfeditor import schema
    f = next(x for x in _walk_fields(json.loads(schema.schema_json()))
             if x["label"] == "Sync effect")
    assert f["kind"] == "enum" and f["depends_on"] == m.SYNC_DEVICE_OFF == 25
    assert {c: len(o) for c, o in f["options_by"].items()} == {"2": 175, "3": 85, "4": 17}
    assert f["options_by"]["2"]["165"] == "SCENE 1"
    assert f["options_by"]["4"]["16"] == "TUNER"


@pytest.fixture(scope="module")
def _qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _iaslot_fields():
    from lfeditor.ui.fields import DependentEnumField, EnumField
    from lfeditor.ui.specs import _iaslot_tab
    fields = [f for sec in _iaslot_tab().columns[0] for f in sec.fields]
    dev = next(f for f in fields if isinstance(f, EnumField) and f.offset == m.SYNC_DEVICE_OFF)
    eff = next(f for f in fields if isinstance(f, DependentEnumField))
    return dev, eff


def test_iaslot_spec_wires_effect_to_device():
    dev, eff = _iaslot_fields()
    assert eff.depends_on == dev.offset and eff.refresh in dev._listeners


def test_effect_combo_follows_device_and_never_rewrites_bytes(_qapp):
    dev, eff = _iaslot_fields()
    dev.build(); eff.build()
    values = [0] * 256
    values[m.SYNC_DEVICE_OFF], values[m.SYNC_EFFECT_OFF] = 2, 165      # AXE-FX III, SCENE 1
    dev.load(values); eff.load(values)
    assert eff.w.count() == 175 and eff.w.currentText() == "SCENE 1"

    dev.w.setCurrentIndex(dev.w.findData(4))                            # -> KEMPER KPA
    assert values[m.SYNC_DEVICE_OFF] == 4 and values[m.SYNC_EFFECT_OFF] == 165  # byte untouched
    assert eff.w.count() == 17 + 1                                      # 17 + "(unknown: 165)"
    assert eff.w.currentText() == "(unknown: 165)"

    eff.w.setCurrentIndex(eff.w.findData(16))                           # pick TUNER
    assert values[m.SYNC_EFFECT_OFF] == 16 and eff.w.currentText() == "TUNER"

    dev.w.setCurrentIndex(dev.w.findData(3))                            # -> AXE-FX II (85)
    assert eff.w.count() == 85 and values[m.SYNC_EFFECT_OFF] == 16      # 16 is valid there: no extra item
    assert eff.w.currentText() == sync_effect_name(3, 16)
    assert eff.w.findText("(unknown: 16)") == -1


def test_device_without_table_keeps_value_visible(_qapp):
    _dev, eff = _iaslot_fields()
    eff.build()
    values = [0] * 256
    values[m.SYNC_DEVICE_OFF], values[m.SYNC_EFFECT_OFF] = 0, 7        # no sync device
    eff.load(values)
    assert eff.w.count() == 1 and eff.w.currentText() == "(unknown: 7)"
    assert values[m.SYNC_EFFECT_OFF] == 7
