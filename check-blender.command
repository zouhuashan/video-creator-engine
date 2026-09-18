#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG="$ROOT/logs/blender-check.log"
SMOKE_SCRIPT="$ROOT/support/blender/anime-smoke.py"
SMOKE_OUTPUT="$ROOT/cache/blender-anime-smoke.png"
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

raw_version="$(/usr/bin/arch -arm64 "$blender" --version 2>&1 | head -n1)"
version="$(printf '%s' "$raw_version" | sed -nE 's/.*([0-9]+\.[0-9]+\.[0-9]+).*/\1/p')"
major="$(printf '%s' "$version" | cut -d. -f1)"
minor="$(printf '%s' "$version" | cut -d. -f2)"
if [ "$major" != "5" ] || [ "$minor" != "2" ]; then
  echo "FAIL Blender 5.2 LTS required, found: $raw_version"
  exit 1
fi

: >"$LOG"
echo "RUN  Blender Anime smoke"
if ! /usr/bin/arch -arm64 "$blender" --background --factory-startup --python "$SMOKE_SCRIPT" -- --output "$SMOKE_OUTPUT" >>"$LOG" 2>&1; then
  echo "FAIL Blender Anime smoke"
  tail -n 100 "$LOG" 2>/dev/null || true
  exit 1
fi
if ! grep -q "VIDEO_CREATOR_BLENDER_ANIME_SMOKE_PASS" "$LOG"; then
  echo "FAIL Blender smoke marker missing"
  tail -n 100 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "PASS Blender Anime smoke"
echo "BIN  $blender"
echo "VER  $raw_version"
echo "IMG  $SMOKE_OUTPUT"
