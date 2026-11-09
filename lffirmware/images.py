"""Firmware image validation.

A genuine LF+ firmware file is ONE sysex frame: F0 00 00 7C 08 06 <payload…> F7 — command 0x08
(firmware upload), sub-command 0x06, payload nibble-encoded except a couple of raw header bytes.
There is one image per hardware model, and **file size does NOT identify the model** (sizes
collide across versions of different models), so identity comes from the SHA-256 allowlist of
known FAMC releases (known_images.py) plus FAMC's own filename convention (LF+12+_FIRM.syx …).
"""
from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass, field

from . import codec
from .known_images import KNOWN_IMAGES

MODELS = ("Mini", "12", "12+", "JR+", "Pro+")

HEADER = bytes([0xF0, 0x00, 0x00, 0x7C, 0x08, 0x06])

# FAMC's filename convention, longest prefix first so "LF+12+" wins over "LF+12".
_NAME_PREFIXES = (
    ("LF+MINI", "Mini"),
    ("LF+PRO+", "Pro+"),
    ("LF+JR+", "JR+"),
    ("LF+12+", "12+"),
    ("LF+12", "12"),
)


@dataclass
class ImageReport:
    path: str
    size: int = 0
    sha256: str = ""
    frame_ok: bool = False          # F0 00 00 7C 08 06 … single F7 terminator
    data_bytes_ok: bool = False     # every payload byte is valid sysex data (<= 0x7F)
    nibble_fraction: float = 0.0    # sanity: genuine images are >99% nibble bytes
    known_model: str | None = None  # from the SHA-256 allowlist
    known_version: str | None = None
    filename_model: str | None = None  # from FAMC's LF+<MODEL>_FIRM naming
    # Decoded from the image itself (lffirmware.codec) — authoritative, unlike the filename.
    header_model: str | None = None    # model letter in the header (F/J/K/L/H -> Mini/12/12+/JR+/Pro+)
    version: str | None = None         # "6.32", from the header
    structure_ok: bool = False         # header parses AND length == blocks*128 AND checksum matches
    errors: list[str] = field(default_factory=list)

    @property
    def is_known_good(self) -> bool:
        return (self.frame_ok and self.data_bytes_ok and self.structure_ok
                and self.known_model is not None)

    @property
    def is_plausible(self) -> bool:
        """Structurally valid (incl. its own length field and checksum) but not in the allowlist —
        needs an explicit user override."""
        return (self.frame_ok and self.data_bytes_ok and self.nibble_fraction > 0.99
                and self.structure_ok)

    def model_for(self, selected_model: str) -> bool:
        """Does this image match the model the user selected? Known hash first, then the model
        letter inside the image, and only then the (user-editable) filename."""
        if self.known_model is not None:
            return self.known_model == selected_model
        if self.header_model is not None:
            return self.header_model == selected_model
        return self.filename_model == selected_model


def model_from_filename(name: str) -> str | None:
    up = name.upper()
    for prefix, model in _NAME_PREFIXES:
        if up.startswith(prefix):
            return model
    return None


def validate_image(path: str | pathlib.Path) -> ImageReport:
    p = pathlib.Path(path)
    rep = ImageReport(path=str(p))
    try:
        data = p.read_bytes()
    except OSError as exc:
        rep.errors.append(f"cannot read file: {exc}")
        return rep

    rep.size = len(data)
    rep.sha256 = hashlib.sha256(data).hexdigest()
    rep.filename_model = model_from_filename(p.name)

    if len(data) < 1024:
        rep.errors.append("file is far too small to be an LF+ firmware image")
        return rep
    if not data.startswith(HEADER):
        rep.errors.append(
            "missing the LF+ firmware header (F0 00 00 7C 08 06) — this is not an LF+ "
            "firmware image (backups start F0 00 00 7C ?? 01)"
        )
    if data[-1] != 0xF7 or data.count(0xF7) != 1:
        rep.errors.append("not a single sysex frame (expected exactly one F7, at end of file)")
    rep.frame_ok = not rep.errors

    body = data[6:-1] if rep.frame_ok else b""
    if body:
        bad = sum(b > 0x7F for b in body)
        rep.data_bytes_ok = bad == 0
        if bad:
            rep.errors.append(f"{bad} payload bytes are not valid sysex data (>0x7F)")
        rep.nibble_fraction = sum(b <= 0x0F for b in body) / len(body)
        if rep.nibble_fraction <= 0.99:
            rep.errors.append("payload is not nibble-encoded like genuine LF+ firmware")

    # Verify the image's own header, length field and checksum (format recovered 2026-11-09).
    try:
        img = codec.decode(data)
    except codec.FirmwareFormatError as exc:
        rep.errors.append(f"firmware structure invalid: {exc}")
    else:
        rep.header_model, rep.version = img.model, img.version
        if img.model is None:
            rep.errors.append(f"unknown model letter {img.model_letter!r} in the firmware header")
        if not img.length_ok:
            rep.errors.append(
                f"header says {img.blocks * codec.BLOCK_BYTES:,} image bytes but the payload "
                f"holds {len(img.memory):,} — truncated or corrupt")
        if not img.checksum_ok:
            rep.errors.append(
                f"payload checksum mismatch (file says {img.trailer:#06x}, computed "
                f"{img.computed_checksum:#06x}) — corrupt or tampered image")
        rep.structure_ok = img.model is not None and img.length_ok and img.checksum_ok
        if rep.filename_model and img.model and rep.filename_model != img.model:
            rep.errors.append(
                f"filename says {rep.filename_model} but the image header says {img.model} — "
                f"trust the header, not the name")

    known = KNOWN_IMAGES.get(rep.sha256)
    if known:
        rep.known_model, rep.known_version, _size = known
        if rep.filename_model and rep.filename_model != rep.known_model:
            rep.errors.append(
                f"filename says {rep.filename_model} but the file's contents are the "
                f"known {rep.known_model} v{rep.known_version} image — the file was renamed; "
                f"trust the contents, not the name"
            )
    return rep


def describe(rep: ImageReport) -> str:
    lines = [f"file    : {rep.path}", f"size    : {rep.size:,} bytes", f"sha256  : {rep.sha256}"]
    if rep.is_known_good:
        lines.append(f"identity: KNOWN GOOD — FAMC {rep.known_model} firmware v{rep.known_version}")
    elif rep.is_plausible:
        lines.append(
            "identity: UNKNOWN image (structurally valid, but not one of the "
            f"{len(KNOWN_IMAGES)} known FAMC releases) — flashing it requires an explicit override"
        )
        if rep.filename_model:
            lines.append(f"filename suggests model: {rep.filename_model}")
    else:
        lines.append("identity: NOT a valid LF+ firmware image")
    if rep.version or rep.header_model:
        lines.append(f"header  : firmware v{rep.version or '?'} for LF+ {rep.header_model or '?'}"
                     f"; length + checksum {'OK' if rep.structure_ok else 'NOT OK'}")
    for e in rep.errors:
        lines.append(f"problem : {e}")
    return "\n".join(lines)
