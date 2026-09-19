#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$ROOT/support/blender/final-child-lookdev-001.py"
OUT="$ROOT/renders/lookdev/final-child-lookdev-001.png"
BLEND="$ROOT/renders/lookdev/final-child-lookdev-001.blend"
LOG="$ROOT/logs/final-child-lookdev-001.log"
STATUS="$ROOT/cache/mpfb-check.json"
mkdir -p "$ROOT/renders/lookdev" "$ROOT/logs" "$ROOT/cache"

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
  exit 1
fi

echo "RUN  FINAL-CHILD-LOOKDEV-001"
: >"$LOG"
rm -f "$STATUS"

if ! VIDEO_CREATOR_MPFB_STATUS="$STATUS" /usr/bin/arch -arm64 "$blender"   --background --python-exit-code 1   --python "$ROOT/support/blender/check-mpfb.py" >>"$LOG" 2>&1; then
  echo "FAIL MPFB unavailable"
  echo "NEXT ./install-mpfb.command"
  tail -n 160 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! /usr/bin/arch -arm64 "$blender"   --background --python-exit-code 1   --python "$SCRIPT" --   --output "$OUT"   --blend-output "$BLEND" >>"$LOG" 2>&1; then
  echo "FAIL FINAL-CHILD-LOOKDEV-001"
  tail -n 220 "$LOG" 2>/dev/null || true
  exit 1
fi

grep -q "VIDEO_CREATOR_FINAL_CHILD_LOOKDEV_FRAMING_PASS" "$LOG" || {
  echo "FAIL final framing gate"
  tail -n 220 "$LOG" 2>/dev/null || true
  exit 1
}

if ! grep -q "VIDEO_CREATOR_FINAL_CHILD_LOOKDEV_PASS" "$LOG" || [ ! -s "$OUT" ] || [ ! -s "$BLEND" ]; then
  echo "FAIL final LookDev output validation"
  tail -n 220 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "PASS FINAL-CHILD-LOOKDEV-001 technical render"
echo "PNG  $OUT"
echo "BLEND $BLEND"
echo "REVIEW PENDING Final guofeng anime child visual gate"
echo "NEXT human visual approval"
