"""Read-only firmware inspection: what's *inside* a validated LF+ image, and the exact checks the
device itself runs before it commits a flash.

This is the analysis from docs/FIRMWARE_NOTES.md ("Inside the image") made into a tool: it decodes
the image (codec), traces its PIC18 code from the reset/interrupt vectors (pic18), and reports the
entry vectors, the code/data split, the recovered function count and the on-device LCD string
table. Nothing here runs or modifies the image; it only reads it.

It also exposes `device_preflight()`: the firmware's receiver validates a distinct set of fields
and refuses a bad or wrong-model image (error codes recovered from the receiver at 0x409C — see
DEVICE_CHECKS). The loader runs the same checks on the host so a bad image is rejected *before* any
flash write begins, and shows the user that our gate mirrors the unit's own.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import codec, pic18

# Standard PIC18 entry points: reset + high/low interrupt vectors are GOTOs at these byte addresses.
ENTRY_VECTORS = (0x00, 0x04, 0x08)
_EXTRA_ENTRY = (0x18,)   # the small reset-stub BRA landing the trace also needs as a seed

# The receiver (0x409C) validates these fields in order; each failure shows on the LCD and returns
# a distinct code. We mirror the host-checkable ones in device_preflight(). Model/identity checks
# (0x16/0x22) compare against the *connected unit's* identity, which only the device knows — the
# host can confirm the image is internally consistent and matches the user-selected model.
DEVICE_CHECKS = (
    (0x17, "command byte 0x08 (firmware-upload)"),
    (0x18, "sub-command byte 0x06"),
    (0x19, "header marker 0x01"),
    (0x1A, "block count within the device maximum"),
    (0x1E, "frame terminator 0xF7"),
    (0x1F, "payload checksum (high)"),
    (0x20, "payload checksum (mid)"),
    (0x21, "payload checksum (low)"),
    (0x16, "firmware version/model matches the connected unit"),
    (0x22, "model letter matches the connected unit"),
    (0xC8, "re-read-from-flash checksum verification"),
)


@dataclass
class Check:
    code: int             # the device's own error code for this field
    name: str
    ok: bool | None       # True pass, False fail, None = only the device can confirm (needs the unit)
    detail: str = ""

    @property
    def mark(self) -> str:
        return {True: "OK", False: "FAIL", None: "device-only"}[self.ok]


@dataclass
class FirmwareInspection:
    version: str
    model: str | None
    model_letter: str
    blocks: int
    image_bytes: int
    checksum_ok: bool
    length_ok: bool
    reset_target: int | None = None       # where Reset GOTOs (the boot-loader region, above image)
    hi_int_target: int | None = None
    lo_int_target: int | None = None
    code_bytes: int = 0
    code_fraction: float = 0.0
    functions: int = 0
    decode_failures: int = 0
    strings: list[tuple[int, str]] = field(default_factory=list)   # (addr, text)
    notable: list[tuple[int, str]] = field(default_factory=list)

    @property
    def bootloader_above_image(self) -> bool:
        """Reset vector jumps above the image → the boot loader is not in the .syx and a failed
        application flash can't overwrite it (the hold-button rescue always survives)."""
        return self.reset_target is not None and self.reset_target >= self.image_bytes


def _ascii_strings(mem: bytes, min_len: int = 5):
    run = bytearray()
    start = 0
    for i, b in enumerate(mem):
        if 0x20 <= b < 0x7F:
            if not run:
                start = i
            run.append(b)
        else:
            if len(run) >= min_len:
                yield start, run.decode("ascii")
            run = bytearray()
    if len(run) >= min_len:
        yield start, run.decode("ascii")


_NOTABLE_HINTS = ("firmware", "kemper", "axe-fx", "axe fx", "waiting", "please wait", "error",
                  "failed", "tuner", "scene", "reset", "factory", "liquid")


def inspect_firmware(data: bytes) -> FirmwareInspection:
    """Decode and statically analyse one firmware .syx frame. Raises codec.FirmwareFormatError if
    the bytes are not a well-formed LF+ firmware frame."""
    img = codec.decode(data)
    mem = img.memory
    insp = FirmwareInspection(
        version=img.version, model=img.model, model_letter=img.model_letter,
        blocks=img.blocks, image_bytes=len(mem),
        checksum_ok=img.checksum_ok, length_ok=img.length_ok,
    )

    def goto_target(addr: int) -> int | None:
        ins = pic18.decode(mem, addr)
        return ins.target if ins and ins.mnemonic == "GOTO" else None

    insp.reset_target = goto_target(0x00)
    insp.hi_int_target = goto_target(0x04)
    insp.lo_int_target = goto_target(0x08)

    cm = pic18.trace(mem, list(ENTRY_VECTORS) + list(_EXTRA_ENTRY))
    insp.code_bytes = cm.code_bytes()
    insp.code_fraction = (insp.code_bytes / len(mem)) if mem else 0.0
    insp.functions = len(cm.functions)
    insp.decode_failures = len(cm.bad)

    strings = list(_ascii_strings(mem))
    insp.strings = strings
    seen = set()
    for addr, s in strings:
        low = s.lower()
        if any(h in low for h in _NOTABLE_HINTS) and s not in seen:
            seen.add(s)
            insp.notable.append((addr, s))
    return insp


