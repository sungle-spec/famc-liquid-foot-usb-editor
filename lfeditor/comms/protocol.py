"""
Liquid Foot+ device protocol over the USB-serial (FTDI VCP) link.

**Confirmed on hardware 2026-06-15** against a real Liquid Foot+ (see docs/LF_USB_DIRECT.md).
This supersedes the earlier 2013-JAR assumption (a `00 CMD 02` MIDI command frame); the modern
Xojo editor — and this code — speak the raw framed-serial protocol the Liquid Router uses, with
only the MODEL byte changed (Router 0x7A → Foot 0x7C).

Wire format (raw bytes — NOT MIDI; data may exceed 0x7F):

    F0 00 00 <MODEL> <dir> .. <cmd> .. F7      dir 0x00 = host→device, 0x05 = device→host

* **Connect handshake** (enters the device's *Editor Mode*): ``F0 00 00 7C 0F 0F C9 00 00 00 00 F7``
  — the device replies ``F0 05 00 7C …`` and the front panel shows "Editor Mode [sel] to exit".
* **Read get-command**: ``F0 00 00 7C 0F 0F <X> F7`` — the device streams back the **decoded**
  record values for that data type (concatenated fixed-length records + a trailing status byte),
  NOT nibble-encoded frames. See ``FOOT_READ_CMDS``.
* **Write**: replay/splice a record's ``F0 00 00 7C 00 <type> 01 <recnum> <len> <nibbles> 00 F7``
  frame (the .syx backup format). The device **ACKs each write with ``F0 09 F7``** (confirmed
  against the real editor's captured traffic — three writes drew three ACKs). Belt-and-braces, a
  read-back also confirms it.

The exact editor connect/read/write/disconnect sequence is the one the real LF+ Editor uses
(verified by a DYLD interposer capture of its full serial session, connect → reads/writes →
disconnect): handshake (×) → ``CA`` → get-commands → writes → ``CC`` → close port. ``CC`` is a
context-sensitive stop control: it leaves an ordinary editor session, stops expression-pedal live
view, and stops the live USB-MIDI stream. See LF_USB_DIRECT.md.

SAFETY: ``send_record`` refuses to transmit unless ``allow_write=True`` is passed explicitly.
"""
from __future__ import annotations

from .transport import Transport
from ..codec import Dump
from ..codec.frame import Frame, TYPE_LAYOUT

MODEL_FOOT = 0x7C    # Liquid Foot+ (also the device sysex ID in every frame header)
MODEL_ROUTER = 0x7A  # Liquid Router (sibling device, same firmware family)
DEFAULT_MODEL = MODEL_FOOT

# Control bytes (all sent with the 0F 0F prefix), from captured original-editor sessions:
#   C9 = handshake / enter Editor Mode   CA = session-begin (sent once after the handshake)
#   CF = start live bidirectional USB-MIDI streaming (after C9 + CA)
#   CC = context-sensitive stop: editor disconnect, USB-MIDI stream, or expression live view
HANDSHAKE_CTRL = 0xC9
SESSION_CTRL = 0xCA
USB_MIDI_STREAM_START_CTRL = 0xCF
USB_MIDI_STREAM_STOP_CTRL = 0xCC
EXIT_CTRL = USB_MIDI_STREAM_STOP_CTRL  # compatibility name for ordinary editor disconnect
LIVE_VIEW_CTRL = 0xD2   # start expression-pedal positions (also stopped by context-sensitive CC)
READ_PREFIX = (0x0F, 0x0F)
WRITE_ACK = b"\xf0\x09\xf7"  # the device's per-write acknowledgement
LIVE_WRITE_PRELUDE = b"\xff"  # 0xFF byte the editor sends before writing config *during* live view
NUM_PEDALS = 4
LIVE_DELIM = 0xFE       # the live-position stream is FE-delimited 8-byte frames

