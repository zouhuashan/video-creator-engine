#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$ROOT/support/blender/reference-dialogue-blockout.py"
FRAMES="$ROOT/cache/reference-dialogue-blockout-frames"
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

ffmpeg="$(command -v ffmpeg 2>/dev/null || true)"
if [ -z "$ffmpeg" ]; then
  echo "FAIL ffmpeg not found"
  exit 1
fi

rm -rf "$FRAMES"
mkdir -p "$FRAMES"
rm -f "$OUT"

echo "RUN  Reference dialogue blockout frames"
: >"$LOG"
if ! /usr/bin/arch -arm64 "$blender" --background --factory-startup --python "$SCRIPT" --   --frames-dir "$FRAMES"   --blend-output "$BLEND" >>"$LOG" 2>&1; then
  echo "FAIL Reference dialogue blockout render"
  tail -n 100 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -q "VIDEO_CREATOR_REFERENCE_FRAMING_PASS" "$LOG"; then
  echo "FAIL Reference dialogue framing gate"
  tail -n 100 "$LOG" 2>/dev/null || true
  exit 1
fi

if ! grep -q "VIDEO_CREATOR_REFERENCE_BLOCKOUT_FRAMES_PASS" "$LOG"; then
  echo "FAIL Reference blockout frame marker missing"
  tail -n 100 "$LOG" 2>/dev/null || true
  exit 1
fi

frame_count="$(find "$FRAMES" -type f -name 'frame_*.png' | wc -l | tr -d ' ')"
if [ "$frame_count" -ne 144 ]; then
  echo "FAIL Reference blockout expected 144 frames, got $frame_count"
  tail -n 100 "$LOG" 2>/dev/null || true
  exit 1
fi

echo "RUN  Encode reference dialogue MP4"
if ! "$ffmpeg" -y -loglevel error   -framerate 24   -start_number 1   -i "$FRAMES/frame_%04d.png"   -an   -c:v libx264   -pix_fmt yuv420p   -movflags +faststart   "$OUT" >>"$LOG" 2>&1; then
  echo "FAIL Reference dialogue MP4 encode"
  tail -n 100 "$LOG" 2>/dev/null || true
  exit 1
fi

if [ ! -s "$OUT" ]; then
  echo "FAIL Reference blockout MP4 missing"
  exit 1
fi

duration="$("$ffmpeg" -i "$OUT" 2>&1 | sed -nE 's/.*Duration: ([0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+).*/\1/p' | head -n1 || true)"

echo "PASS Reference dialogue blockout"
echo "FRAMES $frame_count"
echo "MP4 $OUT"
echo "BLEND $BLEND"
[ -n "$duration" ] && echo "DUR  $duration"
echo "NEXT Review composition / lighting / proportions only"
