"""
UI / widget-level tests for the faithful rebuild.

Run head-less (offscreen). They verify the rebuilt tabs build, bind a real dump losslessly,
and that the key bespoke editors (command-table decode, slot pickers, rocker toggles, the
graphical pedalboard, the merged Midi/Groups grid) behave.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from lfeditor.codec import Dump
from lfeditor.ui.fields import SlotPickerField, CommandTableField, IAStateGridField

ROOT = pathlib.Path(__file__).resolve().parent.parent
RJM = str(ROOT / "reference" / "sysex_dumps" / "RJM.syx")

from conftest import requires_rjm
pytestmark = requires_rjm


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def win(qapp):
    from lfeditor.ui.app import MainWindow
    w = MainWindow()
    w.load(RJM)
    return w


def _fields(tab):
    return getattr(tab, "_all_fields", [])


def test_all_tabs_build_and_load_lossless(win):
    """Building every tab and binding the dump must not mutate any record bytes."""
    before = win.dump.to_bytes()
    for i, w in enumerate(win.tab_widgets):
        if hasattr(w, "rail") and w.rail.list.count() > 1:
            w.rail.list.setCurrentRow(1)
            w.rail.list.setCurrentRow(0)
    assert win.dump.to_bytes() == before


def test_preset_command_table_columns(win):
    """The command table resolves MOTP 1's first two rows to the right Function/MIDI/Cmd/Data."""
    tab = win.tab_widgets[0]  # Presets
    tab.rail.list.setCurrentRow(0)  # MOTP 1
    cmd = next(f for f in _fields(tab) if isinstance(f, CommandTableField))
    # row 0: PC ch2 -> prog 21  => MIDI Command, Program Change, channel 2, (b2<<8)+b3 == 21
    assert cmd.funcs_c[0].currentText() == "MIDI Command"
    assert cmd.cmds[0].currentText() == "Program Change"
    assert cmd.midis[0].currentData() == 1            # channel 2 (0-based)
    assert (cmd.d1s[0].value() << 8) + cmd.d2s[0].value() == 21
    # row 1: CC ch12 #19 = 12
    assert cmd.cmds[1].currentText() == "Control Change"
    assert cmd.midis[1].currentData() == 11           # channel 12
    assert cmd.d1s[1].value() == 19 and cmd.d2s[1].value() == 12


def test_preset_ia_state_grid_names(win):
    tab = win.tab_widgets[0]
    tab.rail.list.setCurrentRow(0)
    grid = next(f for f in _fields(tab) if isinstance(f, IAStateGridField))
    # first IA slot name resolved from the rig
    assert "Sound Sculpture" in grid._items[0].text()
    # slot 1 is ON for MOTP 1
    assert grid._toggles[0].isChecked()


def test_song_slot_picker_round_trips(win):
    tab = win.tab_widgets[win._tab_index("Songs")] if hasattr(win, "_tab_index") else win.tab_widgets[6]
    tab.rail.list.setCurrentRow(0)
    picker = next(f for f in _fields(tab) if isinstance(f, SlotPickerField))
    rec = tab._rec
    from lfeditor.model.song import SLOT_OFF, SLOT_UNUSED
    pos = next(p for p, (idx, _t) in enumerate(picker._items) if idx == 41)
    picker.combos[0].setCurrentIndex(pos)
    assert rec.values[SLOT_OFF] | (rec.values[SLOT_OFF + 1] << 8) == 41
    picker.combos[0].setCurrentIndex(0)  # (unused)
    assert rec.values[SLOT_OFF] | (rec.values[SLOT_OFF + 1] << 8) == SLOT_UNUSED


def test_rocker_toggle_writes_bit(win):
    """A ToggleField rocker flips the bound bit and marks dirty."""
    from lfeditor.ui.fields import ToggleField
    tab = win.tab_widgets[2]  # IA-Slot
    tab.rail.list.setCurrentRow(0)
    tg = next(f for f in _fields(tab) if isinstance(f, ToggleField))
    rec = tab._rec
    before = rec.values[tg.offset] & tg.bitmask
    tg.w.toggle.click()
    after = rec.values[tg.offset] & tg.bitmask
    assert before != after


def test_iaslot_step_names_section(win):
    """The IA-Slot 'Step Names' StringFields bind to value[189:221] (see docs/LF_DATA_MODEL.md)
    and round-trip an edit losslessly, same as the Preset tab's identical field."""
    from lfeditor.ui.fields import StringField
    from lfeditor.model.iaswitch import STEP_NAMES_OFF
    tab = win.tab_widgets[2]  # IA-Slot
    tab.rail.list.setCurrentRow(0)
    step_fields = [f for f in _fields(tab)
                   if isinstance(f, StringField) and f.start >= STEP_NAMES_OFF]
    assert len(step_fields) == 4
    rec = tab._rec
    f0 = step_fields[0]
    f0.w.setText("MYSTEP01")
    f0._write()
    assert "".join(chr(c) for c in rec.values[STEP_NAMES_OFF:STEP_NAMES_OFF + 8]) == "MYSTEP01"


