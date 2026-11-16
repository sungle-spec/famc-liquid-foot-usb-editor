"""Read-only firmware inspection: what's *inside* a validated LF+ image, and the exact checks the
unit itself runs before it accepts one.

Everything here comes from disassembling the v6.32 application images with `pic18` (see
docs/FIRMWARE_NOTES.md, "Inside the image"). Nothing runs or modifies an image; it is only read.

How the unit takes a firmware update (the receiver routine, 0x409C in the 12+ image):

1. It shows "Firmware Waiting" and reads the sysex frame from either serial port.
2. It checks the frame as it arrives (ID byte, ``08 06``, header flag, block count) and
   **stores the image in external memory** — it does not touch its own program flash.
3. After the last byte it checks the ``F7``, the 16-bit checksum trailer and the model letter,
   then reads the stored copy back and compares a second checksum.
4. Only if every check passes does it write an "update pending" record to its EEPROM and jump to
   the boot loader (at 0x1F800, above the image and not part of any ``.syx``), which does the
   actual flashing.

Any failed check shows "Firmware Failed / Error N" for about four seconds and returns, with the
installed firmware untouched (the application has no code that writes program flash).
`DEVICE_ERRORS` maps N to its meaning, and `device_preflight()` runs the same checks on the host
so a bad image never leaves the computer.

Not known from the images (the boot loader is not in them): what the boot loader does if its copy
to flash is interrupted, and whether the power-on "wait for firmware" route still works when the
application itself is damaged — the button check we can see is in the application's start-up code.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import codec, pic18

# PIC18 hardware vectors, plus the application start the boot loader hands off to.
RESET_VECTOR, APP_ENTRY_VECTOR, HIGH_INT_VECTOR, LOW_INT_VECTOR = 0x00, 0x04, 0x08, 0x18
DEVICE_ID = 0x7C               # frame byte 3; the unit compares it with its own ID
RECEIVE_BYTE_TIMEOUT_MS = 96   # per-byte wait on the MIDI port before the unit gives up (approx.)

# "Firmware Failed / Error N" — N as the LCD shows it (3-digit decimal).
DEVICE_ERRORS: dict[int, str] = {
    1: "the header stopped arriving (timeout right after the frame started)",
    22: "wrong ID byte — the frame is not addressed to this unit (expects 7C)",
    23: "not a firmware frame (command byte is not 08)",
    24: "not a firmware frame (sub-command byte is not 06)",
    25: "header flag byte is not 0 or 1",
    26: f"block count is 0 or above {codec.DEVICE_MAX_BLOCKS}",
    27: "data stopped arriving mid-image (timeout)",
    28: "data stopped arriving mid-image (timeout)",
    29: "the checksum trailer stopped arriving (timeout)",
    30: "no F7 where the frame should end — length does not match the block count",
    31: "the received data sums to zero",
    32: "the checksum trailer is zero",
    33: "checksum mismatch — the image was corrupted in transit or on disk",
    34: "this image is for a different LF+ model",
    200: "the stored copy failed read-back verification",
}


def explain_device_error(code: int) -> str:
    """Plain-language meaning of the number after "Firmware Failed / Error" on the unit's LCD."""
    return DEVICE_ERRORS.get(code, "unknown error code (not one the v6.32 receiver produces)")


@dataclass
class Check:
    code: int             # the LCD error number the unit would show if this check failed
    name: str
    ok: bool | None       # True pass, False fail, None = only the unit can decide
    detail: str = ""

    @property
    def mark(self) -> str:
        return {True: "OK", False: "FAIL", None: "unit decides"}[self.ok]


@dataclass
class FirmwareInspection:
    version: str
    model: str | None
    model_letter: str
    blocks: int
    image_bytes: int
    checksum_ok: bool
    length_ok: bool
    reset_target: int | None = None    # Reset GOTO: the boot loader, above the image
    app_entry: int | None = None       # GOTO at 0x0004: where the boot loader starts the app
    isr_target: int | None = None      # GOTO at 0x0008: the (high-priority) interrupt handler
    low_vector: str = ""               # instruction at 0x0018 (low-priority interrupt vector)
    code_bytes: int = 0
    code_fraction: float = 0.0
    functions: int = 0
    decode_failures: int = 0
    writes_program_flash: bool = False  # any TBLWT in reachable code
    strings: list[tuple[int, str]] = field(default_factory=list)   # (addr, text)
    notable: list[tuple[int, str]] = field(default_factory=list)

    @property
    def bootloader_above_image(self) -> bool:
        """Reset jumps above the image → the boot loader is not in the .syx, so no firmware file
        can replace it."""
        return self.reset_target is not None and self.reset_target >= self.image_bytes

    @property
    def vectors_ok(self) -> bool:
        """The layout every FAMC image has: reset → boot loader above the image; application
        entry and interrupt handler inside it."""
        inside = lambda a: a is not None and 0 < a < self.image_bytes   # noqa: E731
        return self.bootloader_above_image and inside(self.app_entry) and inside(self.isr_target)


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

    insp.reset_target = goto_target(RESET_VECTOR)
    insp.app_entry = goto_target(APP_ENTRY_VECTOR)
    insp.isr_target = goto_target(HIGH_INT_VECTOR)
    low = pic18.decode(mem, LOW_INT_VECTOR)
    insp.low_vector = low.text if low else ""

    cm = pic18.trace(mem, [RESET_VECTOR, APP_ENTRY_VECTOR, HIGH_INT_VECTOR, LOW_INT_VECTOR])
    insp.code_bytes = cm.code_bytes()
    insp.code_fraction = (insp.code_bytes / len(mem)) if mem else 0.0
    insp.functions = len(cm.functions)
    insp.decode_failures = len(cm.bad)
    insp.writes_program_flash = any(i.mnemonic.startswith("TBLWT") for i in cm.insns.values())

    insp.strings = list(_ascii_strings(mem))
    seen = set()
    for addr, s in insp.strings:
        if any(h in s.lower() for h in _NOTABLE_HINTS) and s not in seen:
            seen.add(s)
            insp.notable.append((addr, s))
    return insp


