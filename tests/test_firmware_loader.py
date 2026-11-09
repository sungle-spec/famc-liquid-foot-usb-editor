"""lffirmware: image validation, safety gates, and the CLI's refusal paths.

Synthetic-image tests run everywhere; tests against the real FAMC firmware archive skip when
reference/ is absent (public checkouts), same pattern as the reference-rig skips.
"""
import pathlib

import pytest

from lffirmware import codec, images
from lffirmware.cli import main as cli_main
from lffirmware.known_images import KNOWN_IMAGES

REPO = pathlib.Path(__file__).resolve().parent.parent
ARCHIVE = REPO / "reference" / "Liquid Foot" / "Firmware" / "LF_PLUS_firmware_v6_32"
requires_firmware_archive = pytest.mark.skipif(
    not ARCHIVE.exists(), reason="private FAMC firmware archive not present in this checkout")


def synth_image(size: int = 4096, letter: str = "K") -> bytes:
    """A well-formed fake firmware frame (valid header, length field and checksum) — packaging only."""
    return codec.encode(bytes(i % 251 for i in range(size)), 6, 99, letter)


# ---- synthetic validation (runs everywhere) ----

def test_synthetic_image_is_plausible_but_not_known(tmp_path):
    p = tmp_path / "LF+12+_FIRM.syx"
    p.write_bytes(synth_image())
    rep = images.validate_image(p)
    assert rep.frame_ok and rep.data_bytes_ok and rep.nibble_fraction > 0.99
    assert rep.is_plausible and not rep.is_known_good
    assert rep.filename_model == "12+"
    assert rep.model_for("12+") and not rep.model_for("Pro+")
    assert rep.structure_ok and rep.version == "6.99" and rep.header_model == "12+"


def test_corrupt_or_truncated_images_are_never_plausible(tmp_path):
    good = synth_image()
    bad_sum = bytearray(good)
    bad_sum[-2] ^= 0x01                                  # flip a trailer nibble
    p = tmp_path / "LF+12+_FIRM.syx"
    p.write_bytes(bytes(bad_sum))
    rep = images.validate_image(p)
    assert not rep.structure_ok and not rep.is_plausible
    assert any("checksum" in e for e in rep.errors)
    cut = good[:-4 - 16] + good[-4:]                     # drop 16 payload nibbles, keep trailer
    p.write_bytes(cut)
    rep = images.validate_image(p)
    assert not rep.is_plausible and any("truncated" in e or "checksum" in e for e in rep.errors)


def test_header_model_beats_filename(tmp_path):
    p = tmp_path / "LF+MINI_FIRM.syx"                    # lying filename
    p.write_bytes(synth_image(letter="K"))               # header says 12+
    rep = images.validate_image(p)
    assert rep.header_model == "12+" and rep.filename_model == "Mini"
    assert rep.model_for("12+") and not rep.model_for("Mini")
    assert any("header says 12+" in e for e in rep.errors)


def test_backup_file_is_rejected(tmp_path):
    # A backup starts F0 00 00 7C ?? 01 — must never validate as firmware.
    p = tmp_path / "backup.syx"
    p.write_bytes(bytes([0xF0, 0x00, 0x00, 0x7C, 0x00, 0x01]) + bytes(64) + b"\xf7")
    rep = images.validate_image(p)
    assert not rep.frame_ok and not rep.is_plausible and not rep.is_known_good


def test_multi_frame_and_bad_payload_are_rejected(tmp_path):
    two = tmp_path / "two.syx"
    two.write_bytes(synth_image() + synth_image())
    assert not images.validate_image(two).is_plausible
    hot = tmp_path / "hot.syx"
    hot.write_bytes(images.HEADER + bytes([0x90] * 2048) + b"\xf7")  # >0x7F payload
    rep = images.validate_image(hot)
    assert not rep.data_bytes_ok and not rep.is_plausible


def test_filename_model_longest_prefix():
    assert images.model_from_filename("LF+12+_FIRM.syx") == "12+"
    assert images.model_from_filename("LF+12_FIRM.syx") == "12"
    assert images.model_from_filename("lf+pro+_firm.syx") == "Pro+"
    assert images.model_from_filename("whatever.syx") is None


def test_known_images_table_shape():
    assert len(KNOWN_IMAGES) >= 200
    models = {m for m, _v, _s in KNOWN_IMAGES.values()}
    assert models == set(images.MODELS)
    # sizes collide across models — the reason hash identity is mandatory
    sizes = {}
    collision = False
    for m, _v, s in KNOWN_IMAGES.values():
        if s in sizes and sizes[s] != m:
            collision = True
            break
        sizes.setdefault(s, m)
    assert collision, "expected cross-model size collisions (safety rationale)"


# ---- CLI refusal paths (no MIDI I/O anywhere) ----

def test_cli_dry_run_refuses_unknown_image_without_override(tmp_path, capsys):
    p = tmp_path / "LF+12+_FIRM.syx"
    p.write_bytes(synth_image())
    rc = cli_main(["--image", str(p), "--model", "12+", "--dry-run"])
    assert rc == 2
    assert "unknown image hash" in capsys.readouterr().out.lower()


def test_cli_dry_run_unknown_image_with_override(tmp_path, capsys):
    p = tmp_path / "LF+12+_FIRM.syx"
    p.write_bytes(synth_image())
    rc = cli_main(["--image", str(p), "--model", "12+", "--dry-run", "--allow-unverified"])
    assert rc == 0
    assert "nothing sent" in capsys.readouterr().out


def test_cli_refuses_model_mismatch(tmp_path, capsys):
    p = tmp_path / "LF+MINI_FIRM.syx"
    p.write_bytes(synth_image(letter="F"))               # a genuine Mini-format image
    rc = cli_main(["--image", str(p), "--model", "12+", "--dry-run", "--allow-unverified"])
    assert rc == 2
    assert "wrong-model" in capsys.readouterr().out.lower()


def test_cli_refuses_non_firmware(tmp_path, capsys):
    p = tmp_path / "backup.syx"
    p.write_bytes(bytes([0xF0, 0x00, 0x00, 0x7C, 0x00, 0x01]) + bytes(2048) + b"\xf7")
    rc = cli_main(["--image", str(p), "--model", "12+", "--dry-run"])
    assert rc == 2


# ---- against the real archive (private checkouts only) ----

@requires_firmware_archive
def test_v632_images_are_known_good_for_their_models():
    for name, model in [("LF+MINI_FIRM.syx", "Mini"), ("LF+12_FIRM.syx", "12"),
                        ("LF+12+_FIRM.syx", "12+"), ("LF+JR+_FIRM.syx", "JR+"),
                        ("LF+PRO+_FIRM.syx", "Pro+")]:
        rep = images.validate_image(ARCHIVE / name)
        assert rep.is_known_good, f"{name}: {rep.errors}"
        assert rep.known_model == model and rep.known_version == "6.32"
        assert rep.model_for(model)
        for other in images.MODELS:
            if other != model:
                assert not rep.model_for(other)


@requires_firmware_archive
def test_real_image_dry_run_cli_accepts():
    rc = cli_main(["--image", str(ARCHIVE / "LF+12+_FIRM.syx"), "--model", "12+", "--dry-run"])
    assert rc == 0


def test_factory_backups_never_validate_as_firmware():
    # factory files ship publicly, so this guard runs everywhere
    factory = REPO / "lfeditor" / "resources" / "factory"
    for p in sorted(factory.glob("*.syx")):
        rep = images.validate_image(p)
        assert not rep.is_plausible and not rep.is_known_good, p.name
