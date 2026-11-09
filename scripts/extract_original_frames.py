#!/usr/bin/env python3
"""List every F0..F7 sysex frame the ORIGINAL LF+ Editor (Xojo, x86_64, unstripped) builds.

Static, never executes the target. Xojo builds each frame by setting bytes in a MemoryBlock via a
vtable call (`callq *0x18(%reg)`) with the index in %esi and the value in %edx; this script walks
the disassembly of every `Window1.*` method and collects those (index, value) constants.

Caveats: bytes computed at runtime (device-ID at idx 3, per-record numbers, Fractal model byte,
checksums) are NOT literals and show as stale/garbage - treat idx 3 as <device id> (0x7C for the
LF+). A routine whose command byte is computed (e.g. Get_All_IASlots) prints without it.

Usage:
    python3 -I scripts/extract_original_frames.py "<path to LF+ Editor binary>" [--out frames.json]
Requires: nm and llvm-objdump (Xcode command line tools). See docs/ORIGINAL_EDITOR_GAP_ANALYSIS.md.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

OBJDUMP = "/Library/Developer/CommandLineTools/usr/bin/llvm-objdump"
HDR = re.compile(r"^[0-9a-f]{16} <(.+)>:$")


def main(binary: str, out: str | None) -> None:
    text = subprocess.run([OBJDUMP, "-d", "--no-show-raw-insn", binary],
                          capture_output=True, text=True, check=True).stdout
    funcs: dict[str, list[str]] = {}
    cur = None
    for line in text.splitlines():
        m = HDR.match(line)
        if m:
            cur = m.group(1)
            funcs[cur] = []
        elif cur:
            funcs[cur].append(line)

    rows = []
    for name, lines in funcs.items():
        if not name.startswith("_Window1.Window1."):
            continue
        last = esi = edx = None
        pairs: dict[int, int] = {}
        count = 0
        for l in lines:
            if "xorl\t%eax, %eax" in l:
                last = 0
            m = re.search(r"movl\s+\$(0x[0-9a-f]+), %eax", l)
            if m:
                last = int(m.group(1), 16)
            m = re.search(r"movl\s+%eax, %(esi|edx)", l)
            if m:
                if m.group(1) == "esi":
                    esi = last
                else:
                    edx = last
            m = re.search(r"movl\s+\$(0x[0-9a-f]+), %(esi|edx)", l)
            if m:
                v = int(m.group(1), 16)
                if m.group(2) == "esi":
                    esi = v
                else:
                    edx = v
            if re.search(r"callq\s+\*0x18\(", l):
                count += 1
                if esi is not None and edx is not None:
                    pairs[esi] = edx
        if count >= 6 and pairs.get(0) == 0xF0:
            seq = [pairs[i] for i in sorted(pairs)]
            short = name.replace("_Window1.Window1.", "").split("%")[0]
            rows.append((short, " ".join(f"{b:02X}" for b in seq)))

    for short, hexs in sorted(rows):
        print(f"{short:48s} {hexs}")
    if out:
        with open(out, "w") as fh:
            json.dump(rows, fh, indent=1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None)
