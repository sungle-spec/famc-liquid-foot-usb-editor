"""
`Dump` — a whole-device backup: an ordered list of frames plus typed views.

`Dump.from_bytes(data).to_bytes()` is byte-identical to the input for every known dump and
factory file (see tests/). Editing a record's `.values` and re-serialising changes only the
bytes of that record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .frame import Frame, TYPE_NAMES, split_frames

if TYPE_CHECKING:
    from ..model import Record


@dataclass
class Dump:
    frames: list[Frame] = field(default_factory=list)
    #: bytes that appear between/around frames (none in real dumps; kept for fidelity)
    preamble: bytes = b""

    # --- construction ---
    @classmethod
    def from_bytes(cls, data: bytes) -> "Dump":
        raw_frames = split_frames(data)
        frames = [Frame.parse(f) for f in raw_frames]
        # capture any leading bytes before the first F0 (should be empty)
        first = data.find(0xF0)
        preamble = data[:first] if first > 0 else b""
        return cls(frames=frames, preamble=preamble)

    @classmethod
    def from_file(cls, path: str) -> "Dump":
        with open(path, "rb") as fh:
            return cls.from_bytes(fh.read())

    # --- serialisation ---
    def to_bytes(self) -> bytes:
        out = bytearray(self.preamble)
        for fr in self.frames:
            out += fr.to_bytes()
        return bytes(out)

    def to_file(self, path: str) -> None:
        with open(path, "wb") as fh:
            fh.write(self.to_bytes())

    # --- typed access ---
    def records(self, type_: int) -> list[Record]:
        from ..model import wrap  # lazy: avoids a codec<->model import cycle
        return [wrap(f) for f in self.frames if f.type == type_]

    @property
    def presets(self) -> list[Record]:
        return self.records(1)

    @property
    def songs(self) -> list[Record]:
        return self.records(2)

    @property
    def ia_switches(self) -> list[Record]:
        return self.records(3)

    @property
    def setlists(self) -> list[Record]:
        return self.records(5)

    @property
    def sysex_messages(self) -> list[Record]:
        return self.records(6)

    @property
    def pages(self) -> list[Record]:
        return self.records(7)

    @property
    def ia_maps(self) -> list[Record]:
        return self.records(8)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for fr in self.frames:
            key = TYPE_NAMES.get(fr.type, f"type{fr.type}")
            out[key] = out.get(key, 0) + 1
        return out

    def __repr__(self) -> str:
        return f"<Dump {len(self.frames)} frames {self.counts()}>"
