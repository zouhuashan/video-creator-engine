#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$ROOT/support/blender/child-lookdev-v6.py"
OUT="$ROOT/renders/lookdev/child-lookdev-v6.png"
BLEND="$ROOT/renders/lookdev/child-lookdev-v6.blend"
LOG="$ROOT/logs/child-lookdev-v6.log"
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

echo "RUN  P28-02 Child LookDev v6 (MPFB native child)"
: >"$LOG"
rm -f "$STATUS"

if ! VIDEO_CREATOR_MPFB_STATUS="$STATUS" /usr/bin/arch -arm64 "$blender"   --background   --python-exit-code 1   --python "$ROOT/support/blender/check-mpfb.py" >>"$LOG" 2>&1; then
  echo "FAIL MPFB unavailable"
  echo "NEXT ./install-mpfb.command"
  tail -n 140 "$LOG" 2>/dev/null || true
  exit 1
fi

if [ ! -s "$STATUS" ]; then
  echo "FAIL MPFB status file missing"
  tail -n 140 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! /usr/bin/arch -arm64 "$blender"   --background   --python-exit-code 1   --python "$SCRIPT" --   --output "$OUT"   --blend-output "$BLEND" >>"$LOG" 2>&1; then
  echo "FAIL P28-02 Child LookDev v6"
  tail -n 200 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -q "VIDEO_CREATOR_MPFB_NATIVE_CHILD_PASS" "$LOG"; then
  echo "FAIL P28-02 v6 native child phenotype gate"
  tail -n 200 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -q "VIDEO_CREATOR_CHILD_LOOKDEV_V6_FRAMING_PASS" "$LOG"; then
  echo "FAIL P28-02 v6 framing gate"
  tail -n 200 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -q "VIDEO_CREATOR_CHILD_LOOKDEV_V6_PASS" "$LOG" || [ ! -s "$OUT" ] || [ ! -s "$BLEND" ]; then
  echo "FAIL P28-02 v6 output validation"
  tail -n 200 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "PASS P28-02 v6 technical render"
echo "PNG  $OUT"
echo "BLEND $BLEND"
echo "REVIEW PENDING Native child anatomy / juvenile silhouette / reference direction"
echo "NEXT P28-02 human visual review"