# Foot read get-commands, confirmed on hardware. cmd -> (record_type, record_len_bytes).
# The device streams `count * record_len` decoded bytes + 1 trailing status byte. Record
# lengths are the codec's decoded value-counts. (0x0E returns the firmware-data stream, not a
# stored record type — see Get_All_Firmware_Data below — so it is intentionally omitted.)
#
# 0x07/0x08/0x09 (Page/Song/Setlist) were found 2026-07-16 by disassembling the original v6.31
# macOS editor (Xojo, full symbol table): its Window1.Get_All_Pages/Songs/SetLists methods each
# build exactly this bulk frame with X=0x07/0x08/0x09. The same disassembly's OTHER Get_All_*
# methods matched our hardware-confirmed cmd bytes exactly (Presets 0x05, Sysex 0x0A, Config
# 0x0B, IASlotMapping 0x0C, IALabels 0x0D, MAPLabels 0x0F, SongPresetLabels 0x10, and Firmware
# Data 0x0E), which validates the method for the three new ones. This *contradicts* the
# 2026-06-15 manual probe that logged no reply for 0x01-0x20 on Song/Setlist/Page — that probe's
# negative result was apparently a timeout/session-state artifact, not a real device limit.
# **All three (0x07/0x08/0x09) confirmed on a real LF+ 12+ the same day** via
# `scripts/probe_bulk_pages.py`: exact expected reply lengths (Page 50*210+1, Song 254*125+1,
# Setlist 128*90+1 bytes) and bulk Song's first record byte-identical to the already-proven
# per-record path. 0x06 (IASwitch) was ALSO found live in that same hardware session — not in
# the disassembly (the original editor computes that command byte at runtime, so it didn't show
# up as a literal in the binary) but the probe's byte-shape scan turned it up: reply length
# exactly 180*250+1 bytes, content matching real IA-slot effect names ("Sound Sculpture Fun",
# "Keeley Compress Comp") and the Step Names field, and byte-identical to per-record IASwitch
# rec 0. So every per-record type now has a bulk equivalent too — the per-record path
# (FOOT_PER_RECORD_CMDS below) becomes a pure fallback, kept as a safety net in case a given
# firmware/model combination doesn't answer one of these four.
FOOT_READ_CMDS: dict[int, tuple[int, int]] = {
    0x05: (1, 170),    # Preset
    0x06: (3, 250),    # IASwitch
    0x07: (7, 210),    # Page
    0x08: (2, 125),    # Song
    0x09: (5, 90),     # Setlist
    0x0D: (9, 80),     # PresetExt9
    0x0F: (10, 160),   # PresetExt10
    0x0A: (6, 42),     # SysexMsg
    0x0B: (4, 250),    # Config
    0x0C: (8, 100),    # IAMap
    0x10: (11, 96),    # SongExt11
}
# reverse lookup: record type -> its bulk get-command byte
READ_CMD_FOR_TYPE: dict[int, int] = {rt: cmd for cmd, (rt, _l) in FOOT_READ_CMDS.items()}

# 2013-editor-style PER-RECORD read: `F0 00 00 <id> 00 <cmd> 02 <recnum 4 nibbles> F7`, one
# request per record, one genuine .syx record frame back (parseable directly via Frame.parse —
# unlike FOOT_READ_CMDS's bulk stream, no header synthesis needed). **Confirmed on hardware
# 2026-07-15**: this is how Song/Setlist/IASwitch transfer over USB — originally the only way to
# reach them at all, before Song/Setlist/IASwitch each gained a bulk equivalent (0x08/0x09/0x06,
# found 2026-07-16). This path now stays only as pull_dump()'s automatic fallback for whichever
# of the three a given device doesn't answer over bulk. `recnum` is 0-based, matching the
# on-disk record number exactly (verified: requesting recnum=1 returns the on-disk rec_num=1
# record, byte-identical). cmd -> (record_type, record_count).
FOOT_PER_RECORD_CMDS: dict[int, tuple[int, int]] = {
    0x0B: (2, 254),   # Song
    0x0D: (5, 128),   # Setlist
    0x0C: (3, 180),   # IASwitch
}
# reverse lookup: record type -> its per-record cmd byte
PER_RECORD_CMD_FOR_TYPE: dict[int, int] = {rt: cmd for cmd, (rt, _c) in FOOT_PER_RECORD_CMDS.items()}


def frame_bytes(model: int, *body: int) -> bytes:
    """Build a raw F0 00 00 <model> <body...> F7 frame."""
    return bytes([0xF0, 0x00, 0x00, model & 0x7F, *body, 0xF7])


def handshake_frame(model: int = DEFAULT_MODEL) -> bytes:
    """The connect handshake that puts the device into Editor Mode."""
    return frame_bytes(model, *READ_PREFIX, HANDSHAKE_CTRL, 0x00, 0x00, 0x00, 0x00)


