"""LF+ firmware image codec — the on-wire sysex format, fully decoded.

Recovered 2026-11-09 and verified on **332/332** FAMC images (v3.34 -> v6.32, all five models) with
a byte-exact decode -> encode round trip (tests/test_firmware_codec.py). See docs/FIRMWARE_NOTES.md.

One sysex frame ``F0 00 00 7C 08 06 <body> F7`` where ``body`` is:

====  =====================================================================================
13 B  header: ``01 00 00`` | block count (3 nibbles, hi first) | ``00 00 00 00`` |
      major version (1 nibble) | minor version (1 raw byte, decimal, e.g. 0x20 = 32) |
      model letter (1 raw ASCII byte)
 N    payload: the PIC18 program image as nibbles — every image byte is sent high nibble
      first, each nibble XORed with 0x5. The bytes are 16-bit words, **high byte first**
      (the MCU is little-endian, so ``memory`` below swaps each pair).
 4    trailer: 16-bit sum of the payload nibbles (raw, i.e. before any XOR), hi nibble first
====  =====================================================================================

``block count * 128`` is the decoded image length in bytes. The MCU is a PIC18 (128 KB class):
decoded images start with the reset/interrupt ``GOTO`` vectors and contain the unit's LCD text.
The boot-loader region is not part of the image. Model letters: Mini ``F``, 12 ``J``,
12+ ``K``, JR+ ``L``, Pro+ ``H``.
"""
from __future__ import annotations

from dataclasses import dataclass

FRAME_PREFIX = bytes([0xF0, 0x00, 0x00, 0x7C, 0x08, 0x06])
HEADER_LEN = 13
TRAILER_LEN = 4
BLOCK_BYTES = 128
NIBBLE_XOR = 0x5

MODEL_LETTERS = {"F": "Mini", "J": "12", "K": "12+", "L": "JR+", "H": "Pro+"}
LETTER_FOR_MODEL = {v: k for k, v in MODEL_LETTERS.items()}


class FirmwareFormatError(ValueError):
    """The bytes are not a well-formed LF+ firmware frame."""


@dataclass(frozen=True)
class FirmwareImage:
    major: int
    minor: int
    model_letter: str
    blocks: int
    memory: bytes          # PIC18 program memory image, little-endian byte order
    trailer: int           # checksum as stored in the file
    computed_checksum: int  # 16-bit nibble sum recomputed from the payload

    @property
    def version(self) -> str:
        return f"{self.major}.{self.minor:02d}"

    @property
    def model(self) -> str | None:
        return MODEL_LETTERS.get(self.model_letter)

    @property
    def checksum_ok(self) -> bool:
        return self.trailer == self.computed_checksum

    @property
    def length_ok(self) -> bool:
        return len(self.memory) == self.blocks * BLOCK_BYTES

    @property
    def words_be(self) -> bytes:
        """The image as it travels on the wire: 16-bit words, high byte first."""
        return _swap_pairs(self.memory)


def _swap_pairs(b: bytes) -> bytes:
    out = bytearray(len(b))
    out[0::2], out[1::2] = b[1::2], b[0::2]
    if len(b) % 2:           # odd tail has no partner; keep it in place
        out[-1] = b[-1]
    return bytes(out)


def decode(data: bytes) -> FirmwareImage:
    """Parse a firmware ``.syx`` frame. Raises FirmwareFormatError if it isn't one; a parsed
    image can still have ``checksum_ok`` / ``length_ok`` False (callers decide what to do)."""
    if not data.startswith(FRAME_PREFIX) or data[-1:] != b"\xf7":
        raise FirmwareFormatError("not an LF+ firmware frame (F0 00 00 7C 08 06 … F7)")
    body = data[len(FRAME_PREFIX):-1]
    if len(body) < HEADER_LEN + TRAILER_LEN:
        raise FirmwareFormatError("frame too short")
    hdr, payload, tr = body[:HEADER_LEN], body[HEADER_LEN:-TRAILER_LEN], body[-TRAILER_LEN:]
    if hdr[:3] != b"\x01\x00\x00" or hdr[6:10] != b"\x00\x00\x00\x00":
        raise FirmwareFormatError("unrecognised firmware header")
    if any(n > 0x0F for n in hdr[:11]) or any(n > 0x0F for n in tr) or any(n > 0x0F for n in payload):
        raise FirmwareFormatError("payload is not nibble data")
    if len(payload) % 2:
        raise FirmwareFormatError("odd number of payload nibbles")
    if hdr[11] > 0x7F or not 0x20 <= hdr[12] <= 0x7E:
        raise FirmwareFormatError("bad version/model bytes in header")
    words = bytes(((payload[i] ^ NIBBLE_XOR) << 4) | (payload[i + 1] ^ NIBBLE_XOR)
                  for i in range(0, len(payload), 2))
    return FirmwareImage(
        major=hdr[10], minor=hdr[11], model_letter=chr(hdr[12]),
        blocks=(hdr[3] << 8) | (hdr[4] << 4) | hdr[5],
        memory=_swap_pairs(words),
        trailer=(tr[0] << 12) | (tr[1] << 8) | (tr[2] << 4) | tr[3],
        computed_checksum=sum(payload) & 0xFFFF,
    )


def encode(memory: bytes, major: int, minor: int, model_letter: str) -> bytes:
    """Build a firmware ``.syx`` frame from a PIC18 memory image. Pure packaging — it makes a
    *well-formed* frame; it says nothing about whether the code inside is safe to run."""
    if len(memory) % BLOCK_BYTES or not memory:
        raise FirmwareFormatError(f"image length must be a non-zero multiple of {BLOCK_BYTES}")
    blocks = len(memory) // BLOCK_BYTES
    if blocks > 0xFFF:
        raise FirmwareFormatError("image too large for a 12-bit block count")
    if not 0 <= major <= 0x0F or not 0 <= minor <= 0x7F:
        raise FirmwareFormatError("version out of range")
    if len(model_letter) != 1 or model_letter not in MODEL_LETTERS:
        raise FirmwareFormatError(f"unknown model letter {model_letter!r}")
    words = _swap_pairs(memory)
    payload = bytearray()
    for b in words:
        payload.append((b >> 4) ^ NIBBLE_XOR)
        payload.append((b & 0x0F) ^ NIBBLE_XOR)
    csum = sum(payload) & 0xFFFF
    hdr = bytes([0x01, 0x00, 0x00, (blocks >> 8) & 0xF, (blocks >> 4) & 0xF, blocks & 0xF,
                 0, 0, 0, 0, major, minor, ord(model_letter)])
    tr = bytes([(csum >> 12) & 0xF, (csum >> 8) & 0xF, (csum >> 4) & 0xF, csum & 0xF])
    return FRAME_PREFIX + hdr + bytes(payload) + tr + b"\xf7"


def reencode(img: FirmwareImage) -> bytes:
    """Re-encode a parsed image with its own header fields (round-trip helper)."""
    return encode(img.memory, img.major, img.minor, img.model_letter)
