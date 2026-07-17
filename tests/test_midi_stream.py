"""Raw LF+ UART MIDI parser tests; no serial or MIDI device is required."""
from lfeditor.comms.midi_stream import (
    RawMidiStreamParser,
    is_famc_protocol_frame,
    is_forwardable_sysex,
)


def test_complete_control_change():
    parser = RawMidiStreamParser()
    assert parser.feed(bytes([0xB2, 0x45, 0x00])) == [bytes([0xB2, 0x45, 0x00])]


def test_program_change():
    parser = RawMidiStreamParser()
    assert parser.feed(bytes([0xC2, 0x01])) == [bytes([0xC2, 0x01])]


def test_note_on_and_pitch_bend():
    parser = RawMidiStreamParser()
    assert parser.feed(bytes([0x91, 60, 100, 0xE4, 0x01, 0x7F])) == [
        bytes([0x91, 60, 100]),
        bytes([0xE4, 0x01, 0x7F]),
    ]


def test_all_required_channel_message_lengths():
    parser = RawMidiStreamParser()
    chunk = bytes([
        0x80, 60, 0,       # Note Off
        0xA1, 61, 20,      # Poly Pressure
        0xD2, 45,          # Channel Pressure
    ])
    assert parser.feed(chunk) == [
        bytes([0x80, 60, 0]),
        bytes([0xA1, 61, 20]),
        bytes([0xD2, 45]),
    ]


def test_fragmented_message_across_reads():
    parser = RawMidiStreamParser()
    assert parser.feed(bytes([0xB0])) == []
    assert parser.feed(bytes([7])) == []
    assert parser.feed(bytes([100])) == [bytes([0xB0, 7, 100])]


def test_multiple_messages_in_one_chunk():
    parser = RawMidiStreamParser()
    assert parser.feed(bytes([0xB2, 0, 0, 0xB2, 32, 0, 0xC2, 1])) == [
        bytes([0xB2, 0, 0]),
        bytes([0xB2, 32, 0]),
        bytes([0xC2, 1]),
    ]


def test_running_status_across_chunks():
    parser = RawMidiStreamParser()
    assert parser.feed(bytes([0xB3, 10, 20, 11])) == [bytes([0xB3, 10, 20])]
    assert parser.feed(bytes([21, 12, 22])) == [
        bytes([0xB3, 11, 21]),
        bytes([0xB3, 12, 22]),
    ]


def test_realtime_bytes_do_not_break_running_status_or_partial_message():
    parser = RawMidiStreamParser()
    assert parser.feed(bytes([0xB5, 1, 0xF8, 2, 0xFA, 3, 4, 0xFF])) == [
        bytes([0xF8]),
        bytes([0xB5, 1, 2]),
        bytes([0xFA]),
        bytes([0xB5, 3, 4]),
    ]


def test_safe_realtime_is_forwarded_once_and_unsafe_realtime_is_filtered():
    parser = RawMidiStreamParser()
    assert parser.feed(bytes([0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF])) == [
        bytes([0xF8]),
        bytes([0xFA]),
        bytes([0xFB]),
        bytes([0xFC]),
        bytes([0xFE]),
    ]


def test_famc_sysex_frame_is_filtered_and_parser_recovers():
    parser = RawMidiStreamParser()
    # Realtime-looking F8 inside a FAMC frame is raw protocol payload, not musical MIDI.
    famc = bytes.fromhex("f000007c0f0fc9f800000000f7")
    assert parser.feed(famc + bytes([0xC2, 7])) == [bytes([0xC2, 7])]


def test_ordinary_sysex_is_forwarded_across_fragmented_reads():
    parser = RawMidiStreamParser()
    assert parser.feed(bytes.fromhex("f07d0102")) == []
    assert parser.feed(bytes.fromhex("0304f7")) == [bytes.fromhex("f07d01020304f7")]


def test_known_famc_frame_shapes_and_invalid_sysex_are_filtered():
    parser = RawMidiStreamParser()
    frames = (
        bytes.fromhex("f000007c0f0f05f7"),  # host read/control
        bytes.fromhex("f005007c06204b01f7"),  # device reply
        bytes.fromhex("f009f7"),  # write ACK
        bytes.fromhex("f07d01f802f7"),  # non-7-bit raw payload: ambiguous/invalid MIDI SysEx
    )
    assert parser.feed(b"".join(frames)) == []
    assert all(is_famc_protocol_frame(frame) for frame in frames[:3])
    assert not is_forwardable_sysex(frames[3])


def test_famc_looking_user_sysex_is_conservatively_filtered():
    # It may be user-programmed, but it is indistinguishable from editor/control protocol.
    frame = bytes.fromhex("f000007c0102f7")
    assert is_famc_protocol_frame(frame)
    assert not is_forwardable_sysex(frame)
    assert RawMidiStreamParser().feed(frame) == []


def test_unterminated_sysex_is_bounded_and_channel_status_resynchronises():
    parser = RawMidiStreamParser(max_sysex_bytes=16)
    assert parser.feed(bytes([0xF0]) + bytes([1]) * 10_000) == []
    assert parser.buffered_byte_count <= 16
    assert parser.feed(bytes([0x90, 64, 127])) == [bytes([0x90, 64, 127])]


def test_system_common_and_garbage_are_filtered():
    parser = RawMidiStreamParser()
    assert parser.feed(bytes([1, 2, 0xF1, 3, 0xF7, 0xC0, 9])) == [bytes([0xC0, 9])]