def read_command(x: int, model: int = DEFAULT_MODEL) -> bytes:
    """A get-command frame requesting data type `x` (see FOOT_READ_CMDS)."""
    return frame_bytes(model, *READ_PREFIX, x)


def per_record_read_command(cmd: int, rec_num: int, model: int = DEFAULT_MODEL) -> bytes:
    """A per-record get-command frame requesting one record by (0-based) number.

    See FOOT_PER_RECORD_CMDS. `cmd` is the 2013 SendMsg wire byte for the type."""
    return frame_bytes(model, 0x00, cmd, 0x02,
                        (rec_num >> 12) & 0xF, (rec_num >> 8) & 0xF,
                        (rec_num >> 4) & 0xF, rec_num & 0xF)


def select_preset(transport: Transport, preset_1based: int, midi_chan: int = 0) -> None:
    """Select a preset on the device via Bank Select (CC0) + Program Change.

    **Hardware-confirmed 2026-07-15**: the LF+ acts on channel-voice CC/PC arriving on the
    USB-serial UART — but ONLY when the device global "Allow MIDI in" is YES (Config rec 0
    value[47]) AND `midi_chan` matches the device's global MIDI channel (Config rec 0 value[49],
    0-based). The bidirectional USB MIDI Bridge uses this conservative input route after the
    verified C9 → CA → CF live-stream setup."""
    if not 1 <= preset_1based <= 384:
        return
    n = preset_1based - 1
    bank, prog = n // 128, n % 128
    transport.send(bytes([0xB0 | (midi_chan & 0xF), 0x00, bank]))
    transport.send(bytes([0xC0 | (midi_chan & 0xF), prog]))


def session_frame(model: int = DEFAULT_MODEL) -> bytes:
    """The 'begin session' control the editor sends once after the handshake (no reply)."""
    return frame_bytes(model, *READ_PREFIX, SESSION_CTRL)


def exit_frame(model: int = DEFAULT_MODEL) -> bytes:
    """The CC stop control used for an ordinary editor disconnect (no reply).

    The same byte has context-sensitive stop semantics for USB-MIDI streaming and expression
    live view; use their explicitly named builders in those contexts.
    """
    return frame_bytes(model, *READ_PREFIX, EXIT_CTRL)


def usb_midi_stream_start_frame(model: int = DEFAULT_MODEL) -> bytes:
    """Start verified LF+ live USB-MIDI streaming after the C9 → CA session setup."""
    return frame_bytes(model, *READ_PREFIX, USB_MIDI_STREAM_START_CTRL)


def usb_midi_stream_stop_frame(model: int = DEFAULT_MODEL) -> bytes:
    """Stop LF+ live USB-MIDI streaming while leaving the serial port open."""
    return frame_bytes(model, *READ_PREFIX, USB_MIDI_STREAM_STOP_CTRL)


def live_view_start_frame(model: int = DEFAULT_MODEL) -> bytes:
    """Start the live expression-pedal position stream (D2). The device then continuously sends
    FE-delimited 8-byte frames until it gets the stop control."""
    return frame_bytes(model, *READ_PREFIX, LIVE_VIEW_CTRL)


def live_view_stop_frame(model: int = DEFAULT_MODEL) -> bytes:
    """Stop expression-pedal live view with the context-sensitive CC stop control."""
    return frame_bytes(model, *READ_PREFIX, USB_MIDI_STREAM_STOP_CTRL)


def parse_live_positions(buf: bytes) -> tuple[list[list[int]], bytes]:
    """Decode the live-view stream. Each frame is `FE <p0_hi p0_lo> … <p3_hi p3_lo> FE`: four
    16-bit **big-endian** ADC positions, one per pedal (confirmed on a real LF+ 12+, 2026-06-16).

    Returns (list_of_complete_frames, leftover_bytes) so a streaming reader can feed partial
    chunks and keep the trailing remainder for the next call. Each frame is a 4-int list."""
    frames: list[list[int]] = []
    parts = buf.split(bytes([LIVE_DELIM]))
    # parts[0] is a (possibly partial) leading fragment; the last part is the unfinished tail.
    for part in parts[1:-1]:
        if len(part) == NUM_PEDALS * 2:
            frames.append([(part[2 * p] << 8) | part[2 * p + 1] for p in range(NUM_PEDALS)])
    leftover = bytes([LIVE_DELIM]) + parts[-1] if len(parts) > 1 else buf
    return frames, leftover


