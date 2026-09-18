#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
WEB_HOST="${VIDEO_CREATOR_WEB_HOST:-127.0.0.1}"
WEB_PORT="${VIDEO_CREATOR_WEB_PORT:-18765}"
WEB_SCRIPT="$ROOT/scripts/web_server.py"
PID_FILE="$ROOT/cache/web-server.pid"
LOG_FILE="$ROOT/logs/web-server.log"
ENV_LOG="$ROOT/logs/web-env.log"
WEB_PYTHON_DIR="$ROOT/.web-python"
LEGACY_VENV_DIR="$ROOT/.venv-web"
REQUIREMENTS="$ROOT/requirements-web.txt"
REQ_MARKER="$WEB_PYTHON_DIR/.requirements.sha256"
WEB_PYTHON_BIN=""

mkdir -p "$ROOT/cache" "$ROOT/logs"

health_host="$WEB_HOST"
if [ "$health_host" = "0.0.0.0" ] || [ "$health_host" = "::" ]; then
  health_host="127.0.0.1"
fi
WEB_URL="http://$health_host:$WEB_PORT"

python_path() {
  local candidate="$1"
  if [[ "$candidate" == */* ]]; then
    [ -x "$candidate" ] && printf '%s' "$candidate"
  else
    command -v "$candidate" 2>/dev/null || true
  fi
}

python_arch() {
  local python="$1"
  "$python" -c 'import platform; print(platform.machine())' 2>/dev/null || true
}

is_apple_silicon() {
  [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" = "1" ]
}

find_native_python() {
  local candidate resolved arch
  local candidates=(
    /opt/homebrew/bin/python3
    /opt/homebrew/opt/python/bin/python3
    /opt/homebrew/opt/python@3.14/bin/python3.14
    /opt/homebrew/opt/python@3.13/bin/python3.13
    /opt/homebrew/opt/python@3.12/bin/python3.12
    python3
    /usr/bin/python3
  )

  for candidate in "${candidates[@]}"; do
    resolved="$(python_path "$candidate")"
    [ -n "$resolved" ] || continue
    arch="$(python_arch "$resolved")"
    if is_apple_silicon && [ "$arch" != "arm64" ]; then
      continue
    fi
    printf '%s' "$resolved"
    return 0
  done
  return 1
}

bootstrap_arm64_python() {
  local brew_bin="/opt/homebrew/bin/brew"
  local python

  [ "${VIDEO_CREATOR_AUTO_INSTALL_PYTHON:-1}" = "1" ] || return 1

  if [ ! -x "$brew_bin" ]; then
    echo "INFO Native Homebrew was not found at $brew_bin" >&2
    return 1
  fi

  echo "RUN  Install native arm64 Python with Homebrew" >&2
  if ! HOMEBREW_NO_ENV_HINTS=1 arch -arm64 "$brew_bin" install python >>"$ENV_LOG" 2>&1; then
    echo "FAIL Homebrew Python installation failed" >&2
    tail -n 60 "$ENV_LOG" 2>/dev/null >&2 || true
    return 1
  fi

  python="$(find_native_python || true)"
  if [ -z "$python" ]; then
    echo "FAIL Homebrew completed but no arm64 Python was found" >&2
    return 1
  fi

  printf '%s' "$python"
}

select_base_python() {
  local configured="${VIDEO_CREATOR_PYTHON:-}"
  local resolved arch

  if [ -n "$configured" ]; then
    resolved="$(python_path "$configured")"
    if [ -z "$resolved" ]; then
      echo "FAIL Configured Python not found: $configured" >&2
      return 1
    fi
    if is_apple_silicon; then
      arch="$(python_arch "$resolved")"
      if [ "$arch" != "arm64" ]; then
        echo "FAIL VIDEO_CREATOR_PYTHON is $arch, but this Apple Silicon Mac requires arm64." >&2
        return 1
      fi
    fi
    printf '%s' "$resolved"
    return 0
  fi

  resolved="$(find_native_python || true)"
  if [ -n "$resolved" ]; then
    printf '%s' "$resolved"
    return 0
  fi

  if is_apple_silicon; then
    resolved="$(bootstrap_arm64_python || true)"
    if [ -n "$resolved" ]; then
      printf '%s' "$resolved"
      return 0
    fi
    echo "FAIL No native arm64 Python is available." >&2
    echo "NEXT Install native Homebrew at /opt/homebrew, or set VIDEO_CREATOR_PYTHON to an arm64 Python." >&2
  else
    echo "FAIL Python 3 not found." >&2
  fi
  return 1
}

ensure_web_env() {
  local base_python req_hash installed_hash
  base_python="$(select_base_python)" || return 1
  WEB_PYTHON_BIN="$base_python"

  if is_apple_silicon && [ "$(python_arch "$base_python")" != "arm64" ]; then
    echo "FAIL Selected Web Python is not arm64: $(python_arch "$base_python")"
    return 1
  fi

  if [ -d "$LEGACY_VENV_DIR" ]; then
    echo "RUN  Remove legacy Web venv"
    rm -rf "$LEGACY_VENV_DIR"
  fi

  if [ ! -f "$REQUIREMENTS" ]; then
    echo "FAIL Missing Web requirements: $REQUIREMENTS"
    return 1
  fi

  req_hash="$(shasum -a 256 "$REQUIREMENTS" | awk '{print $1}')"
  installed_hash="$(cat "$REQ_MARKER" 2>/dev/null || true)"

  if [ "$req_hash" != "$installed_hash" ]; then
    echo "RUN  Install Web Python dependencies"
    rm -rf "$WEB_PYTHON_DIR"
    mkdir -p "$WEB_PYTHON_DIR"

    if ! PYTHONNOUSERSITE=1 "$base_python" -m pip --version >>"$ENV_LOG" 2>&1; then
      echo "FAIL pip is unavailable in $base_python"
      tail -n 40 "$ENV_LOG" 2>/dev/null || true
      return 1
    fi

    if ! PYTHONNOUSERSITE=1 "$base_python" -m pip install       --disable-pip-version-check       --upgrade       --target "$WEB_PYTHON_DIR"       -r "$REQUIREMENTS" >>"$ENV_LOG" 2>&1; then
      echo "FAIL Web dependency installation failed"
      tail -n 60 "$ENV_LOG" 2>/dev/null || true
      return 1
    fi

    printf '%s\n' "$req_hash" > "$REQ_MARKER"
  fi

  if ! PYTHONNOUSERSITE=1 PYTHONPATH="$WEB_PYTHON_DIR" "$base_python" -s -c     'import platform; from PIL import Image; print(platform.machine(), Image.__version__)' >>"$ENV_LOG" 2>&1; then
    echo "FAIL Web Python self-check failed"
    tail -n 60 "$ENV_LOG" 2>/dev/null || true
    return 1
  fi
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

if [ ! -f "$WEB_SCRIPT" ]; then
  echo "FAIL Missing web server: $WEB_SCRIPT"
  exit 1
fi

ensure_web_env

cd "$ROOT"
PYTHONNOUSERSITE=1 PYTHONPATH="$WEB_PYTHON_DIR" nohup "$WEB_PYTHON_BIN" -s -u "$WEB_SCRIPT"   --host "$WEB_HOST" --port "$WEB_PORT" >>"$LOG_FILE" 2>&1 &
web_pid=$!
echo "$web_pid" > "$PID_FILE"

started=0
for _ in $(seq 1 32); do
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
  echo "--- web log tail ---"
  tail -n 40 "$LOG_FILE" 2>/dev/null || true
  echo "--- env log tail ---"
  tail -n 30 "$ENV_LOG" 2>/dev/null || true
  exit 1
fi

echo "PASS Web started"
echo "URL  $WEB_URL"
echo "PID  $web_pid"
echo "PY   $WEB_PYTHON_BIN ($(python_arch "$WEB_PYTHON_BIN"))"
echo "DEPS $WEB_PYTHON_DIR"
echo "LOG  $LOG_FILE"
