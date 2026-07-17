"""Bounded parser for raw MIDI bytes received from the LF+ USB-serial UART.

The LF+ live USB-MIDI stream shares a carrier with FAMC's F0...F7 control protocol. This parser
publishes complete channel-voice messages, safe realtime messages, and unambiguous ordinary
7-bit SysEx. FAMC/system-common/malformed frames are filtered and buffering is bounded.
"""
from __future__ import annotations


_DATA_LENGTH = {
    0x8: 2,  # Note Off
    0x9: 2,  # Note On
    0xA: 2,  # Poly Pressure
    0xB: 2,  # Control Change
    0xC: 1,  # Program Change
    0xD: 1,  # Channel Pressure
    0xE: 2,  # Pitch Bend
}

# Realtime messages safe to republish from the LF+ without changing parser/running-status state.
# Undefined F9/FD and the destructive System Reset FF remain filtered.
LF_TO_COMPUTER_REALTIME = frozenset((0xF8, 0xFA, 0xFB, 0xFC, 0xFE))

# Known LF+ editor/control frame shapes. A user-programmed SysEx with one of these prefixes is
# intentionally filtered too: on this shared carrier it is indistinguishable from protocol data.
_FAMC_PROTOCOL_PREFIXES = (
    bytes.fromhex("f000007c"),  # host→LF+ handshake, controls, reads, and record writes
    bytes.fromhex("f005007c"),  # LF+→host identification/data frame
    bytes.fromhex("f009"),      # LF+ write acknowledgement
)


def is_famc_protocol_frame(frame: bytes) -> bool:
    """Whether a complete F0...F7 frame matches a known LF+ editor/control shape."""
    return any(frame.startswith(prefix) for prefix in _FAMC_PROTOCOL_PREFIXES)


def is_forwardable_sysex(frame: bytes) -> bool:
    """Whether a complete frame is unambiguous, valid 7-bit musical SysEx.

    FAMC-looking frames and frames containing raw protocol bytes above 0x7F are conservatively
    rejected. Computer→LF+ SysEx has a separate, stricter policy and remains entirely blocked.
    """
    return (
        len(frame) >= 2
        and frame[0] == 0xF0
        and frame[-1] == 0xF7
        and all(value < 0x80 for value in frame[1:-1])
        and not is_famc_protocol_frame(frame)
    )


class RawMidiStreamParser:
    """Incrementally decode raw MIDI channel messages from fragmented byte chunks.

    ``feed()`` returns complete messages as wire-format ``bytes``. Safe realtime is returned as
    one-byte messages without disturbing running status. Unambiguous ordinary SysEx is returned;
    FAMC frames are discarded. A malformed/unterminated SysEx sequence is bounded by
    ``max_sysex_bytes``, after which the parser waits for the next ordinary channel status.
    """

    def __init__(self, max_sysex_bytes: int = 1024):
        if max_sysex_bytes < 2:
            raise ValueError("max_sysex_bytes must be at least 2")
        self.max_sysex_bytes = max_sysex_bytes
        self.reset()

    def reset(self) -> None:
        self._running_status: int | None = None
        self._pending = bytearray()
        self._in_sysex = False
        self._sysex = bytearray()

    @property
    def buffered_byte_count(self) -> int:
        """Number of bytes represented by bounded parser state (useful for safety tests)."""
        return len(self._pending) + len(self._sysex)

    def feed(self, chunk: bytes | bytearray | memoryview) -> list[bytes]:
        messages: list[bytes] = []
        for value in bytes(chunk):
            # FAMC frames can contain raw bytes above 0x7F, including realtime-looking values.
            # Once F0 begins, discard/classify the entire frame before interpreting its contents.
            if self._in_sysex:
                if value == 0xF7:
                    if len(self._sysex) < self.max_sysex_bytes:
                        self._sysex.append(value)
                        frame = bytes(self._sysex)
                        if is_forwardable_sysex(frame):
                            messages.append(frame)
                    self._leave_sysex()
                    continue
                if value == 0xF0:
                    self._sysex = bytearray([value])  # malformed nested start: restart
                    continue
                if len(self._sysex) >= self.max_sysex_bytes - 1:
                    self._leave_sysex()
                else:
                    self._sysex.append(value)
                continue

            # Realtime bytes never cancel running status or a partially collected channel
            # message. Publish only the explicitly safe set; filter undefined F9/FD and reset FF.
            if value >= 0xF8:
                if value in LF_TO_COMPUTER_REALTIME:
                    messages.append(bytes([value]))
                continue

            if value == 0xF0:
                self._running_status = None
                self._pending.clear()
                self._in_sysex = True
                self._sysex = bytearray([value])
                continue

            if 0x80 <= value <= 0xEF:
                self._start_channel_status(value)
                continue

            if value >= 0xF1:
                # System-common and stray F7 bytes are filtered and cancel running status.
                self._running_status = None
                self._pending.clear()
                continue

            # Data byte. Without running status it is arbitrary serial garbage and is ignored.
            if self._running_status is None:
                continue
            self._pending.append(value)
            needed = _DATA_LENGTH[self._running_status >> 4]
            if len(self._pending) == needed:
                messages.append(bytes([self._running_status, *self._pending]))
                self._pending.clear()  # running status remains valid for the next message

        return messages

    def _start_channel_status(self, status: int) -> None:
        self._running_status = status
        self._pending.clear()

    def _leave_sysex(self) -> None:
        self._in_sysex = False
        self._sysex.clear()
        self._running_status = None
        self._pending.clear()