def disconnect(transport: Transport, model: int = DEFAULT_MODEL) -> None:
    """Leave Editor Mode (CC) so the device returns to normal operation, then close the link.

    Mirrors the real editor's disconnect: send CC, then close the port. The device's LCD drops
    out of 'Editor Mode' (no need to press [sel])."""
    try:
        transport.send(exit_frame(model))
        import time
        time.sleep(0.2)
    finally:
        transport.close()


def connect(transport: Transport, model: int = DEFAULT_MODEL,
            retries: int = 6) -> bytes:
    """Handshake into Editor Mode, send the session-begin control, return the device reply.

    Mirrors the real editor's connect sequence (C9 handshake, then CA). The device occasionally
    drops a handshake right after a previous session; retry with a short gap. Returns the reply
    bytes (``F0 05 00 <model> …``) or b"" if it never answered. Do NOT toggle DTR low between
    attempts — that disturbs the FTDI/MCU and wedges the link.
    """
    import time
    for _ in range(retries):
        transport.send(handshake_frame(model))
        reply = b"".join(transport.read_raw(idle_timeout=0.4, overall_timeout=1.2))
        if reply:
            transport.send(session_frame(model))      # CA — editor-faithful, returns nothing
            transport.read_raw(idle_timeout=0.3, overall_timeout=0.6)
            return reply
        time.sleep(1.5)
    return b""


def pull_records(transport: Transport, model: int = DEFAULT_MODEL,
                 cmds=None) -> dict[int, list[list[int]]]:
    """Read the device's data types and return {record_type: [values, ...]}.

    Assumes `connect()` has already put the device in Editor Mode. Streams each get-command,
    strips the trailing status byte, and slices the concatenated stream into fixed-length
    decoded records per FOOT_READ_CMDS. Non-destructive."""
    cmds = list(FOOT_READ_CMDS) if cmds is None else list(cmds)
    out: dict[int, list[list[int]]] = {}
    for x in cmds:
        if x not in FOOT_READ_CMDS:
            continue
        rtype, rlen = FOOT_READ_CMDS[x]
        transport.send(read_command(x, model))
        data = b"".join(transport.read_raw())
        if not data:
            continue
        if len(data) % rlen == 1:        # drop the trailing status byte
            data = data[:-1]
        n = len(data) // rlen
        out[rtype] = [list(data[i * rlen:(i + 1) * rlen]) for i in range(n)]
    return out


#: A slot legitimately not being populated is expected (see docstring below), so a handful of
#: misses in a row is normal. But a device that has stopped answering ENTIRELY for a type (wrong
#: firmware, wedged link) would otherwise burn the full 3.0s timeout on every remaining slot —
#: up to ~28 minutes across all 562 requests with zero UI feedback, indistinguishable from a
#: true hang (this is what a 2026-07-16 forum report turned out to be). Bailing out after this
#: many CONSECUTIVE misses (reset by any hit) bounds the worst case to ~2-4 minutes instead,
#: without risking a false trigger on real sparse-but-populated data (30 unpopulated slots in a
#: row, in what's usually a contiguously-filled list, is an extreme case) — and it's non-
#: destructive: a bailed-out type just has fewer records refreshed this pull, recoverable via a
#: manual per-record "From LF+" (pull_one_record_per_record) on the specific slot if needed.
MAX_CONSECUTIVE_MISSES = 30


def _read_one_reply(transport: Transport, overall_timeout: float = 3.0) -> bytes:
    """Read exactly one per-record reply — via the fast frame-boundary-aware
    `transport.read_one_frame` when the transport supports it (real `SerialTransport`/
    `MidiTransport`), else the generic idle-timeout `read_raw` (test fakes and any other
    Transport that hasn't grown the new method).

    **Why this matters:** each per-record reply is always exactly one bounded F0..F7 frame, so
    waiting for it is really "wait for the terminating F7", not "wait until nothing has arrived
    for a while" — but `read_raw`'s idle-timeout drain does the latter, paying a fixed
    idle_timeout tax on *every single request* just to reconfirm silence the F7 already implied.
    At ~562 requests in a full per-record sweep, that tax alone (0.3s) added ~2.8 minutes versus
    the original editor, which doesn't pay it — found 2026-07-16 chasing a "hangs on reading
    device" report that turned out to be this slowness, not an actual device stall (the earlier
    MAX_CONSECUTIVE_MISSES bail-out below handles the *genuine*-stall case; this handles the
    *not actually stalled, just slower than it needs to be* case, which was the bigger factor)."""
    read_one = getattr(transport, "read_one_frame", None)
    if read_one is not None:
        return read_one(overall_timeout=overall_timeout)
    return b"".join(transport.read_raw(idle_timeout=0.3, overall_timeout=overall_timeout))


