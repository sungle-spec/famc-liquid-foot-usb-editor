"""Device communications — USB-serial + MIDI transports and the LF+ sysex protocol.

The read/write protocol is **hardware-confirmed** (see docs/LF_USB_DIRECT.md). Nothing here
touches a device until a transport is opened; writes are gated behind an explicit opt-in
(`protocol.send_record(..., allow_write=True)`)."""
from .ports import discover, find_serial_ports, find_midi_ports, PortInfo
from .transport import Transport, SerialTransport, MidiTransport
from .protocol import (
    handshake_frame, read_command, session_frame, exit_frame, connect, disconnect,
    pull_records, pull_dump, send_record, write_records_live, select_preset, FOOT_READ_CMDS,
    MODEL_FOOT, MODEL_ROUTER, DEFAULT_MODEL,
)

__all__ = [
    "discover", "find_serial_ports", "find_midi_ports", "PortInfo",
    "Transport", "SerialTransport", "MidiTransport",
    "handshake_frame", "read_command", "session_frame", "exit_frame", "connect", "disconnect",
    "pull_records", "pull_dump", "send_record", "write_records_live", "select_preset",
    "FOOT_READ_CMDS", "MODEL_FOOT", "MODEL_ROUTER", "DEFAULT_MODEL",
]
