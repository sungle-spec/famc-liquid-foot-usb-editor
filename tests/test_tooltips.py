"""Curated hover tooltips (from the original editor) are wired onto our controls, per tab."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QWidget

ROOT = pathlib.Path(__file__).resolve().parent.parent
RJM = str(ROOT / "reference" / "sysex_dumps" / "RJM.syx")

from conftest import requires_rjm
pytestmark = requires_rjm


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_help_text_is_populated():
    from lfeditor.ui.help_text import FIELD_HELP, SECTION_HELP, tooltip_for, section_tooltip
    total = sum(len(v) for v in FIELD_HELP.values())
    assert total >= 77
    for tab in FIELD_HELP.values():
        for v in tab.values():
            assert len(v) > 10 and not v.startswith(("jm", "Combo", "Popup"))
    # per-tab scoping: the same generic label means different things on different tabs
    assert tooltip_for("Expression Pedals", "Type").startswith("Define the Type of Pedal")
    assert tooltip_for("Preset", "Act as IA-Slot (vs Preset)").startswith("This will make the preset act")
    assert tooltip_for("Preset", "Type") == ""        # 'Type' is not a Preset field
    assert tooltip_for("nope", "nope") == ""
    assert "Preset Defined Label" in section_tooltip("Preset", "IA-Slot Defined Labels")


@pytest.mark.parametrize("tab_title", ["Preset", "Set-List", "IA-Slot", "Sysex Msg",
                                       "Expression Pedals", "Global Settings", "Colours"])
def test_tab_tooltips_attached(qapp, tab_title):
    from lfeditor.ui.app import MainWindow
    from lfeditor.ui.help_text import FIELD_HELP, SECTION_HELP
    w = MainWindow(); w.load(RJM)
    tab = [t for t in w.tab_widgets
           if getattr(getattr(t, "spec", None), "title", None) == tab_title][0]
    present = {c.toolTip() for c in tab.findChildren(QWidget) if c.toolTip()}
    expected = set(FIELD_HELP.get(tab_title, {}).values()) | set(SECTION_HELP.get(tab_title, {}).values())
    for text in expected:
        assert text in present, f"[{tab_title}] tooltip not wired: {text[:40]!r}"


def test_toggle_switches_show_detail_not_name(qapp):
    # a curated toggle's inner rocker switch must carry the full help, not its caption name —
    # otherwise hovering the switch shadows the detailed tooltip with the function name.
    from lfeditor.ui.app import MainWindow
    from lfeditor.ui.components import RockerSwitch, ToggleSwitch
    w = MainWindow(); w.load(RJM)
    ps = [t for t in w.tab_widgets
          if getattr(getattr(t, "spec", None), "title", None) == "Preset"][0]
    rockers = ps.findChildren(RockerSwitch) + ps.findChildren(ToggleSwitch)
    # no rocker shows a bare function name as its tooltip
    names = {"Act as IA-Slot (vs Preset)", "Allow multi-presses (process steps/reset)",
             "Resend globals", "Resend IA-slot states"}
    assert not any(r.toolTip() in names for r in rockers)
    # the multi-press rocker carries the detailed help
    assert any("allow multiple presses" in r.toolTip() for r in rockers)


@pytest.mark.parametrize("cls,key", [("PagesTab", "Pages"), ("MidiGroupsTab", "Midi/Groups")])
def test_custom_tab_tooltips_attached(qapp, cls, key):
    # Pages and Midi/Groups are custom widgets (no spec.title) — find them by type
    from lfeditor.ui.app import MainWindow
    from lfeditor.ui.help_text import FIELD_HELP, SECTION_HELP
    w = MainWindow(); w.load(RJM)
    tab = [t for t in w.tab_widgets if type(t).__name__ == cls][0]
    present = {c.toolTip() for c in tab.findChildren(QWidget) if c.toolTip()}
    expected = set(FIELD_HELP.get(key, {}).values()) | set(SECTION_HELP.get(key, {}).values())
    for text in expected:
        assert text in present, f"[{key}] tooltip not wired: {text[:40]!r}"
