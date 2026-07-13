"""
Expression-pedal global settings — live in Config (type 4) **record #0**. There are 4 pedals.
Offsets pinned via diff_dumps.py against the live editor.

  value[5 + i]        = pedal i type      (0..3 pedals)
  value[9 + 2*i]      = pedal i CC number (changing the type resets this)

Other per-pedal fields (channel, sensitivity, min/max sweep, hi-res 2nd button) are
interleaved nearby and not yet individually pinned.
"""
from __future__ import annotations

NUM_PEDALS = 4
TYPE_OFF = 5        # pedal i type at value[5 + i]
CC_OFF = 9          # pedal i CC# at value[9 + 2*i]
CC_STRIDE = 2

# Per-pedal toggles packed as bitfields (one bit per pedal, bit i = pedal i+1).
# Pinned by diff-RE: pedal 1 = bit0, pedal 2 = bit1 (value[37] 0→2, value[69] 0→2).
AUTO_CALIBRATE_OFF = 37   # auto-calibrate bitfield
BLOCK_RESET_OFF = 69      # block-reset bitfield
FORCE_ZIPPER_OFF = 70     # force-zipper bitfield (live-diff 2026-06-16: pedal 1 -> bit0)

# Four field-major arrays of 4 pedals each (stride 1), pinned by a user-assisted single-variable
# diff on pedal 1 and corroborated by the baseline bytes ([57..60] = [1,0,0,0] = Max 126/127s):
MIN_SWEEP_OFF = 53    # CC-sweep min, value[53 + pedal], stored directly (0..127)
MAX_SWEEP_OFF = 57    # CC-sweep max, value[57 + pedal], stored INVERTED (byte = 127 - shown)
TOE_TRIG_OFF = 61     # toe trigger, value[61 + pedal] (0 = NONE)
HEEL_TRIG_OFF = 65    # heel trigger, value[65 + pedal] (0 = NONE)
MAX_SWEEP_INVERT = 127

# Per-pedal MIDI channel: low nibble of the cmd/chan byte that pairs with each CC byte
# (value[10 + 2*pedal]; high nibble = expression command). 0-based (0 → channel 1).
CHAN_OFF = 10         # chan byte = CHAN_OFF + CC_STRIDE * pedal
# Sensitivity level: field-major array, value[33 + pedal].
SENS_LEVEL_OFF = 33
SENS_LEVELS = {0: "Default", 1: "Ignore", 2: "High", 3: "Low"}

# Per-pedal FLAGS byte at value[71 + pedal] (pedal 1 = value[71]). Reverse-engineered by live
# hardware diff on a real LF+ 12+ (fw 6.32, 2026-06-16): this is a bitfield, NOT a 0-127 value.
#   bit 0x01 = "Blk Heel/Toe Sensitivity"
#   bit 0x10 = "Hi-Res Mode"  (also forces a pedal re-calibration on the device when applied)
PEDAL_FLAGS_OFF = 71
BLK_HEELTOE_SENS_BIT = 0x01
HIRES_MODE_BIT = 0x10
# Back-compat alias (was modelled as a value; now known to be the flags byte):
BLK_HEELTOE_SENS_OFF = PEDAL_FLAGS_OFF

# value[17:33] is the per-pedal **calibration / range block**, confirmed by live calibration
# (2026-06-16): two 2-byte little-endian arrays of 4 pedals each —
#   value[17 + 2*pedal] = calibrated MAX (toe) ADC reading   (pedal 1 swept 409 -> 1023)
#   value[25 + 2*pedal] = calibrated MIN (heel) ADC reading  (pedal 1 swept 10  -> 84)
# These are raw ADC values set by physically sweeping the pedal, not typeable fields; "Hi-Res
# Mode" resets them (forcing re-calibration). Round-trips losslessly; not surfaced as editable.
CALIBRATION_MAX_OFF = 17
CALIBRATION_MIN_OFF = 25
CALIBRATION_BLOCK = range(17, 33)


def chan_offset(pedal: int) -> int:
    return CHAN_OFF + CC_STRIDE * pedal

PEDAL_TYPES = {
    0: "Not Active", 1: "Continuous", 2: "Latch", 3: "Momentary",
    4: "1 — ignore", 5: "2 — ignore", 6: "Trigger IA", 7: "Toggle IA",
    8: "Page Button Press", 9: "2 Page Buttons",
}


def type_offset(pedal: int) -> int:
    return TYPE_OFF + pedal


def cc_offset(pedal: int) -> int:
    return CC_OFF + CC_STRIDE * pedal
