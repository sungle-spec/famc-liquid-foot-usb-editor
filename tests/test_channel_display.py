"""Global MIDI channel fields display 1..16 while storing firmware-compatible 0..15."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from lfeditor.model.config import MIDI_CHANNEL_OFF, EXTENDER_EXPANDER_CHAN_OFF
from lfeditor.ui.fields import IntField
from lfeditor.ui.specs import GLOBAL_TABS


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _global_field(label: str) -> IntField:
    spec = GLOBAL_TABS["Global"]
    return next(
        field
        for column in spec.columns
        for section in column
        for field in section.fields
        if isinstance(field, IntField) and field.label == label
    )


@pytest.mark.parametrize(
    ("label", "offset"),
    [
        ("MIDI channel", MIDI_CHANNEL_OFF),
        ("Expander via MIDI CHAN", EXTENDER_EXPANDER_CHAN_OFF),
    ],
)
def test_global_midi_channel_display_and_storage(qapp, label, offset):
    field = _global_field(label)
    widget = field.build()
    values = [0] * 250

    assert field.plus_one is True
    assert widget.minimum() == 1
    assert widget.maximum() == 16

    values[offset] = 0
    field.load(values)
    assert widget.value() == 1
    assert values[offset] == 0

    values[offset] = 15
    field.load(values)
    assert widget.value() == 16
    assert values[offset] == 15

    widget.setValue(1)
    assert values[offset] == 0
    widget.setValue(16)
    assert values[offset] == 15
