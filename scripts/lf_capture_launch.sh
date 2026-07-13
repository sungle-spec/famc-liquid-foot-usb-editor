#!/bin/sh
# Launch the original LF+ Editor with the serial interposer injected so all traffic to/from
# the Liquid Foot+ is logged to scripts/ARTIFACTS/lf_runtime_capture.txt.
#
# Run this FROM A TERMINAL (double-clicking the .app or `open -a` will NOT inject — macOS
# strips DYLD_* from LaunchServices launches; the binary must be exec'd directly with the env
# set, which only a direct shell launch like this does).
#
#   sh scripts/lf_capture_launch.sh
#
# The editor window is then driven by hand (Connect, toggle a control, Send) — see
# docs/HARDWARE_RE_CAPTURE.md.
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DYLIB="$REPO/scripts/ARTIFACTS/lf_interpose.dylib"
if [ ! -f "$DYLIB" ]; then
    echo "building interposer…"
    clang -arch x86_64 -dynamiclib -O2 -o "$DYLIB" "$REPO/scripts/lf_interpose.c" || exit 1
fi
export DYLD_INSERT_LIBRARIES="$DYLIB"
exec "/Applications/LF+ Editor.app/Contents/MacOS/LF+ Editor"
