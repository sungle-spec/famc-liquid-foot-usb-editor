"""lffirmware.inspect: read-only image inspection + the device's own acceptance checks.

Synthetic images (valid header/length/checksum) run everywhere; the real-image assertions skip
when the private firmware archive is absent, same pattern as the rest of the loader tests.
"""
import pathlib

import pytest

from lffirmware import codec, inspect

REPO = pathlib.Path(__file__).resolve().parent.parent
ARCHIVE = REPO / "reference" / "Liquid Foot" / "Firmware" / "LF_PLUS_firmware_v6_32"
requires_firmware_archive = pytest.mark.skipif(
    not ARCHIVE.exists(), reason="private FAMC firmware archive not present in this checkout")


def synth(letter: str = "K", size: int = 8192) -> bytes:
    # A small image whose reset vector GOTOs above its own length (like a real one).
    mem = bytearray(bytes(i % 251 for i in range(size)))
    # Reset vector: GOTO 0x1F800 (word 0xFC00) -> EF00 F0FC little-endian in the FIRST two words.
    mem[0:4] = bytes([0x00, 0xEF, 0xFC, 0xF0])
    return codec.encode(bytes(mem), 6, 50, letter)


def test_inspect_reports_version_model_and_entry_vector():
    insp = inspect.inspect_firmware(synth("K"))
    assert insp.version == "6.50" and insp.model == "12+" and insp.model_letter == "K"
    assert insp.reset_target == 0x1F800
    assert insp.bootloader_above_image is True        # above the image => rescue survives a bad flash
    # Synthetic payload is random bytes, so the trace from the vectors runs but need not fully decode;
    # the strict "0 decode failures" assertion is for real images (below).
    assert insp.code_bytes > 0 and insp.functions >= 1


def test_inspect_rejects_non_firmware():
    with pytest.raises(codec.FirmwareFormatError):
        inspect.inspect_firmware(b"\xf0\x00\x00\x7c\x00\x01not firmware\xf7")


def test_device_preflight_passes_for_matching_model():
    checks = inspect.device_preflight(synth("K"), "12+")
    assert all(c.ok is not False for c in checks)      # nothing fails
    codes = {c.code for c in checks}
    assert {0x17, 0x18, 0x19, 0x1A, 0x1E, 0x1F, 0x22, 0x16, 0xC8} <= codes
    model_check = next(c for c in checks if c.code == 0x22)
    assert model_check.ok is True


def test_device_preflight_flags_wrong_model():
    checks = inspect.device_preflight(synth("K"), "Pro+")
    model_check = next(c for c in checks if c.code == 0x22)
    assert model_check.ok is False
    assert any("refused by the unit" in c.detail for c in checks if c.ok is False)


def test_device_preflight_detects_bad_checksum():
    img = bytearray(synth("K"))
    img[-2] ^= 0x0F                                    # corrupt a trailer nibble
    checks = inspect.device_preflight(bytes(img), "12+")
    csum = next(c for c in checks if c.code == 0x1F)
    assert csum.ok is False


def test_device_preflight_on_garbage_returns_single_frame_failure():
    checks = inspect.device_preflight(b"not a frame at all")
    assert len(checks) == 1 and checks[0].ok is False


def test_describe_functions_are_plain_text():
    data = synth("K")
    txt = inspect.describe_inspection(inspect.inspect_firmware(data))
    assert "firmware" in txt and "reset" in txt
    pf = inspect.describe_preflight(inspect.device_preflight(data, "12+"))
    assert "device acceptance checks" in pf and "err 0x22" in pf


@requires_firmware_archive
def test_real_v632_image_full_inspection():
    data = (ARCHIVE / "LF+12+_FIRM.syx").read_bytes()
    insp = inspect.inspect_firmware(data)
    assert insp.version == "6.32" and insp.model == "12+"
    assert insp.reset_target == 0x1F800 and insp.bootloader_above_image
    assert insp.code_fraction > 0.80 and insp.decode_failures == 0
    assert insp.functions > 100
    # The LCD string table is recovered from the data region.
    joined = " ".join(s for _a, s in insp.notable)
    assert "Firmware Waiting" in joined
    checks = inspect.device_preflight(data, "12+")
    assert not [c for c in checks if c.ok is False]


@requires_firmware_archive
def test_every_real_model_decodes_without_failures():
    for name, model in [("LF+MINI_FIRM.syx", "Mini"), ("LF+12_FIRM.syx", "12"),
                        ("LF+JR+_FIRM.syx", "JR+"), ("LF+12+_FIRM.syx", "12+"),
                        ("LF+PRO+_FIRM.syx", "Pro+")]:
        insp = inspect.inspect_firmware((ARCHIVE / name).read_bytes())
        assert insp.model == model and insp.decode_failures == 0
        assert insp.bootloader_above_image


# ---- loader GUI (the Inspect button + the device-checks summary line) ----
@pytest.fixture(scope="session")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_gui_choose_file_enables_inspect_and_shows_device_checks(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from lffirmware.gui import LoaderWindow

    p = tmp_path / "LF+12+_FIRM.syx"
    p.write_bytes(synth("K"))
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(p), "")))
    w = LoaderWindow()
    assert not w.inspect_btn.isEnabled()
    w.choose_file()
    assert w.inspect_btn.isEnabled()
    assert "device checks:" in w.report.toPlainText()
    w.close()


def test_gui_inspect_dialog_body_is_built(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from lffirmware.gui import LoaderWindow

    p = tmp_path / "LF+PRO+_FIRM.syx"
    p.write_bytes(synth("H"))
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(p), "")))
    captured = {}
    monkeypatch.setattr(QMessageBox, "exec", lambda self: captured.setdefault("text", self.text()))
    w = LoaderWindow()
    w.choose_file()
    w.model.setCurrentText("Pro+")
    w.show_inspection()
    assert "firmware" in captured["text"] and "device acceptance checks" in captured["text"]
    w.close()
