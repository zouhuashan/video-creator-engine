#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${VIDEO_CREATOR_PYTHON:-python3}"
WEB_HOST="${VIDEO_CREATOR_WEB_HOST:-127.0.0.1}"
WEB_PORT="${VIDEO_CREATOR_WEB_PORT:-8765}"
WEB_SCRIPT="$ROOT/scripts/web_server.py"
PID_FILE="$ROOT/cache/web-server.pid"
LOG_FILE="$ROOT/logs/web-server.log"

mkdir -p "$ROOT/cache" "$ROOT/logs"

health_host="$WEB_HOST"
if [ "$health_host" = "0.0.0.0" ] || [ "$health_host" = "::" ]; then
  health_host="127.0.0.1"
fi
WEB_URL="http://$health_host:$WEB_PORT"

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

if [ -f "$PID_FILE" ]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$existing_pid" ] && is_project_web_pid "$existing_pid"; then
    echo "PASS Web already running"
    echo "URL  $WEB_URL"
    echo "PID  $existing_pid"
    echo "LOG  $LOG_FILE"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if command -v lsof >/dev/null 2>&1; then
  listener_pid="$(lsof -nP -iTCP:"$WEB_PORT" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)"
  if [ -n "$listener_pid" ]; then
    if is_project_web_pid "$listener_pid"; then
      echo "$listener_pid" > "$PID_FILE"
      echo "PASS Web already running"
      echo "URL  $WEB_URL"
      echo "PID  $listener_pid"
      echo "LOG  $LOG_FILE"
      exit 0
    fi
    echo "FAIL Port $WEB_PORT is already in use by PID $listener_pid"
    echo "NEXT Change VIDEO_CREATOR_WEB_PORT or stop the other service."
    exit 1
  fi
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "FAIL Python not found: $PYTHON_BIN"
  exit 1
fi

if [ ! -f "$WEB_SCRIPT" ]; then
  echo "FAIL Missing web server: $WEB_SCRIPT"
  exit 1
fi

cd "$ROOT"
nohup "$PYTHON_BIN" -u "$WEB_SCRIPT" --host "$WEB_HOST" --port "$WEB_PORT" >>"$LOG_FILE" 2>&1 &
web_pid=$!
echo "$web_pid" > "$PID_FILE"

started=0
for _ in $(seq 1 24); do
  if ! kill -0 "$web_pid" 2>/dev/null; then
    break
  fi
  if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 1 "$WEB_URL/" >/dev/null 2>&1; then
    started=1
    break
  fi
  sleep 0.25
done

if [ "$started" -ne 1 ]; then
  if command -v curl >/dev/null 2>&1; then
    echo "FAIL Web did not become healthy: $WEB_URL"
  elif kill -0 "$web_pid" 2>/dev/null; then
    started=1
  else
    echo "FAIL Web process exited during startup"
  fi
fi

if [ "$started" -ne 1 ]; then
  rm -f "$PID_FILE"
  echo "--- log tail ---"
  tail -n 40 "$LOG_FILE" 2>/dev/null || true
  exit 1
fi

echo "PASS Web started"
echo "URL  $WEB_URL"
echo "PID  $web_pid"
echo "LOG  $LOG_FILE"