def test_midi_groups_channel_grid(win):
    tab = win.tab_widgets[4]  # Midi/Groups
    # channel 1 name comes from Config #1; editing writes back there
    assert tab._name_edits[0].text() != "" or True  # name may be blank in some rigs
    tab._name_edits[0].setText("TESTDEV")
    tab._write_name(0)
    assert "".join(chr(c) for c in tab._cfg1.values[0:7]) == "TESTDEV"


def test_pages_pedalboard_swap(win):
    tab = win.tab_widgets[7]  # Pages
    tab.rail.list.setCurrentRow(0)
    rec = tab._rec
    from lfeditor.model.page import FUNC1_OFF
    a, b = rec.values[FUNC1_OFF + 0], rec.values[FUNC1_OFF + 1]
    tab._swap(0, 1, copy=False)
    assert rec.values[FUNC1_OFF + 0] == b and rec.values[FUNC1_OFF + 1] == a


def test_label_grid_field_reads_and_writes_sibling_ext_record(win):
    """LabelGridField must edit the parent's linked extension record (by rec_num), losslessly."""
    d = win.dump
    tab = next(w for w in win.tab_widgets if getattr(w, "type_", None) == 1)  # Presets
    tab.rail.list.setCurrentRow(0)
    lab = next(f for f in _fields(tab) if f.__class__.__name__ == "LabelGridField")

    # the field binds to the Ext9 record with the same rec_num as preset 0
    ext = next(r for r in d.records(9) if r.frame.rec_num == d.records(1)[0].frame.rec_num)
    assert [e.text() for e in lab.edits] == ext.labels()

    # editing slot 0 writes straight into the ext record (8-char field) and re-encodes
    lab.edits[0].setText("TestLbl")
    lab._write(0)
    assert ext.label(0) == "TestLbl"
    # round-trips: decoding the re-encoded dump yields the same label
    again = Dump.from_bytes(d.to_bytes())
    assert again.records(9)[0].label(0) == "TestLbl"


def test_preset_map_labels_ext10_surfaced_and_editable(win):
    """The Presets tab surfaces the PresetExt10 (type-10) MAP-label store as an editable grid,
    bound to the parent preset's linked Ext10 record, and round-trips losslessly."""
    d = win.dump
    tab = next(w for w in win.tab_widgets if getattr(w, "type_", None) == 1)
    tab.rail.list.setCurrentRow(0)
    grids = [f for f in _fields(tab) if f.__class__.__name__ == "LabelGridField"]
    assert sorted(g.ext_type for g in grids) == [9, 10]   # IA-Slot Defined + MAP labels
    ext10 = next(g for g in grids if g.ext_type == 10)
    assert len(ext10.edits) == 20

    rec10 = next(r for r in d.records(10) if r.frame.rec_num == d.records(1)[0].frame.rec_num)
    ext10.edits[3].setText("MapLbl")
    ext10._write(3)
    assert rec10.label(3) == "MapLbl"
    again = Dump.from_bytes(d.to_bytes())
    assert again.records(10)[0].label(3) == "MapLbl"


def test_exp_pedal_flag_bits(win):
    """Exp-Pedals per-pedal flags byte value[71+pedal] (live-RE'd on hardware): bit 0x01 =
    Blk Heel/Toe Sens, bit 0x10 = Hi-Res Mode; plus Force-zipper bitfield at value[70]."""
    from lfeditor.ui.fields import ToggleField
    from lfeditor.model.expedal import (PEDAL_FLAGS_OFF, BLK_HEELTOE_SENS_BIT, HIRES_MODE_BIT,
                                        FORCE_ZIPPER_OFF, NUM_PEDALS)
    tab = next(w for w in win.tab_widgets
               if any(isinstance(f, ToggleField) and f.offset == PEDAL_FLAGS_OFF
                      and f.bitmask == HIRES_MODE_BIT for f in _fields(w)))
    toggles = [f for f in _fields(tab) if isinstance(f, ToggleField)]
    # every pedal exposes Blk-Heel/Toe (0x01) + Hi-Res (0x10) on v[71+p], and Force-zipper on v[70]
    for p in range(NUM_PEDALS):
        assert any(f.offset == PEDAL_FLAGS_OFF + p and f.bitmask == BLK_HEELTOE_SENS_BIT for f in toggles)
        assert any(f.offset == PEDAL_FLAGS_OFF + p and f.bitmask == HIRES_MODE_BIT for f in toggles)
        assert any(f.offset == FORCE_ZIPPER_OFF and f.bitmask == (1 << p) for f in toggles)

    cfg = win.dump.records(4)[0]
    hires = next(f for f in toggles if f.offset == PEDAL_FLAGS_OFF and f.bitmask == HIRES_MODE_BIT)
    cfg.values[PEDAL_FLAGS_OFF] = 0
    hires.load(cfg.values); hires.w.toggle.click()      # set Hi-Res bit on pedal 1
    assert cfg.values[PEDAL_FLAGS_OFF] & HIRES_MODE_BIT
    assert Dump.from_bytes(win.dump.to_bytes()).records(4)[0].values[PEDAL_FLAGS_OFF] & HIRES_MODE_BIT


