"""Frames recovered from the original v6.31 editor binary (static analysis; not hardware-confirmed)."""
import pytest

from lfeditor.comms import protocol as P

ID = P.MODEL_FOOT  # 0x7C


def test_exact_frames():
    assert P.reset_config_frame() == bytes([0xF0, 0, 0, ID, 0x0F, 0x0F, 0xD0, 0, 0, 0, 0, 0xF7])
    assert P.reset_factory_frame() == bytes([0xF0, 0, 0, ID, 0x0F, 0x0F, 0xD1, 0, 0, 0, 0, 0xF7])
    assert P.thru_mode_start_frame() == bytes([0xF0, 0, 0, ID, 0x0F, 0x0F, 0xCB, 0xF7])
    assert P.simulator_start_frame() == bytes([0xF0, 0, 0, ID, 0x0F, 0x0F, 0xCF, 0xF7])
    assert P.internal_data_update_frame() == bytes([0xF0, 0, 0, ID, 0x0F, 0x0F, 0x72, 0x0A, 0xF7])


def test_simulator_start_is_the_usb_midi_stream_start_byte():
    assert P.simulator_start_frame() == P.usb_midi_stream_start_frame()


def test_model_byte_is_parameterised():
    assert P.reset_config_frame(P.MODEL_ROUTER)[3] == P.MODEL_ROUTER


@pytest.mark.parametrize("get_cmd,set_cmd", [
    (0x05, 0x69),  # Presets
    (0x06, 0x6A),  # IA-Slots
    (0x07, 0x6B),  # Pages
    (0x08, 0x6C),  # Songs
    (0x09, 0x6D),  # Set-Lists
    (0x0A, 0x6E),  # Sysex
    (0x0C, 0x70),  # IA-Maps
    (0x0D, 0x71),  # IA labels (Preset ext 9)
    (0x0E, 0x72),  # firmware / internal data
    (0x0F, 0x73),  # MAP labels (Preset ext 10)
    (0x10, 0x74),  # Song preset labels (Song ext 11)
])
def test_bulk_write_opcode_is_read_plus_0x64(get_cmd, set_cmd):
    """Every `Set_All_*` literal in the original equals its `Get_All_*` opcode + 0x64."""
    assert P.bulk_set_cmd(get_cmd) == set_cmd


def test_internal_data_checksum_and_ack():
    block = bytes((i * 31) & 0xFF for i in range(24_000))
    cs = P.internal_data_checksum(block)
    assert cs == sum(block) & 0xFFFF
    assert P.internal_data_ack_ok(bytes([cs >> 8, cs & 0xFF]), block)
    assert not P.internal_data_ack_ok(bytes([cs >> 8, (cs + 1) & 0xFF]), block)
    assert not P.internal_data_ack_ok(b"\x00", block) and not P.internal_data_ack_ok(b"", block)


def test_no_app_code_sends_the_destructive_frames():
    import pathlib
    root = pathlib.Path(P.__file__).resolve().parent.parent
    for path in root.rglob("*.py"):
        if path.name == "protocol.py":
            continue
        text = path.read_text()
        assert "reset_config_frame" not in text and "reset_factory_frame" not in text, path
