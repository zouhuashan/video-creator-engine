#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
WEB_HOST="${VIDEO_CREATOR_WEB_HOST:-127.0.0.1}"
WEB_PORT="${VIDEO_CREATOR_WEB_PORT:-18765}"
WEB_SCRIPT="$ROOT/scripts/web_server.py"
PID_FILE="$ROOT/cache/web-server.pid"
START_SCRIPT="$ROOT/start-web.command"
WEB_PYTHON_DIR="$ROOT/.web-python"
BOOTSTRAP_DIR="$ROOT/support/web-python"

select_preflight_python() {
  local candidate
  for candidate in     "${VIDEO_CREATOR_PYTHON:-}"     "/opt/homebrew/bin/python3"     "$(command -v python3 2>/dev/null || true)"     "/usr/bin/python3"
  do
    [ -n "$candidate" ] && [ -x "$candidate" ] && { printf '%s' "$candidate"; return 0; }
  done
  return 1
}

run_preflight() {
  local python
  python="$(select_preflight_python || true)"
  if [ -z "$python" ]; then
    echo "FAIL Web preflight: Python 3 not found"
    return 1
  fi

  echo "RUN  Web preflight"
  if ! PYTHONNOUSERSITE=1 PYTHONPATH="$BOOTSTRAP_DIR:$WEB_PYTHON_DIR:$ROOT" "$python" -s -m py_compile     "$ROOT/scripts/web_server.py"     "$ROOT/scripts/godot_rig_readiness.py"     "$ROOT/scripts/build_character_rig_v2.py"     "$ROOT/scripts/rig_v2_segment.py"; then
    echo "FAIL Web preflight: Python syntax check failed"
    return 1
  fi

  if ! PYTHONNOUSERSITE=1 PYTHONPATH="$BOOTSTRAP_DIR:$WEB_PYTHON_DIR:$ROOT" "$python" -s -c     'import scripts.web_server; print("WEB_IMPORT_PASS")' >/dev/null; then
    echo "FAIL Web preflight: web_server import failed"
    return 1
  fi

  echo "PASS Web preflight"
}

is_project_web_pid() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null || return 1

  local command cwd
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  if printf '%s' "$command" | grep -F "$WEB_SCRIPT" >/dev/null 2>&1; then
    return 0
  fi

  if command -v lsof >/dev/null 2>&1; then
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)"
    if [ "$cwd" = "$ROOT" ] && printf '%s' "$command" | grep -F "scripts/web_server.py" >/dev/null 2>&1; then
      return 0
    fi
  fi

  return 1
}

find_project_pid() {
  if [ -f "$PID_FILE" ]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$pid" ] && is_project_web_pid "$pid"; then
      printf '%s' "$pid"
      return 0
    fi
    rm -f "$PID_FILE"
  fi

  if command -v lsof >/dev/null 2>&1; then
    local listener
    listener="$(lsof -nP -iTCP:"$WEB_PORT" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)"
    if [ -n "$listener" ] && is_project_web_pid "$listener"; then
      printf '%s' "$listener"
      return 0
    fi
  fi

  return 1
}

run_preflight

if web_pid="$(find_project_pid)"; then
  echo "RUN  Stop Web PID $web_pid"
  kill -TERM "$web_pid" 2>/dev/null || true

  for _ in $(seq 1 20); do
    if ! kill -0 "$web_pid" 2>/dev/null; then
      break
    fi
    sleep 0.25
  done

  if kill -0 "$web_pid" 2>/dev/null; then
    echo "RUN  Force stop Web PID $web_pid"
    kill -KILL "$web_pid" 2>/dev/null || true
  fi

  rm -f "$PID_FILE"
  echo "PASS Web stopped"
else
  echo "INFO Web is not running; start instead."
fi

exec "$START_SCRIPT"
