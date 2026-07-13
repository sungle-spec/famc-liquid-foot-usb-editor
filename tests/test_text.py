"""Unit tests for the shared fixed-width ASCII codec (lfeditor/text.py)."""
from lfeditor.text import decode_ascii, encode_ascii


def test_decode_strips_trailing_spaces():
    vals = list(b"Solo            ")  # 16 bytes, space-padded
    assert decode_ascii(vals, 0, 16) == "Solo"


def test_decode_honours_offset_and_length():
    vals = list(b"AAAABBBBBBBB")
    assert decode_ascii(vals, 4, 8) == "BBBBBBBB"


def test_decode_maps_nonprintable_to_space():
    vals = [0x00, ord("X"), 0xFF, ord("Y")]  # control, X, control, Y
    assert decode_ascii(vals, 0, 4) == " X Y"
    # a trailing non-printable becomes a space and is then stripped
    assert decode_ascii([ord("X"), 0x00], 0, 2) == "X"


def test_encode_pads_to_length():
    assert encode_ascii("Solo", 8) == list(b"Solo    ")


def test_encode_truncates_overlong():
    assert encode_ascii("0123456789", 8) == list(b"01234567")


def test_encode_maps_nonprintable_to_32():
    assert encode_ascii("a\tb", 4) == [ord("a"), 32, ord("b"), 32]


def test_round_trip_is_stable():
    for original in ("", "Delay", "Driven X", "12345678"):
        encoded = encode_ascii(original, 16)
        assert decode_ascii(encoded, 0, 16) == original.rstrip()
        # re-encoding the decoded form is idempotent
        assert encode_ascii(decode_ascii(encoded, 0, 16), 16) == encoded
