"""CLI: python -m lffirmware --image <file> --model <model> --port <midi-out> [--dry-run]."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .images import MODELS, describe, validate_image
from .send import SessionLog, estimate_seconds, list_ports, send_firmware

CHECKLIST = """Before sending, confirm ALL of these:
  * The device is connected to this computer's MIDI OUT -> device MIDI IN (5-pin DIN via a
    USB-MIDI interface). The LF+ USB (serial) port is NOT the firmware path.
  * The device shows "Waiting For Firmware" (bricked route: hold the power-up button for
    firmware-wait; working route: menu -> Utilities -> FIRMWARE LOADING -> SELECT).
  * No other MIDI software is running (DAWs, editors, MIDI monitors).
  * Laptop on AC power. Do not touch the device, cables, or this computer until it restarts.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="lffirmware",
        description=f"LF+ Firmware Loader {__version__} (beta) — flashes FAMC Liquid Foot+ "
                    "firmware over MIDI. THIS CAN PERMANENTLY DAMAGE YOUR DEVICE; read "
                    "docs/FIRMWARE_LOADER.md first and always have a backup.")
    ap.add_argument("--image", help="firmware .syx file (from your original editor install)")
    ap.add_argument("--model", choices=MODELS, help="your hardware model (YOU must know this)")
    ap.add_argument("--port", help="MIDI output port name (see --list-ports)")
    ap.add_argument("--list-ports", action="store_true", help="list MIDI output ports and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate everything and show what would be sent; no MIDI I/O")
    ap.add_argument("--yes", action="store_true", help="skip interactive confirmations (testers)")
    ap.add_argument("--allow-unverified", action="store_true",
                    help="allow an image that is not in the known-good hash list")
    ap.add_argument("--log-dir", help="where to write the session log")
    ap.add_argument("--decode", metavar="OUT.bin",
                    help="read-only: decode --image to a raw PIC18 program-memory image (little-"
                         "endian, for a disassembler such as Ghidra's PIC-18 module) and exit")
    ap.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.list_ports:
        ports = list_ports()
        print("\n".join(ports) if ports else "no MIDI output ports found")
        return 0

    if args.decode:
        if not args.image:
            ap.error("--decode needs --image")
        return _decode(args.image, args.decode)

    if not args.image or not args.model:
        ap.error("--image and --model are required (or use --list-ports)")

    rep = validate_image(args.image)
    print(describe(rep))
    print()

    if not (rep.is_known_good or rep.is_plausible):
        print("REFUSING: this file is not an LF+ firmware image.")
        return 2
    if not rep.is_known_good and not args.allow_unverified:
        print("REFUSING: unknown image hash. If you are certain this is genuine FAMC firmware,")
        print("re-run with --allow-unverified.")
        return 2
    if not rep.model_for(args.model):
        got = rep.known_model or rep.filename_model or "unknown"
        print(f"REFUSING: you selected model {args.model} but this image is for {got}.")
        print("Flashing wrong-model firmware can permanently damage the unit.")
        return 2

    est = estimate_seconds(rep.size)
    print(f"Ready: {args.model} firmware"
          + (f" v{rep.known_version}" if rep.known_version else " (unverified)")
          + f", {rep.size:,} bytes, ~{est:.0f}s over DIN MIDI.")

    if args.dry_run:
        print("\n--dry-run: nothing sent. The above is exactly what a real run would flash.")
        return 0

    if not args.port:
        ap.error("--port is required to send (see --list-ports)")

    print()
    print(CHECKLIST)
    if not args.yes:
        answer = input(f'Type the model name ("{args.model}") to confirm the flash: ').strip()
        if answer != args.model:
            print("Confirmation did not match — aborted, nothing sent.")
            return 1

    log = SessionLog(args.log_dir)
    print(f"Session log: {log.path}")

    def progress(elapsed: float, estimated: float) -> None:
        pct = min(99, int(elapsed / max(estimated, 1) * 100))
        print(f"\r  sending… {elapsed:5.0f}s (~{pct}%)", end="", flush=True)

    try:
        result = send_firmware(args.port, open(args.image, "rb").read(), rep, log,
                               on_progress=progress)
    finally:
        log.close()
    print(f"\nDone in {result['seconds']:.0f}s. Device replies: {len(result['replies'])}.")
    print("Watch the device LCD — it should program itself and restart. Do not power off")
    print("until it has. Send the log file above with your tester report.")
    return 0


def _decode(image: str, out: str) -> int:
    from . import codec
    try:
        with open(image, "rb") as fh:
            img = codec.decode(fh.read())
    except (OSError, codec.FirmwareFormatError) as exc:
        print(f"cannot decode: {exc}")
        return 2
    with open(out, "wb") as fh:
        fh.write(img.memory)
    print(f"v{img.version} for LF+ {img.model or '?'}: {len(img.memory):,} bytes "
          f"({img.blocks} x {codec.BLOCK_BYTES}) -> {out}; checksum "
          f"{'OK' if img.checksum_ok else 'MISMATCH'}, length {'OK' if img.length_ok else 'MISMATCH'}")
    return 0 if img.checksum_ok and img.length_ok else 2


def _selftest() -> int:
    """Frozen-bundle gate for CI: exercise validation + the refusal logic, no MIDI I/O."""
    import tempfile

    from . import codec
    from .known_images import KNOWN_IMAGES

    assert len(KNOWN_IMAGES) >= 200, "known-images table missing from bundle"
    with tempfile.TemporaryDirectory() as d:
        fake = f"{d}/LF+12+_FIRM.syx"
        with open(fake, "wb") as f:
            f.write(codec.encode(bytes(range(256)) * 16, 6, 99, "K"))
        rep = validate_image(fake)
        assert rep.is_plausible and not rep.is_known_good and rep.filename_model == "12+"
        assert main(["--image", fake, "--model", "12+", "--dry-run"]) == 2          # no override
        assert main(["--image", fake, "--model", "12+", "--dry-run",
                     "--allow-unverified"]) == 0
        assert main(["--image", fake, "--model", "Pro+", "--dry-run",
                     "--allow-unverified"]) == 2                                     # wrong model
    print(f"selftest OK — LF+ Firmware Loader {__version__}, "
          f"{len(KNOWN_IMAGES)} known images")
    return 0


if __name__ == "__main__":
    sys.exit(main())
