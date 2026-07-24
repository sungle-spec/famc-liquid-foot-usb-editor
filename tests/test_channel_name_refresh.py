"""Renaming a MIDI channel on Midi/Groups must show up immediately in other tabs' MIDI-command
pickers (Presets/Songs/IA-Slot's CommandTableField, Exp Pedals' ChannelNameField) -- those fields
cache the Config#1 channel-name list at the last set_dump()/set_context(), so a live rename needs
MainWindow.refresh_channel_names() to propagate without a reload."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_qsettings(monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    import lfeditor.ui.app as app_module
    ini = str(tmp_path / "settings.ini")
    monkeypatch.setattr(app_module, "QSettings", lambda *a, **k: QSettings(ini, QSettings.IniFormat))


@pytest.fixture()
def win(qapp, isolated_qsettings):
    from lfeditor.ui.app import MainWindow
    w = MainWindow()
    w.load_factory("Factory_DefaultsPro.syx", "Pro+")
    return w


from lfeditor.ui.app import TAB_ORDER


def _tab(win, title):
    return win.tab_widgets[TAB_ORDER.index(title)]


def test_renaming_channel_on_midi_groups_updates_presets_command_picker(win):
    midi_groups = _tab(win, "Midi/Groups")
    presets = _tab(win, "Presets")

    ch = 14   # channel 15 (0-based index 14), matches the reported "LR+" rename
    midi_groups._name_edits[ch].setText("LR+")
    midi_groups._write_name(ch)

    cmd_field = next(f for f in presets._all_fields if hasattr(f, "midis"))
    assert cmd_field._chan_names[ch] == "15: LR+"
    assert cmd_field.midis[0].itemText(ch) == "15: LR+"


def test_renaming_channel_on_midi_groups_updates_exp_pedals_chan_picker(win):
    midi_groups = _tab(win, "Midi/Groups")
    exp_pedals = _tab(win, "Exp Pedals")

    ch = 14
    midi_groups._name_edits[ch].setText("LR+")
    midi_groups._write_name(ch)

    chan_field = next(f for f in exp_pedals._all_fields if hasattr(f, "_names") and not hasattr(f, "midis"))
    assert chan_field._names[ch] == "LR+"
