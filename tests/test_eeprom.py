"""Tests for the FTDI EEPROM driver-setup module + wizard (no hardware required)."""
import os
import platform
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

from lfeditor.comms import eeprom as ee


def test_detect_state_returns_known_state():
    st = ee.detect_state()
    assert st.state in (ee.READY, ee.ENABLED_NO_PORT, ee.NEEDS_ENABLE,
                        ee.OTHER_FTDI, ee.NO_DEVICE, ee.NO_BACKEND)
    assert isinstance(st.message, str) and st.message


def test_constants():
    assert ee.FAMC_CUSTOM_PID == 0x87C0
    assert ee.SERIAL_PID == 0x6015
    assert ee.PID_OFFSET == 0x04


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only revert guard")
def test_revert_blocked_on_macos():
    assert ee.revert_blocked_reason() is not None
    # revert write must refuse early (before any hardware access) on macOS
    res = ee.set_product_id(ee.SERIAL_PID, ee.FAMC_CUSTOM_PID, "/tmp/lf_eeprom_test",
                            allow_write=True)
    assert res.ok is False and "macOS" in res.message


def test_write_refused_without_allow_write_or_device():
    # No device connected → can't even back up → returns ok=False (never writes).
    res = ee.set_product_id(ee.FAMC_CUSTOM_PID, ee.SERIAL_PID, "/tmp/lf_eeprom_test",
                            allow_write=False)
    assert res.ok is False


def test_wizard_builds():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from lfeditor.ui.eeprom_wizard import EepromWizard
    w = EepromWizard()
    assert w.status.text()
    # enable only offered when a 0x87C0 device is present
    assert w.btn_enable.isEnabled() == (w._state.state == ee.NEEDS_ENABLE)


def test_wizard_shows_revert_block_reason_inline(monkeypatch):
    # A disabled button with only a tooltip reads as broken, not intentional — the reason
    # must also be visible in the body text without hovering.
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from lfeditor.ui import eeprom_wizard as wizard_module

    monkeypatch.setattr(wizard_module.ee, "revert_blocked_reason", lambda: "blocked for testing")
    w = wizard_module.EepromWizard()
    assert "Revert: blocked for testing" in w.detail.text()
    assert not w.btn_revert.isEnabled()

    monkeypatch.setattr(wizard_module.ee, "revert_blocked_reason", lambda: None)
    w2 = wizard_module.EepromWizard()
    assert "Revert:" not in w2.detail.text()
