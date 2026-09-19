#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$ROOT/support/blender/child-lookdev-v4.py"
OUT="$ROOT/renders/lookdev/child-lookdev-v4.png"
BLEND="$ROOT/renders/lookdev/child-lookdev-v4.blend"
LOG="$ROOT/logs/child-lookdev-v4.log"
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

echo "RUN  P28-02 Child LookDev v4"
: >"$LOG"
if ! /usr/bin/arch -arm64 "$blender" --background --factory-startup --python "$SCRIPT" --   --output "$OUT"   --blend-output "$BLEND" >>"$LOG" 2>&1; then
  echo "FAIL P28-02 Child LookDev v4"
  tail -n 180 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -q "VIDEO_CREATOR_CHILD_LOOKDEV_V4_FRAMING_PASS" "$LOG"; then
  echo "FAIL P28-02 v4 framing gate"
  tail -n 180 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -q "VIDEO_CREATOR_CHILD_LOOKDEV_V4_PASS" "$LOG" || [ ! -s "$OUT" ] || [ ! -s "$BLEND" ]; then
  echo "FAIL P28-02 v4 output validation"
  tail -n 180 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "PASS P28-02 v4 technical render"
echo "PNG  $OUT"
echo "BLEND $BLEND"
echo "REVIEW PENDING Organic hair / organic sleeves / soft child face / guofeng silhouette"
echo "NEXT P28-02 human visual review"
