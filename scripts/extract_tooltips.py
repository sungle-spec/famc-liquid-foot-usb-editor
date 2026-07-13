#!/usr/bin/env python3
"""
Extract every control tooltip (Xojo "HelpTag"/Tooltip) from the original FAMC LF+ Editor binary.

The compiled Xojo app stores each control's properties as length-prefixed strings:
``<PropName><space><uint32 little-endian length><utf-8 bytes>``. A control's ``Tooltip`` is the
exact text the editor shows on hover; ``Name`` is the control id; ``InitialParent`` is the
containing GroupBox/TabPanel; a GroupBox's ``Caption`` is the on-screen section title.

This parser walks every ``Tooltip`` occurrence, grabs the nearest preceding ``Name`` /
``InitialParent`` / ``Caption`` in the same control block, then resolves the parent chain to a
section caption so the output can be grouped the way the UI looks. Output: JSON (all fields) +
a grouped Markdown reference.

Usage:
    python3 scripts/extract_tooltips.py ["/Applications/LF+ Editor.app/Contents/MacOS/LF+ Editor"]
        [--json out.json] [--md out.md]

The binary is third-party reference material (not redistributed); this only reads it locally.
"""
from __future__ import annotations
import json, re, struct, sys, argparse
from collections import OrderedDict

DEFAULT_BIN = "/Applications/LF+ Editor.app/Contents/MacOS/LF+ Editor"
PROP_RE = re.compile(rb"([A-Za-z][A-Za-z0-9_]{2,30}) ")


def read_len_prefixed(data: bytes, after: int, lo=0, hi=5000):
    """At byte `after`, read <uint32 LE len><len bytes>; return (text, end) or None."""
    if after + 4 > len(data):
        return None
    ln = struct.unpack_from("<I", data, after)[0]
    if not (lo <= ln < hi):
        return None
    raw = data[after + 4: after + 4 + ln]
    if raw and not all(9 <= b < 127 or b >= 160 for b in raw):
        return None
    return raw.decode("utf-8", "replace"), after + 4 + ln


def control_blocks(data: bytes):
    """Yield (start, name) for every control, delimited by its `Name <len> <ident>` property.
    A control's properties live in [start, next_start)."""
    blocks = []
    for m in re.finditer(rb"Name ", data):
        # require a standalone "Name" property, not the tail of "FontName"/"sendFontName"/etc.
        prev = data[m.start() - 1] if m.start() else 0
        if 65 <= prev <= 90 or 97 <= prev <= 122:   # ASCII letter before -> part of a longer word
            continue
        got = read_len_prefixed(data, m.end(), hi=80)
        if not got:
            continue
        val, _ = got
        if val and re.fullmatch(r"[A-Za-z0-9_]+", val):
            blocks.append((m.start(), val))
    return blocks


def prop_in(data: bytes, lo: int, hi: int, name: bytes, maxlen=4000):
    """First `name <len> <utf8>` whose marker is within [lo, hi)."""
    seg = data[lo:hi]
    m = re.search(re.escape(name) + b" ", seg)
    if not m:
        return None
    got = read_len_prefixed(seg, m.end(), hi=maxlen)
    return got[0] if got else None


def extract(path: str):
    data = open(path, "rb").read()
    blocks = control_blocks(data)        # (offset_of_Name, name), in order
    # Xojo serialises a control's properties (Tooltip/InitialParent/Caption/…) BEFORE its Name,
    # so a control "owns" the byte range ending at its Name: (prev_name_offset, this_name_offset].
    captions = {}
    for i, (start, name) in enumerate(blocks):
        lo = blocks[i - 1][0] if i else 0
        cap = prop_in(data, lo, start, b"Caption", maxlen=160)
        if cap and cap.strip():
            captions.setdefault(name, cap)

    rows = []
    for i, (start, name) in enumerate(blocks):
        lo = blocks[i - 1][0] if i else 0
        parent = prop_in(data, lo, start, b"InitialParent", maxlen=80)
        own_caption = captions.get(name)
        section = captions.get(parent or "", "")
        for m in re.finditer(rb"Tooltip ", data[lo:start]):
            got = read_len_prefixed(data[lo:start], m.end(), hi=4000)
            if not got or not got[0].strip():
                continue
            rows.append(OrderedDict(
                offset=lo + m.start(), control=name, parent=parent, section=section,
                caption=own_caption, tooltip=got[0].replace("\r", "\n"),
            ))
    rows.sort(key=lambda r: r["offset"])   # binary order ≈ window/tab layout order
    return rows, captions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("binary", nargs="?", default=DEFAULT_BIN)
    ap.add_argument("--json", default="scripts/ARTIFACTS/lf_tooltips.json")
    ap.add_argument("--md", default="scripts/ARTIFACTS/lf_tooltips.md")
    args = ap.parse_args()

    rows, captions = extract(args.binary)
    # de-duplicate identical (control, tooltip) pairs, keep first
    seen, uniq = set(), []
    for r in rows:
        key = (r["control"], r["tooltip"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)

    with open(args.json, "w") as fh:
        json.dump(uniq, fh, indent=2, ensure_ascii=False)

    # one entry per unique tooltip TEXT, listing the control(s) that use it, in layout order
    by_text = OrderedDict()
    for r in sorted(uniq, key=lambda r: r["offset"]):
        e = by_text.setdefault(r["tooltip"], {"controls": [], "offset": r["offset"]})
        if r["control"] and r["control"] not in e["controls"]:
            e["controls"].append(r["control"])
    with open(args.md, "w") as fh:
        fh.write("# LF+ Editor v6.31 — control tooltips (extracted from the original app)\n\n")
        fh.write("Every hover tooltip in the original FAMC LF+ Editor, extracted verbatim from the\n"
                 "compiled app, in the app's own layout order. Each entry lists the control id(s)\n"
                 "that show that tooltip. Generated by `scripts/extract_tooltips.py` — third-party\n"
                 "reference (FAMC's text), kept for interoperability/preservation.\n\n")
        fh.write(f"**{len(by_text)} unique tooltips** across {len(uniq)} control instances.\n\n")
        for text, e in by_text.items():
            ctrls = ", ".join(f"`{c}`" for c in e["controls"][:6]) or "—"
            fh.write(f"- {text}\n  <br>· _{ctrls}_\n")

    print(f"controls with tooltips: {len(rows)}  unique pairs: {len(uniq)}  "
          f"unique texts: {len(by_text)}")
    print(f"wrote {args.json} and {args.md}")
    # cluster by large offset gaps -> approximate window/tab boundaries
    print("=== offset clusters (≈ windows/tabs); first control + size ===")
    cluster, last = [], None
    clusters = []
    for r in uniq:
        if last is not None and r["offset"] - last > 40000:
            clusters.append(cluster); cluster = []
        cluster.append(r); last = r["offset"]
    if cluster:
        clusters.append(cluster)
    for c in clusters:
        caps = [x["section"] for x in c if x["section"]]
        sig = max(set(caps), key=caps.count) if caps else (c[0]["control"] or "?")
        print(f"  {len(c):3} @ {c[0]['offset']}  sig={sig[:40]!r}  first={c[0]['control']}")


if __name__ == "__main__":
    main()