def pull_records_per_record(transport: Transport, model: int = DEFAULT_MODEL,
                            cmds=None, on_progress=None,
                            max_consecutive_misses: int = MAX_CONSECUTIVE_MISSES) -> list[Frame]:
    """Read Song/Setlist/IASwitch one record at a time (see FOOT_PER_RECORD_CMDS) — the path
    the bulk get-commands in FOOT_READ_CMDS cannot reach.

    Assumes `connect()` has already put the device in Editor Mode. Unlike `pull_records`, the
    device's reply to each request is already a genuine .syx record frame, so it is parsed
    directly with no header synthesis. A record the device doesn't answer for is skipped (not
    every slot need be populated) — but `max_consecutive_misses` unanswered requests IN A ROW for
    one type gives up on the REST of that type's range (see MAX_CONSECUTIVE_MISSES) rather than
    grinding through every remaining slot's full timeout. `on_progress(cmd, rec_num, count)` is
    called before each request, if given, since this is ~562 requests end to end. Each reply is
    read via `_read_one_reply` (fast frame-boundary-aware read on real hardware — see its
    docstring for why the naive idle-timeout drain was the actual cause of a "hangs" report)."""
    cmds = list(FOOT_PER_RECORD_CMDS) if cmds is None else list(cmds)
    frames: list[Frame] = []
    for cmd in cmds:
        if cmd not in FOOT_PER_RECORD_CMDS:
            continue
        _rtype, count = FOOT_PER_RECORD_CMDS[cmd]
        misses = 0
        for rec_num in range(count):
            if on_progress:
                on_progress(cmd, rec_num, count)
            transport.send(per_record_read_command(cmd, rec_num, model))
            data = _read_one_reply(transport)
            if not data:
                misses += 1
                if misses >= max_consecutive_misses:
                    break
                continue
            misses = 0
            try:
                frames.append(Frame.parse(data))
            except ValueError:
                continue
    return frames


def pull_one_record_per_record(transport: Transport, type_: int, rec_num: int,
                               model: int = DEFAULT_MODEL) -> Frame | None:
    """Read a single Song/Setlist/IASwitch record by (type, 0-based rec_num).

    For scoped single-record refreshes (e.g. a per-record "From LF+" button) — much cheaper
    than pulling the whole type's range via `pull_records_per_record`. Returns None if `type_`
    isn't a per-record type or the device didn't answer."""
    cmd = PER_RECORD_CMD_FOR_TYPE.get(type_)
    if cmd is None:
        return None
    transport.send(per_record_read_command(cmd, rec_num, model))
    data = _read_one_reply(transport)
    if not data:
        return None
    try:
        return Frame.parse(data)
    except ValueError:
        return None


def pull_dump(transport: Transport, model: int = DEFAULT_MODEL, cmds=None,
              per_record: bool = True, on_progress=None) -> Dump:
    """Full read: handshake, pull every readable data type, wrap into a Dump.

    Bulk-path records (FOOT_READ_CMDS) are synthesised from the decoded values using a
    per-type header template so they re-encode to the device's .syx frame format (and can be
    written back). `per_record=True` (default) additionally runs the per-record path
    (FOOT_PER_RECORD_CMDS) as a FALLBACK, but only for types the bulk phase didn't already
    return records for — Song/Setlist/IASwitch normally all come back over their bulk commands
    (0x08/0x09/0x06) and are skipped here, saving up to 562 redundant per-record round trips. If
    a device/firmware doesn't answer one of those three over bulk, this transparently recovers
    it per-record instead — pass `per_record=False` to skip the fallback entirely (e.g. for a
    quick preset-only pull).
    `on_progress` is forwarded to `pull_records_per_record` — wire it up so the caller can show
    live progress during the per-record sweep, which is otherwise indistinguishable from a hang
    (see MAX_CONSECUTIVE_MISSES). The handshake is sent here; callers that already connected can
    pass an open, post-handshake transport — a second handshake is harmless."""
    connect(transport, model)
    recs = pull_records(transport, model, cmds)
    dump = Dump()
    for rtype, value_lists in recs.items():
        for rec_num, values in enumerate(value_lists):
            dump.frames.append(_synth_frame(rtype, rec_num, values, model))
    if per_record:
        remaining = [cmd for cmd, (rtype, _count) in FOOT_PER_RECORD_CMDS.items()
                    if not recs.get(rtype)]
        dump.frames.extend(pull_records_per_record(transport, model, cmds=remaining,
                                                    on_progress=on_progress))
    return dump


