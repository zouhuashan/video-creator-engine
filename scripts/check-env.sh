#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
failures=0

report_failure() {
  printf 'FAIL: %s\n' "$1"
  failures=$((failures + 1))
}

check_exact() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$actual" == "$expected" ]]; then
    printf 'PASS: %s %s\n' "$label" "$actual"
  else
    report_failure "$label expected $expected, found ${actual:-unavailable}"
  fi
}

if command -v python3 >/dev/null 2>&1; then
  python_actual="$(python3 --version 2>&1 | sed -E 's/^Python //')"
else
  python_actual=""
fi
check_exact "Python" "$(cat "$root_dir/.python-version")" "$python_actual"

if command -v python3 >/dev/null 2>&1; then
  pillow_actual="$(python3 -c 'import PIL; print(PIL.__version__)' 2>/dev/null || true)"
else
  pillow_actual=""
fi
check_exact "Pillow" "$(cat "$root_dir/.pillow-version")" "$pillow_actual"

if command -v node >/dev/null 2>&1; then
  node_actual="$(node --version 2>/dev/null | sed 's/^v//')"
else
  node_actual=""
fi
check_exact "Node.js" "$(cat "$root_dir/.nvmrc")" "$node_actual"

if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg_actual="$(ffmpeg -version 2>&1 | sed -nE '1s/^ffmpeg version ([0-9]+\.[0-9]+).*$/\1/p')"
else
  ffmpeg_actual=""
fi
check_exact "FFmpeg" "$(cat "$root_dir/.ffmpeg-version")" "$ffmpeg_actual"

if command -v codex >/dev/null 2>&1; then
  codex_version="$(codex --version 2>/dev/null || true)"
  if [[ "$codex_version" == codex-cli* ]]; then
    printf 'PASS: Codex CLI %s\n' "${codex_version#codex-cli }"
  else
    report_failure "Codex CLI is installed but could not report its version"
  fi
else
  report_failure "Codex CLI not found on PATH"
fi

if (( failures > 0 )); then
  printf 'FAIL: environment check (%s issue(s))\n' "$failures"
  exit 1
fi

printf 'PASS: environment check\n'
