"""PIC18 disassembler (lffirmware/pic18.py) — decode correctness + a trace over a real image.

The real-image checks run only when the decoded firmware .bin is available locally (reference/ is
gitignored), so CI without it still exercises the instruction decoder on hand-built word sequences.
"""
import pathlib

import pytest

from lffirmware import codec, pic18

FW_DIR = pathlib.Path(__file__).resolve().parent.parent / "reference" / "Liquid Foot" / "Firmware"


def _le(*words: int) -> bytes:
    out = bytearray()
    for w in words:
        out += bytes([w & 0xFF, (w >> 8) & 0xFF])
    return bytes(out)


def test_goto_is_two_words_and_targets_byte_address():
    # GOTO 0x1F800: PIC GOTO stores a word address (0xFC00); byte target = 0x1F800.
    ins = pic18.decode(_le(0xEF00, 0xF0FC), 0)
    assert ins.mnemonic == "GOTO" and ins.size == 4 and ins.target == 0x1F800
    assert ins.flow == pic18.JUMP


def test_call_and_return_flow():
    call = pic18.decode(_le(0xEC22, 0xF001), 0)   # CALL 0x02444
    assert call.mnemonic == "CALL" and call.size == 4 and call.flow == pic18.CALL
    assert call.target == ((0x0122 | (0x001 << 8)) << 1)
    assert pic18.decode(_le(0x0012), 0).mnemonic == "RETURN"
    assert pic18.decode(_le(0x0012), 0).flow == pic18.RET


def test_relative_branches_are_signed():
    # BRA (0xD0xx) +3 words from pc+2; RCALL is 0xD8xx.
    bra = pic18.decode(_le(0xD003), 0)
    assert bra.mnemonic == "BRA" and bra.target == 0x08 and bra.flow == pic18.JUMP
    assert pic18.decode(_le(0xD800), 0).mnemonic == "RCALL"
    bz = pic18.decode(_le(0xE0FE), 0)             # BZ, negative displacement
    assert bz.mnemonic == "BZ" and bz.flow == pic18.CJUMP


def test_byte_bit_and_literal_ops_decode():
    assert pic18.decode(_le(0x0E55), 0).mnemonic == "MOVLW"      # MOVLW 0x55
    assert pic18.decode(_le(0x0E55), 0).k == 0x55
    assert pic18.decode(_le(0x6A80), 0).mnemonic == "CLRF"       # CLRF 0x80
    assert pic18.decode(_le(0x9C0A), 0).mnemonic == "BCF"        # BCF f,bit
    assert pic18.decode(_le(0x0003), 0).mnemonic == "SLEEP"
    movff = pic18.decode(_le(0xC123, 0xF456), 0)                 # MOVFF 0x123,0x456
    assert movff.mnemonic == "MOVFF" and movff.size == 4 and movff.f2 == 0x456


def test_skip_instruction_marks_skip_flow():
    assert pic18.decode(_le(0xA40A), 0).flow == pic18.SKIP       # BTFSC
    assert pic18.decode(_le(0x2E80), 0).mnemonic == "DECFSZ"
    assert pic18.decode(_le(0x2E80), 0).flow == pic18.SKIP


def test_decode_rejects_odd_and_out_of_range():
    assert pic18.decode(b"\x00\x00", 1) is None
    assert pic18.decode(b"\x00\x00", 10) is None


def _have_image() -> pathlib.Path | None:
    cand = FW_DIR / "LF_PLUS_firmware_v6_32" / "LF+12+_FIRM.syx"
    return cand if cand.exists() else None


@pytest.mark.skipif(_have_image() is None, reason="firmware image not present (reference/ is local)")
def test_trace_over_real_image_covers_most_of_it_without_decode_errors():
    img = codec.decode(_have_image().read_bytes())
    mem = img.memory
    # Standard PIC18 entry points: reset + the two interrupt vectors are GOTOs at 0/4/8.
    assert pic18.decode(mem, 0).mnemonic == "GOTO"
    cm = pic18.trace(mem, [0x0, 0x4, 0x8, 0x18])
    assert not cm.bad, f"decode failures at {sorted(hex(a) for a in cm.bad)}"
    assert cm.code_bytes() > len(mem) * 0.80      # most of the image is reachable code
    assert len(cm.functions) > 100                # many call targets found
    # The reset vector jumps to the boot-loader region above the image (not part of the .syx).
    assert 0x1F800 in cm.out_of_image
