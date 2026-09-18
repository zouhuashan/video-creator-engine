#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG="$ROOT/logs/godot-install.log"
MIN_VERSION="4.7.2"
SMOKE_DIR="$ROOT/support/godot/smoke"
IK_SMOKE_DIR="$ROOT/support/godot/ik-smoke"
mkdir -p "$ROOT/logs"

version_ge() {
  local a="$1" b="$2"
  local a1 a2 a3 b1 b2 b3
  IFS=. read -r a1 a2 a3 <<<"$a"
  IFS=. read -r b1 b2 b3 <<<"$b"
  a1="${a1:-0}"; a2="${a2:-0}"; a3="${a3:-0}"
  b1="${b1:-0}"; b2="${b2:-0}"; b3="${b3:-0}"
  (( a1 > b1 )) && return 0
  (( a1 < b1 )) && return 1
  (( a2 > b2 )) && return 0
  (( a2 < b2 )) && return 1
  (( a3 >= b3 ))
}

find_godot() {
  local candidate
  for candidate in     "/opt/homebrew/bin/godot"     "/Applications/Godot.app/Contents/MacOS/Godot"     "$(command -v godot 2>/dev/null || true)"
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
  echo "RUN  Install stable Godot (arm64 cask)"
  if ! HOMEBREW_NO_ENV_HINTS=1 /usr/bin/arch -arm64 "$brew_bin" install --cask godot >>"$LOG" 2>&1; then
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

raw_version="$(/usr/bin/arch -arm64 "$godot" --version 2>&1 | head -n1)"
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
output="$(/usr/bin/arch -arm64 "$godot" --headless --path "$SMOKE_DIR" --scene res://main.tscn --quit-after 10 2>&1 || true)"
printf '%s\n' "$output" >>"$LOG"
if ! printf '%s' "$output" | grep -q "VIDEO_CREATOR_GODOT_SMOKE_PASS"; then
  echo "FAIL Godot smoke test"
  tail -n 60 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "RUN  Godot TwoBoneIK smoke"
ik_output="$(/usr/bin/arch -arm64 "$godot" --headless --path "$IK_SMOKE_DIR" --scene res://main.tscn --quit-after 10 2>&1 || true)"
printf '%s\\n' "$ik_output" >>"$LOG"

if ! printf '%s' "$ik_output" | grep -q "VIDEO_CREATOR_GODOT_IK_PASS"; then
  echo "FAIL Godot TwoBoneIK smoke"
  printf '%s\n' "$ik_output" | tail -n 60
  exit 1
fi

echo "PASS Godot ready"
echo "BIN  $godot"
echo "VER  $raw_version"
echo "NEXT python3 scripts/godot_rig_readiness.py projects/jinghua-yuan-series"
