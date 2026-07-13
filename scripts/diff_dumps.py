#!/usr/bin/env python3
"""
Diff two LF+ .syx exports at the decoded-value level — the engine of field-offset RE.

Workflow: export a baseline from the real LF+ Editor, change ONE field, re-export, then:

    python scripts/diff_dumps.py base.syx changed.syx

It prints every (record type, record number, value index, old -> new) that differs, which
pins exactly where that field lives in the record. Add the offset to lfeditor/ui/specs.py.
"""
import sys

sys.path.insert(0, "scripts")
from parse_dump import split_frames, parse_frame, decode_values  # noqa: E402

from lfeditor.codec.frame import TYPE_NAMES  # noqa: E402


def index_frames(path):
    out = {}
    for raw in split_frames(open(path, "rb").read()):
        info = parse_frame(raw)
        if info["ok"]:
            out[(info["type"], info["rec_num"])] = decode_values(raw)
    return out


def main(a, b):
    fa, fb = index_frames(a), index_frames(b)
    keys = sorted(set(fa) | set(fb))
    ndiff = 0
    for key in keys:
        va, vb = fa.get(key), fb.get(key)
        if va is None or vb is None:
            print(f"{TYPE_NAMES.get(key[0]):>10} #{key[1]}: present in only one file")
            continue
        for i, (x, y) in enumerate(zip(va, vb)):
            if x != y:
                t = TYPE_NAMES.get(key[0], f"type{key[0]}")
                print(f"{t:>10} #{key[1]:<4} value[{i:3}]  {x:3} (0x{x:02X}) -> {y:3} (0x{y:02X})")
                ndiff += 1
    print(f"\n{ndiff} value(s) differ.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python scripts/diff_dumps.py base.syx changed.syx")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
