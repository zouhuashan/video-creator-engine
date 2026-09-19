#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG="$ROOT/logs/mpfb-check.log"

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

: >"$LOG"
echo "RUN  Check MPFB"
if ! /usr/bin/arch -arm64 "$blender" --background --python-exit-code 1 --python "$ROOT/support/blender/check-mpfb.py" >>"$LOG" 2>&1; then
  echo "FAIL MPFB unavailable"
  tail -n 100 "$LOG" 2>/dev/null || true
  exit 1
fi

grep -q "VIDEO_CREATOR_MPFB_PASS" "$LOG" || {
  echo "FAIL MPFB validation marker missing"
  tail -n 120 "$LOG" 2>/dev/null || true
  exit 1
}

echo "PASS MPFB ready"
