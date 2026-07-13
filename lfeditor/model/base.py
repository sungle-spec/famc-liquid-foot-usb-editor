"""
Model records: a thin typed layer over `codec.frame.Frame`.

A `Record` wraps one frame and exposes typed views onto its decoded `values`. Edits write
straight back into `frame.values`, so `frame.to_bytes()` stays lossless for every field we
have *not* mapped (the v6 extension bytes round-trip untouched). This mirrors the Router
editor's surgical-write philosophy.
"""
from __future__ import annotations

from ..codec.frame import Frame
from ..text import decode_ascii, encode_ascii

NAME_LEN = 16  # full name: 16 ASCII chars at values[0:16]
NICK_OFF = 16  # nick name: 8 ASCII chars at values[16:24] (v6 addition)
NICK_LEN = 8


class Record:
    """Base wrapper. Name-bearing records (Preset/Song/Setlist/IASwitch/IAMap/SysexMsg/Page)
    carry a 16-char **full name** at values[0:16] and an 8-char **nick name** at
    values[16:24] — verified across all types in the v6.31 dumps. Type-specific data
    follows from value 24 (precise offsets mapped per type via live-editor diffing)."""

    has_name = True

    def __init__(self, frame: Frame):
        self.frame = frame

    # --- identity ---
    @property
    def type(self) -> int:
        return self.frame.type

    @property
    def number(self) -> int:
        """1-based record number as shown in the editor (device stores 0-based)."""
        return self.frame.rec_num + 1

    @property
    def values(self) -> list[int]:
        return self.frame.values

    # --- name ---
    @property
    def name(self) -> str:
        if not self.has_name:
            return ""
        return decode_ascii(self.frame.values, 0, NAME_LEN)

    @name.setter
    def name(self, text: str) -> None:
        self._write_ascii(0, NAME_LEN, text)

    # --- nick name (8 chars) ---
    @property
    def nick(self) -> str:
        if not self.has_name:
            return ""
        return decode_ascii(self.frame.values, NICK_OFF, NICK_LEN)

    @nick.setter
    def nick(self, text: str) -> None:
        self._write_ascii(NICK_OFF, NICK_LEN, text)

    def _write_ascii(self, off: int, length: int, text: str) -> None:
        if not self.has_name:
            raise AttributeError(f"{type(self).__name__} has no name field")
        self.frame.values[off:off + length] = encode_ascii(text, length)

    def __repr__(self) -> str:
        n = f" {self.name!r}" if self.has_name else ""
        return f"<{type(self).__name__} #{self.number}{n}>"
