"""Tests for the FTDI EEPROM driver-setup module + wizard (no hardware required)."""
import os
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


def test_no_platform_gate_on_revert():
    # Enable and Revert must go through the identical write path on every OS - there is no
    # platform-specific pre-check left in set_product_id() (the old macOS block was an
    # untested assumption; real hardware testing during the original protocol-cracking work
    # showed Revert works fine on macOS, so both directions now behave the same everywhere).
    assert not hasattr(ee, "revert_blocked_reason")
    import inspect
    src = inspect.getsource(ee.set_product_id)
    assert "platform" not in src


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


def test_wizard_revert_enabled_purely_by_device_state(monkeypatch):
    # Revert availability now depends only on whether the device is in a revertible state
    # (READY / ENABLED_NO_PORT) — no platform special-casing, on macOS or anywhere else.
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from lfeditor.ui import eeprom_wizard as wizard_module

    ready_state = wizard_module.ee.DeviceState(
        wizard_module.ee.READY, "Ready", pid=wizard_module.ee.SERIAL_PID,
        serial_ports=["/dev/cu.usbserial-TEST"],
    )
    monkeypatch.setattr(wizard_module.ee, "detect_state", lambda: ready_state)
    w = wizard_module.EepromWizard()
    assert w.btn_revert.isEnabled()

    needs_enable_state = wizard_module.ee.DeviceState(
        wizard_module.ee.NEEDS_ENABLE, "Needs enable", pid=wizard_module.ee.FAMC_CUSTOM_PID,
    )
    monkeypatch.setattr(wizard_module.ee, "detect_state", lambda: needs_enable_state)
    w2 = wizard_module.EepromWizard()
    assert not w2.btn_revert.isEnabled()
