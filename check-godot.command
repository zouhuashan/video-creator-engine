#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SMOKE_DIR="$ROOT/support/godot/smoke"

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
  echo "FAIL Godot not installed"
  echo "NEXT ./install-godot.command"
  exit 1
fi

raw_version="$("$godot" --version 2>&1 | head -n1)"
if printf '%s' "$raw_version" | grep -Eiq '(dev|alpha|beta|rc)'; then
  echo "FAIL Pre-release Godot is not accepted: $raw_version"
  exit 1
fi

output="$("$godot" --headless --path "$SMOKE_DIR" --scene res://main.tscn --quit-after 10 2>&1 || true)"
if ! printf '%s' "$output" | grep -q "VIDEO_CREATOR_GODOT_SMOKE_PASS"; then
  echo "FAIL Godot smoke test"
  printf '%s\n' "$output" | tail -n 40
  exit 1
fi

echo "PASS Godot smoke"
echo "BIN  $godot"
echo "VER  $raw_version"
