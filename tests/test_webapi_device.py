"""The webapi WebSerial bridge (Session.dev_*), which web/serial.js drives from the browser.

The browser does the async navigator.serial I/O; every *byte* of the protocol comes from these
helpers. These tests pin the bridge to comms/protocol.py (the hardware-confirmed source of truth)
and simulate the device's read stream the same way serial.js slices it, so the only thing left to
verify on real hardware is the transport itself.
"""
import pathlib

import pytest

from conftest import requires_rjm

from lfeditor.codec import Dump
from lfeditor.codec.frame import TYPE_NAMES
from lfeditor.comms.protocol import (
    DEFAULT_MODEL,
    FOOT_READ_CMDS,
    exit_frame,
    handshake_frame,
    read_command,
    session_frame,
)
from lfeditor.webapi import Session

ROOT = pathlib.Path(__file__).resolve().parent.parent
FACTORY = ROOT / "lfeditor" / "resources" / "factory" / "Factory_Defaults12.syx"
# The real-hardware reference dump (read-only): unlike the factory files it contains every
# record type the device's read commands expose, including the ext records.
RJM = ROOT / "reference" / "sysex_dumps" / "RJM.syx"


def _loaded_session() -> Session:
    s = Session()
    s.load(FACTORY.read_bytes())
    return s


# ---- control / request frames: byte-parity with comms.protocol ----

def test_control_frames_match_protocol():
    s = Session()
    assert bytes(s.dev_handshake()) == handshake_frame()
    assert bytes(s.dev_session()) == session_frame()
    assert bytes(s.dev_exit()) == exit_frame()
    for x in FOOT_READ_CMDS:
        assert bytes(s.dev_read_command(x)) == read_command(x)


def test_frames_are_wellformed_sysex_for_the_foot():
    s = Session()
    for frame in (s.dev_handshake(), s.dev_session(), s.dev_exit(), s.dev_read_command(0x05)):
        b = bytes(frame)
        assert b[:4] == bytes([0xF0, 0x00, 0x00, DEFAULT_MODEL]) and b[-1] == 0xF7


def test_dev_read_cmds_matches_the_confirmed_command_table():
    got = {int(x): (int(rt), int(rl)) for x, rt, rl in Session().dev_read_cmds()}
    assert got == FOOT_READ_CMDS


@requires_rjm
def test_read_cmd_record_lengths_match_decoded_lengths():
    # serial.js slices the device stream into rlen-sized records; rlen must equal the codec's
    # decoded value-count for that record type or every slice would be misaligned.
    dump = Dump.from_file(str(RJM))
    by_type = {}
    for f in dump.frames:
        by_type.setdefault(f.type, len(f.values))
    for _cmd, (rtype, rlen) in FOOT_READ_CMDS.items():
        assert rtype in by_type, f"record type {rtype} missing from the RJM reference dump"
        assert by_type[rtype] == rlen, f"record type {rtype}: codec {by_type[rtype]} != table {rlen}"


# ---- the pull path: device stream -> dev_load, sliced exactly as serial.js does ----

def _slice_like_serial_js(data: bytes, rlen: int) -> list[list[int]]:
    if len(data) % rlen == 1:  # trailing status byte
        data = data[:-1]
    n = len(data) // rlen
    return [list(data[i * rlen:(i + 1) * rlen]) for i in range(n)]


@requires_rjm
def test_dev_load_round_trips_a_simulated_device_read():
    src = Dump.from_file(str(RJM))
    records_by_type = {}
    for _cmd, (rtype, rlen) in FOOT_READ_CMDS.items():
        frames = [f for f in src.frames if f.type == rtype]
        if not frames:
            continue
        # what the device streams for this get-command: count*rlen bytes + 1 status byte
        stream = b"".join(bytes(f.values) for f in frames) + b"\x00"
        records_by_type[rtype] = _slice_like_serial_js(stream, rlen)

    s = Session()
    counts = s.dev_load(records_by_type)
    assert not s.dirty  # a fresh device read is the open document, not an unsaved edit

    for rtype, lists in records_by_type.items():
        got = [list(f.values) for f in s.dump.frames if f.type == rtype]
        assert got == lists, f"record type {rtype} did not survive dev_load"
        assert counts.get(TYPE_NAMES[rtype]) == len(lists)

    # and the loaded document re-encodes: Save after a device pull must work
    assert s.save()[:1] == b"\xf0"


# ---- the write path: dev_write_frame is a valid frame that decodes back to the record ----

def test_dev_write_frame_decodes_back_to_the_same_record():
    s = _loaded_session()
    for rtype in (1, 4, 8):  # Preset, Config, IAMap — all in the device's exposed set
        idx = 0
        frame_bytes = bytes(s.dev_write_frame(rtype, idx))
        assert frame_bytes[:1] == b"\xf0" and frame_bytes[-1:] == b"\xf7"
        parsed = Dump.from_bytes(frame_bytes)
        assert len(parsed.frames) == 1
        f = parsed.frames[0]
        assert f.type == rtype
        assert list(f.values) == list(s._frames(rtype)[idx].values)


def test_dev_write_frame_out_of_range_is_empty():
    s = _loaded_session()
    assert bytes(s.dev_write_frame(1, 9999)) == b""
    assert bytes(s.dev_write_frame(1, -1)) == b""
