#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG="$ROOT/logs/mpfb-install.log"
LIST_LOG="$ROOT/logs/mpfb-extension-list.log"
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
  echo "NEXT ./install-blender.command"
  exit 1
fi

: >"$LOG"
: >"$LIST_LOG"
rm -f "$STATUS"

echo "RUN  Sync Blender extension repositories"
if ! /usr/bin/arch -arm64 "$blender" --online-mode --command extension sync >>"$LOG" 2>&1; then
  echo "FAIL Blender extension repository sync"
  tail -n 160 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "RUN  Verify MPFB package is published"
if ! /usr/bin/arch -arm64 "$blender" --online-mode --command extension list -s >"$LIST_LOG" 2>>"$LOG"; then
  echo "FAIL Blender extension package list"
  tail -n 160 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -Eiq '(^|[^[:alnum:]_])mpfb([^[:alnum:]_]|$)' "$LIST_LOG"; then
  echo "FAIL MPFB package not found in synced Blender repositories"
  echo "--- extension list tail ---"
  tail -n 120 "$LIST_LOG" 2>/dev/null || true
  echo "--- install log tail ---"
  tail -n 120 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "RUN  Install and enable MPFB"
if ! /usr/bin/arch -arm64 "$blender" --online-mode --command extension install -s -e mpfb >>"$LOG" 2>&1; then
  echo "FAIL MPFB extension install"
  tail -n 180 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "RUN  Validate MPFB real human creation"
if ! VIDEO_CREATOR_MPFB_STATUS="$STATUS" /usr/bin/arch -arm64 "$blender"   --background   --python-exit-code 1   --python "$ROOT/support/blender/check-mpfb.py" >>"$LOG" 2>&1; then
  echo "FAIL MPFB validation after install"
  tail -n 180 "$LOG" 2>/dev/null || true
  exit 1
fi

if [ ! -s "$STATUS" ]; then
  echo "FAIL MPFB status file missing after install"
  tail -n 180 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "PASS MPFB ready"
python3 - "$STATUS" <<'PY'
import json, sys
p=json.load(open(sys.argv[1], encoding="utf-8"))
print("MODULE", p.get("module"))
probe=p.get("probe") or {}
print("VERTS ", probe.get("base_vertices"))
print("MODE  ", p.get("automation_mode"))
PY
echo "NEXT ./render-child-lookdev-v5.command"
