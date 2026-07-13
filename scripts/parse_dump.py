#!/usr/bin/env python3
"""
FAMC Liquid Foot+ sysex dump segmenter / analyser.

A full-device dump (or a saved .syx) is a concatenation of FAMC sysex frames:

    F0 00 00 <ID> 00 <TYPE> <SUB> <num...> <len...> <nibble data> <cksum:4 nibbles> F7

Every data value is nibble-encoded: one byte -> (hi_nibble, lo_nibble), so each
logical value occupies 2 sysex bytes. The 4-nibble trailer is the sum of all data
nibble-bytes (mod 2^16), checked against the running sum (see Preset.SetFromSysex
in the decompiled JAR).

TYPE (byte 5), from the decompiled `liquidfoot` package:
    1 = Preset      2 = Song       3 = IASwitch
    4 = Config      5 = Setlist    6 = SysexMSG

Some types put a 4-nibble record number at bytes 7..10 then a 2-nibble length at
11..12 (data @13); others a 2-nibble number at 7..8 then 2-nibble length at 9..10
(data @11). We auto-detect the data offset by which one makes the checksum verify.

Usage:
    python scripts/parse_dump.py <file.syx> [file2.syx ...]
"""
import sys
from collections import Counter, defaultdict

TYPE_NAMES = {
    1: "Preset", 2: "Song", 3: "IASwitch", 4: "Config", 5: "Setlist", 6: "SysexMSG",
    7: "v6_tbl7", 8: "v6_tbl8", 9: "v6_preset_ext9", 10: "v6_preset_ext10", 11: "v6_song_ext11",
}

# Per-type header layout for the 2020 (v6.31) format. Empirically fit against the
# device dumps: there is NO trailing checksum (the 2013 JAR had a 4-nibble checksum;
# v6 firmware dropped it). Types whose record count can exceed 255 use a 4-nibble
# record number (bytes 7..10) with data starting at 13; the rest use a 2-nibble
# number (bytes 7..8) with data at 11. The value count is in the 2-nibble length
# field just before the data.
#   type -> (data_off, len_hi_byte, recnum_4nibble)
TYPE_LAYOUT = {
    1:  (13, 11, True),   # Preset            len@11..12, recnum@7..10
    2:  (11, 9,  False),  # Song              len@9..10,  recnum@7..8
    3:  (11, 9,  False),  # IASwitch
    4:  (11, 9,  False),  # Config / Global
    5:  (11, 9,  False),  # Setlist
    6:  (11, 9,  False),  # SysexMSG
    7:  (11, 9,  False),  # v6 global table 7
    8:  (11, 9,  False),  # v6 global table 8
    9:  (13, 11, True),   # v6 per-preset extension
    10: (13, 11, True),   # v6 per-preset extension 2
    11: (11, 9,  False),  # v6 per-song extension
}


def split_frames(data: bytes):
    """Yield each F0..F7 frame (inclusive) found in data."""
    i = 0
    n = len(data)
    while i < n:
        if data[i] != 0xF0:
            i += 1
            continue
        j = data.find(0xF7, i + 1)
        if j == -1:
            break
        yield data[i : j + 1]
        i = j + 1


def decode_values(frame: bytes):
    """Decode a frame's nibble-encoded payload into a list of byte values."""
    t = frame[5]
    data_off, len_hi, recnum4 = TYPE_LAYOUT[t]
    nv = (frame[len_hi] << 4) + (frame[len_hi + 1] & 0xF)
    region = frame[data_off : data_off + 2 * nv]
    return [(region[k] << 4) | (region[k + 1] & 0xF) for k in range(0, len(region), 2)]


def parse_frame(frame: bytes):
    """Return a dict describing one frame (2020/v6.31 layout, no checksum)."""
    info = {
        "len": len(frame), "id": None, "type": None, "sub": None,
        "data_off": None, "n_values": None, "ok": False, "rec_num": None,
    }
    if len(frame) < 13 or frame[0] != 0xF0 or frame[-1] != 0xF7:
        return info
    info.update(id=frame[3], type=frame[5], sub=frame[6])
    t = frame[5]
    if t not in TYPE_LAYOUT:
        return info
    data_off, len_hi, recnum4 = TYPE_LAYOUT[t]
    nv = (frame[len_hi] << 4) + (frame[len_hi + 1] & 0xF)
    expected = data_off + 2 * nv + 1  # + F7, no checksum
    info["data_off"] = data_off
    info["n_values"] = nv
    info["ok"] = (expected == len(frame))
    if recnum4:
        info["rec_num"] = (frame[7] << 12) + (frame[8] << 8) + (frame[9] << 4) + (frame[10] & 0xF)
    else:
        info["rec_num"] = (frame[7] << 4) + (frame[8] & 0xF)
    return info


def analyse(path: str):
    data = open(path, "rb").read()
    frames = list(split_frames(data))
    by_type = Counter()
    lens_by_type = defaultdict(set)
    nval_by_type = defaultdict(set)
    bad = 0
    nums_by_type = defaultdict(list)
    reencode_ok = True
    for fr in frames:
        info = parse_frame(fr)
        t = info["type"]
        by_type[t] += 1
        if info["ok"]:
            lens_by_type[t].add(info["len"])
            nval_by_type[t].add(info["n_values"])
            nums_by_type[t].append(info["rec_num"])
        else:
            bad += 1
    # Byte-exact round-trip check: re-encode every byte of the file by splitting
    # frames and re-nibble-encoding the decoded values back into place.
    reencoded = bytearray()
    for fr in frames:
        info = parse_frame(fr)
        if not info["ok"]:
            reencoded += fr
            continue
        off = info["data_off"]
        vals = decode_values(fr)
        body = bytearray(fr[:off])
        for v in vals:
            body.append((v >> 4) & 0xF)
            body.append(v & 0xF)
        body += fr[off + 2 * len(vals):]
        reencoded += body
    # account for any inter-frame bytes (there are none in these dumps)
    reencode_ok = bytes(reencoded) == bytes().join(frames)

    print(f"\n=== {path} ===")
    print(f"total bytes: {len(data):,}   frames: {len(frames)}   "
          f"bad-frames: {bad}   roundtrip: {'OK' if reencode_ok else 'MISMATCH'}")
    print(f"{'type':>6} {'name':<10} {'count':>6} {'frame_len(s)':<18} {'n_values':<14} num_range")
    for t in sorted(by_type, key=lambda x: (x is None, x)):
        name = TYPE_NAMES.get(t, "?")
        lens = sorted(lens_by_type[t])
        nvals = sorted(nval_by_type[t])
        nums = nums_by_type[t]
        numrange = f"{min(nums)}..{max(nums)}" if nums else "-"
        lens_s = ",".join(map(str, lens))[:17]
        print(f"{str(t):>6} {name:<10} {by_type[t]:>6} {lens_s:<18} {str(nvals):<14} {numrange}")


if __name__ == "__main__":
    paths = sys.argv[1:] or ["reference/sysex_dumps/FAMC12plus_new.syx"]
    for p in paths:
        analyse(p)
