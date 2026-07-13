"""
Shared ASCII codec for the device's fixed-width, space-padded text fields.

The Liquid Foot stores every name and label as a fixed-length run of printable ASCII:
space-padded on the right, with non-printable bytes shown (and written) as spaces. Both the
model records and the UI field editors read and write these runs, so the encode/decode pair
lives in one place instead of being re-implemented at every call site.
"""
from __future__ import annotations


def decode_ascii(values, start: int, length: int) -> str:
    """Decode `length` bytes at `start` as printable ASCII, with trailing spaces stripped."""
    chars = values[start:start + length]
    return "".join(chr(c) if 32 <= c < 127 else " " for c in chars).rstrip()


def encode_ascii(text: str, length: int) -> list[int]:
    """Encode `text` into exactly `length` bytes: space-padded, non-printables mapped to 32."""
    padded = (text + " " * length)[:length]
    return [ord(ch) if 32 <= ord(ch) < 127 else 32 for ch in padded]
