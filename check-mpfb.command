#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG="$ROOT/logs/mpfb-check.log"
STATUS="$ROOT/cache/mpfb-check.json"
mkdir -p "$ROOT/logs" "$ROOT/cache"

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
rm -f "$STATUS"
echo "RUN  Check MPFB"
if ! VIDEO_CREATOR_MPFB_STATUS="$STATUS" /usr/bin/arch -arm64 "$blender"   --background   --python-exit-code 1   --python "$ROOT/support/blender/check-mpfb.py" >>"$LOG" 2>&1; then
  echo "FAIL MPFB unavailable"
  tail -n 140 "$LOG" 2>/dev/null || true
  exit 1
fi

if [ ! -s "$STATUS" ]; then
  echo "FAIL MPFB status file missing"
  tail -n 140 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "PASS MPFB ready"
python3 - "$STATUS" <<'PY'
import json, sys
p=json.load(open(sys.argv[1], encoding="utf-8"))
print("ROOT", p.get("root_package"))
print("API ", p.get("service_api"))
PY