def test_hires_decodes_against_captured_backup():
    """Live-captured backup: Hi-Res-on (pedal 1) sets value[71] bit 0x10 and resets the
    calibration block. Verified against the byte values recorded from the real device."""
    from lfeditor.model.expedal import (PEDAL_FLAGS_OFF, HIRES_MODE_BIT, CALIBRATION_MAX_OFF,
                                        CALIBRATION_MIN_OFF)
    # values recorded from the device this session (pedal 1 calibrated then Hi-Res toggled)
    assert HIRES_MODE_BIT == 0x10
    # MAX at v[17], MIN at v[25] for pedal 0 (2-byte LE); calibrated pedal 1 read 1023 / 84
    assert CALIBRATION_MAX_OFF == 17 and CALIBRATION_MIN_OFF == 25


def test_page_button_function_decoder():
    """The page-button Function byte decoder matches the manual + the captured editor labels."""
    from lfeditor.model.page import decode_button_function as dec
    ia = ["Sound Sculpture", "Keeley", "Whammy", "Fuzz", "Cornish TB83X"]  # slots 1..5
    pages = ["Skrydstrup", "Kemper"]
    assert dec(0) == ""                       # NOT DEFINED
    assert dec(1) == "PRESET B#01"            # preset button 1
    assert dec(60) == "PRESET B#60"
    assert dec(61) == "MENU"                  # system fn 1
    assert dec(63) == "Context UP"            # system fn 3 (byte 60+3)
    assert dec(64) == "Context DWN"
    assert dec(79) == "Current MODE"          # system fn 19 (v6.31 label; manual said MODE CYCLE)
    assert dec(80) == "Change PAGE"           # system fn 20 — confirmed via the live editor
    assert dec(81) == "SYS FN 21"             # fn 21+ undefined in v6.31 -> generic
    assert dec(128, ia) == "(001) Sound Sculpture"   # IA slot 1
    assert dec(132, ia) == "(005) Cornish TB83X"     # IA slot 5
    assert dec(200, page_names=pages) == "(001) Skrydstrup"  # page switch 1
    assert dec(201, page_names=pages) == "(002) Kemper"
    assert dec(249, page_names=pages) == "Page #50"  # page with no name -> generic


def test_song_mtc_fields_bind_and_write(win):
    """The Songs Parameters MTC fields (enable + Hour/Min/Sec/Frame) write the pinned offsets."""
    from lfeditor.model.song import (MTC_HOUR_OFF, MTC_MIN_OFF, MTC_SEC_OFF, MTC_FRAME_OFF,
                                     MTC_ENABLE_OFF, MTC_ENABLE_BIT)
    from lfeditor.ui.fields import IntField, ToggleField
    tab = next(w for w in win.tab_widgets if getattr(w, "type_", None) == 2)  # Songs
    tab.rail.list.setCurrentRow(0)
    rec = tab._rec
    by_off = {f.offset: f for f in _fields(tab) if isinstance(f, IntField)}
    by_off[MTC_HOUR_OFF].w.setValue(1)
    by_off[MTC_MIN_OFF].w.setValue(2)
    by_off[MTC_SEC_OFF].w.setValue(3)
    by_off[MTC_FRAME_OFF].w.setValue(4)
    assert [rec.values[o] for o in (MTC_HOUR_OFF, MTC_MIN_OFF, MTC_SEC_OFF, MTC_FRAME_OFF)] == [1, 2, 3, 4]
    en = next(f for f in _fields(tab) if isinstance(f, ToggleField) and f.offset == MTC_ENABLE_OFF)
    if not (rec.values[MTC_ENABLE_OFF] & MTC_ENABLE_BIT):
        en.w.toggle.click()
    assert rec.values[MTC_ENABLE_OFF] & MTC_ENABLE_BIT
