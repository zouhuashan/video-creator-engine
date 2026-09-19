#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG="$ROOT/logs/mpfb-install.log"
mkdir -p "$ROOT/logs"

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

echo "RUN  Install/enable MPFB"
: >"$LOG"

# Blender's official extension CLI resolves package id 'mpfb' from enabled repositories.
if ! /usr/bin/arch -arm64 "$blender" --command extension install -s -e mpfb >>"$LOG" 2>&1; then
  # If already installed, installation can report a non-zero status on some builds.
  # Validate the operator before treating this as fatal.
  if ! /usr/bin/arch -arm64 "$blender" --background --python-exit-code 1 --python "$ROOT/support/blender/check-mpfb.py" >>"$LOG" 2>&1; then
    echo "FAIL MPFB install/enable"
    tail -n 140 "$LOG" 2>/dev/null || true
    exit 1
  fi
fi

if ! /usr/bin/arch -arm64 "$blender" --background --python-exit-code 1 --python "$ROOT/support/blender/check-mpfb.py" >>"$LOG" 2>&1; then
  echo "FAIL MPFB validation"
  tail -n 140 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -q "VIDEO_CREATOR_MPFB_PASS" "$LOG"; then
  echo "FAIL MPFB validation marker missing"
  tail -n 140 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "PASS MPFB ready"
echo "NEXT ./render-child-lookdev-v5.command"
