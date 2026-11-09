"""lffirmware.codec — the decoded LF+ firmware wire format (verified on 332 real images)."""
import glob
import pathlib
import re
import zipfile

import pytest

from lffirmware import codec
from lffirmware.cli import main as cli_main

REPO = pathlib.Path(__file__).resolve().parent.parent
FW = REPO / "reference" / "Liquid Foot" / "Firmware"
V632 = FW / "LF_PLUS_firmware_v6_32"
requires_archive = pytest.mark.skipif(
    not V632.exists(), reason="private FAMC firmware archive not present in this checkout")


# ---- synthetic (runs everywhere) ----

def test_encode_decode_roundtrip_and_fields():
    mem = bytes((i * 7 + 3) & 0xFF for i in range(128 * 5))
    frame = codec.encode(mem, 6, 32, "K")
    assert frame.startswith(codec.FRAME_PREFIX) and frame.endswith(b"\xf7")
    assert max(frame[1:-1]) <= 0x7F          # every data byte is valid sysex
    img = codec.decode(frame)
    assert (img.version, img.model, img.blocks) == ("6.32", "12+", 5)
    assert img.memory == mem and img.checksum_ok and img.length_ok
    assert codec.reencode(img) == frame


def test_wire_layout_is_nibble_xor5_words_high_byte_first():
    # memory 00 EF  ->  word 0xEF00 on the wire  ->  nibbles E,F,0,0 each XOR 5 -> B,A,5,5
    mem = bytes([0x00, 0xEF]) + bytes(126)
    payload = codec.encode(mem, 6, 32, "K")[6 + codec.HEADER_LEN:-codec.TRAILER_LEN - 1]
    assert list(payload[:4]) == [0xB, 0xA, 0x5, 0x5]
    assert all(n <= 0x0F for n in payload)


def test_header_and_trailer_layout():
    frame = codec.encode(bytes(1002 * 128), 6, 32, "K")        # the 12+ v6.32 block count
    body = frame[6:-1]
    assert body[:13] == bytes([1, 0, 0, 0x3, 0xE, 0xA, 0, 0, 0, 0, 6, 0x20, 0x4B])
    nib = body[13:-4]
    csum = sum(nib) & 0xFFFF
    assert body[-4:] == bytes([(csum >> 12) & 15, (csum >> 8) & 15, (csum >> 4) & 15, csum & 15])


@pytest.mark.parametrize("model,letter", [("Mini", "F"), ("12", "J"), ("12+", "K"),
                                          ("JR+", "L"), ("Pro+", "H")])
def test_model_letters(model, letter):
    assert codec.LETTER_FOR_MODEL[model] == letter
    assert codec.decode(codec.encode(bytes(128), 5, 1, letter)).model == model


def test_malformed_inputs_raise():
    good = codec.encode(bytes(256), 6, 1, "K")
    for bad in (b"", good[:-1], b"\xf0\x00\x00\x7c\x00\x01" + good[6:], good[:10] + b"\xf7"):
        with pytest.raises(codec.FirmwareFormatError):
            codec.decode(bad)
    with pytest.raises(codec.FirmwareFormatError):
        codec.encode(bytes(100), 6, 1, "K")              # not a multiple of 128
    with pytest.raises(codec.FirmwareFormatError):
        codec.encode(bytes(128), 6, 1, "Z")              # unknown model letter


def test_decode_cli_writes_memory_image(tmp_path, capsys):
    mem = bytes(range(128)) * 3
    src, out = tmp_path / "LF+12+_FIRM.syx", tmp_path / "out.bin"
    src.write_bytes(codec.encode(mem, 6, 32, "K"))
    assert cli_main(["--image", str(src), "--decode", str(out)]) == 0
    assert out.read_bytes() == mem and "checksum OK" in capsys.readouterr().out
    src.write_bytes(b"not firmware")
    assert cli_main(["--image", str(src), "--decode", str(out)]) == 2


# ---- real archive (skips in public checkouts) ----

def _all_real_images():
    found = [pathlib.Path(p).read_bytes() for p in glob.glob(str(FW / "**" / "*.syx"), recursive=True)]
    for z in glob.glob(str(FW / "**" / "*.zip"), recursive=True):
        try:
            with zipfile.ZipFile(z) as zf:
                found += [zf.read(n) for n in zf.namelist() if n.lower().endswith(".syx")]
        except zipfile.BadZipFile:
            pass
    return found


@requires_archive
def test_every_real_image_roundtrips_byte_exact():
    imgs = _all_real_images()
    assert len(imgs) >= 100
    for raw in imgs:
        img = codec.decode(raw)
        assert img.checksum_ok and img.length_ok and img.model, img.version
        assert codec.reencode(img) == raw


@requires_archive
def test_v632_12plus_decodes_to_pic18_code_with_lcd_text():
    img = codec.decode((V632 / "LF+12+_FIRM.syx").read_bytes())
    assert (img.version, img.model, len(img.memory)) == ("6.32", "12+", 128256)
    # PIC18 little-endian reset/interrupt vectors: three GOTOs (EFxx F0xx) at 0x0000/0x0008/0x0018
    for off in (0x00, 0x04, 0x08):
        assert img.memory[off + 1] == 0xEF and img.memory[off + 3] == 0xF0
    text = img.memory
    for needle in (b"Waiting", b"PRESET", b"Global", b"KEMPER", b"Liquid", b"FAMC"):
        assert needle in text, needle
    assert re.search(rb"Active Func Displays", text)