def device_preflight(data: bytes, selected_model: str | None = None) -> list[Check]:
    """The device's own acceptance checks, run on the host. Order and codes mirror the receiver at
    0x409C. Checks the host cannot make without the connected unit are returned as ok=None."""
    checks: list[Check] = []
    try:
        img = codec.decode(data)
    except codec.FirmwareFormatError as exc:
        # Nothing downstream is meaningful if it isn't even a firmware frame.
        return [Check(0x17, "well-formed firmware frame", False, str(exc))]

    frame_ok = data.startswith(codec.FRAME_PREFIX)
    checks.append(Check(0x17, "command byte 0x08 (firmware-upload)",
                        frame_ok and data[4] == 0x08))
    checks.append(Check(0x18, "sub-command byte 0x06", frame_ok and data[5] == 0x06))
    checks.append(Check(0x19, "header marker 0x01", data[6:9] == b"\x01\x00\x00"
                        if len(data) > 9 else False))
    checks.append(Check(0x1A, "block count within range",
                        0 < img.blocks <= 0xFFF, f"{img.blocks} blocks"))
    checks.append(Check(0x1E, "frame terminator 0xF7", data[-1:] == b"\xf7"))
    checks.append(Check(0x1F, "payload checksum", img.checksum_ok,
                        f"file {img.trailer:#06x} vs computed {img.computed_checksum:#06x}"))
    checks.append(Check(0x1A, "image length matches block count", img.length_ok,
                        f"{len(img.memory):,} bytes"))

    if selected_model is not None:
        matches = img.model == selected_model
        checks.append(Check(0x22, f"model letter is {img.model or '?'} (you chose {selected_model})",
                            matches, "" if matches else "wrong-model firmware is refused by the unit"))
    else:
        checks.append(Check(0x22, f"model letter {img.model_letter!r} -> {img.model or 'unknown'}",
                            img.model is not None))
    # These the unit checks against its own identity; the host can't see the connected device here.
    checks.append(Check(0x16, "version/model matches the connected unit", None,
                        "confirmed by the device as it receives"))
    checks.append(Check(0xC8, "re-read-from-flash checksum verification", None,
                        "the unit re-reads flash and re-verifies after writing"))
    return checks


def describe_inspection(insp: FirmwareInspection, max_strings: int = 12) -> str:
    lines = [
        f"firmware : v{insp.version} for LF+ {insp.model or '?'} (model letter {insp.model_letter!r})",
        f"image    : {insp.image_bytes:,} bytes, {insp.blocks} x {codec.BLOCK_BYTES}-byte blocks",
        f"integrity: checksum {'OK' if insp.checksum_ok else 'MISMATCH'}, "
        f"length {'OK' if insp.length_ok else 'MISMATCH'}",
    ]
    if insp.reset_target is not None:
        boot = ("above the image — boot loader is NOT in this file, so a failed flash keeps the "
                "hold-button rescue" if insp.bootloader_above_image else "inside the image")
        lines.append(f"reset    : GOTO {insp.reset_target:#07x} ({boot})")
    if insp.hi_int_target is not None:
        lines.append(f"interrupts: high GOTO {insp.hi_int_target:#07x}, low GOTO "
                     f"{insp.lo_int_target:#07x}")
    lines.append(f"code     : {insp.code_bytes:,} bytes ({insp.code_fraction * 100:.0f}% of image) "
                 f"in ~{insp.functions} functions; {insp.decode_failures} decode failures")
    lines.append(f"strings  : {len(insp.strings)} printable runs (the unit's LCD text table)")
    for addr, s in insp.notable[:max_strings]:
        lines.append(f"  {addr:#07x}  {s}")
    return "\n".join(lines)


def describe_preflight(checks: list[Check]) -> str:
    lines = ["device acceptance checks (the unit runs these before it commits a flash):"]
    for c in checks:
        lines.append(f"  [{c.mark:>11}]  err {c.code:#04x}  {c.name}"
                     + (f"  — {c.detail}" if c.detail else ""))
    failed = [c for c in checks if c.ok is False]
    lines.append(f"=> {'ALL HOST-CHECKABLE FIELDS PASS' if not failed else str(len(failed)) + ' FAILED'}")
    return "\n".join(lines)
