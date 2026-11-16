"""lffirmware.inspect: read-only image inspection + the unit's own acceptance checks.

Synthetic images (valid header/length/checksum) run everywhere; the real-image assertions skip
when the private firmware archive is absent, same pattern as the rest of the loader tests.
"""
import pathlib

import pytest

from lffirmware import codec, images, inspect

REPO = pathlib.Path(__file__).resolve().parent.parent
ARCHIVE = REPO / "reference" / "Liquid Foot" / "Firmware" / "LF_PLUS_firmware_v6_32"
requires_firmware_archive = pytest.mark.skipif(
    not ARCHIVE.exists(), reason="private FAMC firmware archive not present in this checkout")
REAL = [("LF+MINI_FIRM.syx", "Mini"), ("LF+12_FIRM.syx", "12"), ("LF+JR+_FIRM.syx", "JR+"),
        ("LF+12+_FIRM.syx", "12+"), ("LF+PRO+_FIRM.syx", "Pro+")]


def _goto(addr: int) -> bytes:
    w = addr >> 1
    return bytes([w & 0xFF, 0xEF, (w >> 8) & 0xFF, 0xF0 | ((w >> 16) & 0x0F)])


def synth(letter: str = "K", size: int = 8192) -> bytes:
    """A small image with the FAMC vector layout: reset -> boot loader above the image, app entry
    and interrupt handler inside it. The rest is filler (RETURNs), not real firmware."""
    mem = bytearray(b"\x12\x00" * (size // 2))           # RETURN everywhere
    mem[0:4] = _goto(0x1F800)                            # reset -> boot loader
    mem[4:8] = _goto(0x0100)                             # application start
    mem[8:12] = _goto(0x0200)                            # interrupt handler
    mem[0x18:0x1A] = bytes([0xF3, 0xD7])                 # BRA 0x0000 (low-priority vector)
    return codec.encode(bytes(mem), 6, 50, letter)


# ---- inspection ----
def test_inspect_reports_version_model_and_vectors():
    insp = inspect.inspect_firmware(synth("K"))
    assert insp.version == "6.50" and insp.model == "12+" and insp.model_letter == "K"
    assert insp.reset_target == 0x1F800 and insp.bootloader_above_image
    assert insp.app_entry == 0x0100 and insp.isr_target == 0x0200
    assert insp.low_vector == "BRA 0x00000"
    assert insp.vectors_ok and insp.decode_failures == 0
    assert insp.writes_program_flash is False


def test_inspect_flags_a_reset_vector_inside_the_image():
    mem = bytearray(b"\x12\x00" * 4096)
    mem[0:4] = _goto(0x0100)                             # reset does NOT go to a boot loader
    insp = inspect.inspect_firmware(codec.encode(bytes(mem), 6, 50, "K"))
    assert not insp.bootloader_above_image and not insp.vectors_ok
    assert "NOT the standard layout" in inspect.describe_inspection(insp)


def test_inspect_detects_table_writes():
    mem = bytearray(b"\x12\x00" * 4096)
    mem[0:4] = _goto(0x1F800)
    mem[4:8] = _goto(0x0100)
    mem[8:12] = _goto(0x0200)
    mem[0x100:0x102] = bytes([0x0D, 0x00])               # TBLWT*+ at the app entry
    insp = inspect.inspect_firmware(codec.encode(bytes(mem), 6, 50, "K"))
    assert insp.writes_program_flash is True


def test_inspect_rejects_non_firmware():
    with pytest.raises(codec.FirmwareFormatError):
        inspect.inspect_firmware(b"\xf0\x00\x00\x7c\x00\x01not firmware\xf7")


# ---- the unit's acceptance checks ----
def _by_code(checks):
    return {c.code: c for c in checks}


def test_preflight_passes_for_matching_model_and_uses_the_units_error_numbers():
    checks = inspect.device_preflight(synth("K"), "12+")
    assert not [c for c in checks if c.ok is False]
    assert [c.code for c in checks] == [22, 23, 24, 25, 26, 30, 31, 32, 33, 34, 200]
    assert set(c.code for c in checks) <= set(inspect.DEVICE_ERRORS)
    assert _by_code(checks)[34].ok is True
    assert _by_code(checks)[200].ok is None              # only the unit can do the read-back


def test_preflight_flags_wrong_model_as_error_34():
    c = _by_code(inspect.device_preflight(synth("K"), "Pro+"))[34]
    assert c.ok is False and "12+" in c.detail


def test_preflight_without_a_selected_model_leaves_34_to_the_unit():
    assert _by_code(inspect.device_preflight(synth("K")))[34].ok is None


def test_preflight_detects_bad_checksum_as_error_33():
    img = bytearray(synth("K"))
    img[-2] ^= 0x0F                                      # corrupt a trailer nibble
    assert _by_code(inspect.device_preflight(bytes(img), "12+"))[33].ok is False


def test_preflight_on_garbage_returns_single_frame_failure():
    checks = inspect.device_preflight(b"not a frame at all")
    assert len(checks) == 1 and checks[0].ok is False


def test_block_count_limit_is_reported_not_enforced():
    """1007 is the v6.32 receiver's ceiling; one genuine old image (12+ v3.36) has 1008 blocks, so
    the host reports it (check 26) instead of refusing to parse or validate the file."""
    assert codec.DEVICE_MAX_BLOCKS == 0x3EF == 1007
    assert codec.DEVICE_MAX_BLOCKS * codec.BLOCK_BYTES == 0x1F780 < 0x1F800
    big = codec.encode(b"\x12\x00" * (1008 * 64), 6, 50, "K")
    assert not codec.decode(big).blocks_ok
    assert _by_code(inspect.device_preflight(big, "12+"))[26].ok is False
    assert codec.decode(codec.encode(b"\x12\x00" * (1007 * 64), 6, 50, "K")).blocks_ok


def test_error_table_and_explanations():
    assert "different LF+ model" in inspect.explain_device_error(34)
    assert "checksum mismatch" in inspect.explain_device_error(33)
    assert "unknown" in inspect.explain_device_error(99)
    txt = inspect.describe_device_errors()
    assert " 34 " in txt and "200" in txt and "unchanged" in txt


def test_describe_functions_are_plain_text():
    data = synth("K")
    txt = inspect.describe_inspection(inspect.inspect_firmware(data))
    assert "firmware" in txt and "reset" in txt and "app start" in txt
    pf = inspect.describe_preflight(inspect.device_preflight(data, "12+"))
    assert "error  34" in pf and "every check this computer can make passes" in pf


def test_cli_explain_error(capsys):
    from lffirmware.cli import main
    assert main(["--explain-error", "33"]) == 0
    assert "checksum mismatch" in capsys.readouterr().out
    assert main(["--explain-error"]) == 0
    assert "Firmware Failed" in capsys.readouterr().out
    assert main(["--explain-error", "99"]) == 2


# ---- real FAMC images (private archive) ----
@requires_firmware_archive
@pytest.mark.parametrize("name,model", REAL)
def test_real_v632_images_have_the_standard_layout(name, model):
    data = (ARCHIVE / name).read_bytes()
    insp = inspect.inspect_firmware(data)
    assert insp.version == "6.32" and insp.model == model
    assert insp.reset_target == 0x1F800 and insp.vectors_ok
    assert insp.low_vector == "BRA 0x00000"
    assert insp.code_fraction > 0.80 and insp.decode_failures == 0 and insp.functions > 100
    assert insp.writes_program_flash is False            # flashing is the boot loader's job
    assert "Firmware Waiting" in " ".join(s for _a, s in insp.notable)
    assert not [c for c in inspect.device_preflight(data, model) if c.ok is False]


@requires_firmware_archive
@pytest.mark.parametrize("name,model", REAL)
def test_real_receiver_uses_exactly_the_documented_error_codes(name, model):
    """Find the routine that hands over to the boot loader and read the error numbers it raises;
    they must be exactly DEVICE_ERRORS, and its block-count limit must be DEVICE_MAX_BLOCKS."""
    import bisect
    from collections import Counter
    from lffirmware import pic18
    mem = codec.decode((ARCHIVE / name).read_bytes()).memory
    cm = pic18.trace(mem, [0, 4, 8, 0x18])
    (src,) = [s for ss in cm.out_of_image.values() for s in ss if s > 8]
    fs = sorted(cm.functions)
    start = fs[bisect.bisect_right(fs, src) - 1]
    ins = list(pic18.linear(mem, start, src + 4))
    raised = []
    for n, i in enumerate(ins):
        if i.mnemonic == "MOVLW":
            call = next((j for j in ins[n + 1:n + 4] if j.mnemonic == "CALL"), None)
            if call is not None:
                raised.append((i.k, call.target))
    err_fn = Counter(t for _k, t in raised).most_common(1)[0][0]
    assert sorted({k for k, t in raised if t == err_fn}) == sorted(inspect.DEVICE_ERRORS)
    sublw = [i.k for i in ins if i.mnemonic == "SUBLW"]
    assert 0x03 in sublw and 0xEF in sublw               # the 0x03EF block-count ceiling


# ---- loader GUI (the Inspect button + the unit-checks summary line) ----
@pytest.fixture(scope="session")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_gui_choose_file_enables_inspect_and_shows_unit_checks(qapp, tmp_path, monkeypatch):
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
    assert "unit checks: every check this computer can make passes" in w.report.toPlainText()
    w.close()


def test_gui_inspect_dialog_has_report_checks_and_error_table(qapp, tmp_path, monkeypatch):
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
    body = captured["text"]
    assert "app start" in body and "checks the unit makes" in body and "Firmware Failed" in body
    w.close()
