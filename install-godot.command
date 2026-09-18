#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG="$ROOT/logs/godot-install.log"
MIN_VERSION="4.7.2"
SMOKE_DIR="$ROOT/support/godot/smoke"
mkdir -p "$ROOT/logs"

version_ge() {
  local a="$1" b="$2"
  [ "$(printf '%s\n%s\n' "$b" "$a" | sort -V | head -n1)" = "$b" ]
}

find_godot() {
  local candidate
  for candidate in     "$(command -v godot 2>/dev/null || true)"     "/opt/homebrew/bin/godot"     "/Applications/Godot.app/Contents/MacOS/Godot"
  do
    [ -n "$candidate" ] && [ -x "$candidate" ] && { printf '%s' "$candidate"; return 0; }
  done
  return 1
}

godot="$(find_godot || true)"
if [ -z "$godot" ]; then
  brew_bin="$(command -v brew 2>/dev/null || true)"
  [ -x /opt/homebrew/bin/brew ] && brew_bin=/opt/homebrew/bin/brew
  if [ -z "$brew_bin" ]; then
    echo "FAIL Homebrew not found"
    exit 1
  fi
  echo "RUN  Install stable Godot"
  if ! HOMEBREW_NO_ENV_HINTS=1 "$brew_bin" install godot >>"$LOG" 2>&1; then
    echo "FAIL Godot install failed"
    tail -n 60 "$LOG" 2>/dev/null || true
    exit 1
  fi
  godot="$(find_godot || true)"
fi

if [ -z "$godot" ]; then
  echo "FAIL Godot binary not found after installation"
  exit 1
fi

raw_version="$("$godot" --version 2>&1 | head -n1)"
if printf '%s' "$raw_version" | grep -Eiq '(dev|alpha|beta|rc)'; then
  echo "FAIL Pre-release Godot is not allowed for production: $raw_version"
  exit 1
fi
version="$(printf '%s' "$raw_version" | sed -nE 's/.*([0-9]+\.[0-9]+\.[0-9]+).*/\1/p')"
if [ -z "$version" ] || ! version_ge "$version" "$MIN_VERSION"; then
  echo "FAIL Godot >= $MIN_VERSION required, found: $raw_version"
  exit 1
fi

echo "RUN  Godot smoke test"
output="$("$godot" --headless --path "$SMOKE_DIR" --scene res://main.tscn --quit-after 10 2>&1 || true)"
printf '%s\n' "$output" >>"$LOG"
if ! printf '%s' "$output" | grep -q "VIDEO_CREATOR_GODOT_SMOKE_PASS"; then
  echo "FAIL Godot smoke test"
  tail -n 60 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "PASS Godot ready"
echo "BIN  $godot"
echo "VER  $raw_version"
echo "NEXT python3 scripts/godot_rig_readiness.py projects/jinghua-yuan-series"
