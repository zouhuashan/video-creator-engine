#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$ROOT/support/blender/child-lookdev-v1.py"
OUT="$ROOT/renders/lookdev/child-lookdev-v1.png"
BLEND="$ROOT/renders/lookdev/child-lookdev-v1.blend"
LOG="$ROOT/logs/child-lookdev-v1.log"
mkdir -p "$ROOT/renders/lookdev" "$ROOT/logs"

find_blender() {
  local candidate
  for candidate in     "/opt/homebrew/bin/blender"     "/Applications/Blender.app/Contents/MacOS/Blender"     "$(command -v blender 2>/dev/null || true)"
  do
    [ -n "$candidate" ] && [ -x "$candidate" ] && { printf '%s' "$candidate"; return 0; }
  done
  return 1
}

blender="$(find_blender || true)"
if [ -z "$blender" ]; then
  echo "FAIL Blender not installed"
  echo "NEXT ./install-blender.command"
  exit 1
fi

echo "RUN  P28-02 Child LookDev v1"
: >"$LOG"
if ! /usr/bin/arch -arm64 "$blender" --background --factory-startup --python "$SCRIPT" --   --output "$OUT"   --blend-output "$BLEND" >>"$LOG" 2>&1; then
  echo "FAIL P28-02 Child LookDev v1"
  tail -n 120 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -q "VIDEO_CREATOR_CHILD_LOOKDEV_FRAMING_PASS" "$LOG"; then
  echo "FAIL P28-02 framing gate"
  tail -n 120 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -q "VIDEO_CREATOR_CHILD_LOOKDEV_PASS" "$LOG" || [ ! -s "$OUT" ] || [ ! -s "$BLEND" ]; then
  echo "FAIL P28-02 output validation"
  tail -n 120 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "PASS P28-02 technical render"
echo "PNG  $OUT"
echo "BLEND $BLEND"
echo "REVIEW PENDING Child identity / face / hair / costume / lighting"
echo "NEXT P28-02 human visual review"