def _synth_frame(rtype: int, rec_num: int, values: list[int], model: int) -> Frame:
    """Build a Frame whose .raw header re-encodes to the device .syx write format."""
    data_off, len_hi, recnum4 = TYPE_LAYOUT[rtype]
    nv = len(values)
    hdr = bytearray([0xF0, 0x00, 0x00, model & 0x7F, 0x00, rtype, 0x01])
    if recnum4:
        hdr += bytes([(rec_num >> 12) & 0xF, (rec_num >> 8) & 0xF,
                      (rec_num >> 4) & 0xF, rec_num & 0xF])
    else:
        hdr += bytes([(rec_num >> 4) & 0xF, rec_num & 0xF])
    # length field (2 nibbles) sits in the two bytes right before the data
    while len(hdr) < len_hi:
        hdr.append(0x00)
    hdr.append((nv >> 4) & 0xF)
    hdr.append(nv & 0xF)
    while len(hdr) < data_off:
        hdr.append(0x00)
    raw = bytes(hdr) + bytes((nv * 2 + 1))  # placeholder body; to_bytes() re-nibbles values
    return Frame(type=rtype, sub=0x01, rec_num=rec_num, dev_id=model & 0x7F,
                 values=list(values), raw=raw)


def send_record(transport: Transport, frame, *, allow_write: bool = False,
                verify_read=None) -> bool:
    """Write ONE record back to the device. Refuses unless `allow_write=True`.

    `frame` is a codec.Frame (or raw .syx-format bytes). The device ACKs with ``F0 09 F7``; this
    waits for that ACK and returns whether it arrived. If `verify_read` (a zero-arg callable
    returning the record's current bytes) is also given, the result must additionally be truthy —
    belt-and-braces confirmation that the write actually landed.
    """
    if not allow_write:
        raise PermissionError(
            "Device writes are disabled. Pass allow_write=True only with hardware connected "
            "and after the user has confirmed — see docs/LF_USB_DIRECT.md."
        )
    data = frame if isinstance(frame, (bytes, bytearray)) else frame.to_bytes()
    flush = getattr(transport, "flush_input", None)
    if flush:                       # clear any stale RX (e.g. trailing live-view stream) first
        flush()
    transport.send(bytes(data))
    acked = WRITE_ACK in b"".join(transport.read_raw(idle_timeout=0.6, overall_timeout=3.0))
    if verify_read is None:
        return acked
    import time
    time.sleep(0.2)
    return acked and bool(verify_read())


def write_records_live(transport: Transport, frames, *, allow_write: bool = False) -> bool:
    """Write records back **while the live-view stream is running** — how the original editor
    saves expression-pedal calibration (confirmed by an interposer capture of its session,
    2026-06-17).

    The device will not accept a normal record write around the live stream: stopping it first
    (``CC`` then ``CA``) leaves the device unable to ACK, and a bare write mid-stream is ignored.
    What the original does instead, all WITHOUT leaving the stream: send a single ``0xFF`` prelude
    byte, write every config record frame back-to-back, then read the single ``F0 09 F7`` ACK that
    the device returns after the LAST record. (The ACK arrives mixed into the continuing stream.)

    Do NOT send ``CC``/``CA`` around this. The caller should pause its read loop first so it does
    not race the port, and resume the stream (re-send ``D2``) afterwards.
    """
    if not allow_write:
        raise PermissionError(
            "Device writes are disabled. Pass allow_write=True only with hardware connected "
            "and after the user has confirmed — see docs/LF_USB_DIRECT.md."
        )
    flush = getattr(transport, "flush_input", None)
    if flush:                       # drop buffered live-stream bytes so the trailing ACK is found
        flush()
    transport.send(LIVE_WRITE_PRELUDE)
    for fr in frames:
        data = fr if isinstance(fr, (bytes, bytearray)) else fr.to_bytes()
        transport.send(bytes(data))
    return WRITE_ACK in b"".join(transport.read_raw(idle_timeout=0.6, overall_timeout=3.0))
