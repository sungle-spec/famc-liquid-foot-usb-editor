#!/bin/sh
# Launch the ORIGINAL LF+ Editor with the serial-traffic interposer so we can capture
# exactly how it saves expression-pedal calibration. Traffic appends to
# scripts/ARTIFACTS/lf_runtime_capture.txt. Run this in a Terminal you own.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
export LF_CAPTURE_LOG="$DIR/scripts/ARTIFACTS/lf_runtime_capture.txt"
export DYLD_INSERT_LIBRARIES="$DIR/scripts/ARTIFACTS/lf_interpose_uni.dylib"
exec "/Applications/LF+ Editor.app/Contents/MacOS/LF+ Editor"