def device_preflight(data: bytes, selected_model: str | None = None) -> list[Check]:
    """The unit's own acceptance checks, in the order its receiver makes them, run on the host.
    `code` is the LCD error number the unit would show for that check."""
    try:
        img = codec.decode(data)
    except codec.FirmwareFormatError as exc:
        # Nothing downstream is meaningful if it isn't even a firmware frame.
        return [Check(23, "well-formed firmware frame", False, str(exc))]

    hdr = data[len(codec.FRAME_PREFIX):len(codec.FRAME_PREFIX) + codec.HEADER_LEN]
    checks = [
        Check(22, f"ID byte is {DEVICE_ID:02X}", data[3] == DEVICE_ID,
              "the unit compares this with its own ID"),
        Check(23, "command byte is 08 (firmware)", data[4] == 0x08),
        Check(24, "sub-command byte is 06", data[5] == 0x06),
        Check(25, "header flag byte is 0 or 1", hdr[1] <= 1, f"is {hdr[1]}"),
        Check(26, f"block count is 1..{codec.DEVICE_MAX_BLOCKS} (v6.32 receiver)", img.blocks_ok,
              f"{img.blocks} blocks = {img.blocks * codec.BLOCK_BYTES:,} bytes"),
        Check(30, "frame ends with F7 exactly where the block count says", img.length_ok,
              f"{len(img.memory):,} image bytes in the file"),
        Check(31, "data checksum is not zero", img.computed_checksum != 0),
        Check(32, "checksum trailer is not zero", img.trailer != 0),
        Check(33, "checksum trailer matches the data", img.checksum_ok,
              f"file says {img.trailer:#06x}, data sums to {img.computed_checksum:#06x}"),
    ]
    if selected_model is not None:
        ok = img.model == selected_model
        checks.append(Check(34, f"image is for the LF+ {selected_model}", ok,
                            f"header letter {img.model_letter!r} = {img.model or 'unknown model'}"))
    else:
        checks.append(Check(34, "image is for the connected unit's model",
                            None if img.model else False,
                            f"header letter {img.model_letter!r} = {img.model or 'unknown model'}; "
                            "choose your model to check this here"))
    checks.append(Check(200, "stored copy reads back intact", None,
                        "the unit re-reads what it stored before handing over to the boot loader"))
    return checks


def describe_inspection(insp: FirmwareInspection, max_strings: int = 12) -> str:
    lines = [
        f"firmware : v{insp.version} for LF+ {insp.model or '?'} (model letter {insp.model_letter!r})",
        f"image    : {insp.image_bytes:,} bytes, {insp.blocks} x {codec.BLOCK_BYTES}-byte blocks",
        f"integrity: checksum {'OK' if insp.checksum_ok else 'MISMATCH'}, "
        f"length {'OK' if insp.length_ok else 'MISMATCH'}",
    ]
    if insp.reset_target is not None:
        where = ("above the image: the boot loader is not in this file, so no firmware file can "
                 "replace it" if insp.bootloader_above_image else
                 "INSIDE the image — not the layout of any FAMC release")
        lines.append(f"reset    : GOTO {insp.reset_target:#07x} ({where})")
    if insp.app_entry is not None:
        lines.append(f"app start: GOTO {insp.app_entry:#07x} (vector at 0x0004)")
    if insp.isr_target is not None:
        lines.append(f"interrupt: GOTO {insp.isr_target:#07x} (vector at 0x0008); "
                     f"low-priority vector at 0x0018: {insp.low_vector or '?'}")
    lines.append(f"vectors  : {'standard FAMC layout' if insp.vectors_ok else 'NOT the standard layout'}")
    lines.append(f"code     : {insp.code_bytes:,} bytes ({insp.code_fraction * 100:.0f}% of image) "
                 f"in ~{insp.functions} functions; {insp.decode_failures} decode failures")
    lines.append("flash    : " + ("this code CAN write program flash (contains table writes)"
                                  if insp.writes_program_flash else
                                  "this code never writes program flash itself (no table writes); "
                                  "flashing is done by the boot loader"))
    lines.append(f"strings  : {len(insp.strings)} printable runs (the unit's LCD text table)")
    for addr, s in insp.notable[:max_strings]:
        lines.append(f"  {addr:#07x}  {s}")
    return "\n".join(lines)


def describe_preflight(checks: list[Check]) -> str:
    lines = ["checks the unit makes before it accepts an image "
             "(number = its \"Firmware Failed / Error N\"):"]
    for c in checks:
        lines.append(f"  [{c.mark:>12}]  error {c.code:>3}  {c.name}"
                     + (f"  — {c.detail}" if c.detail else ""))
    failed = [c for c in checks if c.ok is False]
    lines.append("=> every check this computer can make passes" if not failed
                 else f"=> {len(failed)} FAILED — the unit would refuse this image")
    return "\n".join(lines)


def describe_device_errors() -> str:
    lines = ["\"Firmware Failed / Error N\" on the unit's display means:"]
    lines += [f"  {code:>3}  {text}" for code, text in DEVICE_ERRORS.items()]
    lines.append("Each of these is raised before the boot loader is involved, so the firmware "
                 "already installed on the unit is unchanged.")
    return "\n".join(lines)
