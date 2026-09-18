#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$ROOT/support/blender/reference-dialogue-blockout.py"
OUT="$ROOT/cache/reference-dialogue-blockout.mp4"
BLEND="$ROOT/cache/reference-dialogue-blockout.blend"
LOG="$ROOT/logs/reference-dialogue-blockout.log"
mkdir -p "$ROOT/cache" "$ROOT/logs"

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

echo "RUN  Reference dialogue blockout"
: >"$LOG"
if ! /usr/bin/arch -arm64 "$blender" --background --factory-startup --python "$SCRIPT" --   --output "$OUT"   --blend-output "$BLEND" >>"$LOG" 2>&1; then
  echo "FAIL Reference dialogue blockout"
  tail -n 100 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -q "VIDEO_CREATOR_REFERENCE_BLOCKOUT_PASS" "$LOG" || [ ! -s "$OUT" ]; then
  echo "FAIL Reference blockout output missing"
  tail -n 100 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "PASS Reference dialogue blockout"
echo "MP4 $OUT"
echo "BLEND $BLEND"
echo "NEXT Replace proxy characters with final adult + child lookdev models"
