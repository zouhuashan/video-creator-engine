#!/usr/bin/env python3
"""Safe local ComfyUI service manager for VideoCreator Engine.

Only manages a ComfyUI process started by this module. It never kills an
unmanaged/external ComfyUI process and never executes user supplied commands.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "comfyui-service.log"
STATE_PATH = LOG_DIR / "comfyui-service.json"


class ComfyUIServiceError(RuntimeError):
    pass


def _loopback_endpoint(base_url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlsplit(str(base_url or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "http" or host not in {"127.0.0.1", "localhost", "::1"}:
        raise ComfyUIServiceError("managed ComfyUI must use a local http://127.0.0.1/localhost address")
    port = int(parsed.port or 8188)
    if not 1 <= port <= 65535:
        raise ComfyUIServiceError("invalid ComfyUI port")
    return host, port


def _candidate_homes() -> list[Path]:
    candidates: list[Path] = []
    configured = str(os.environ.get("COMFYUI_HOME") or "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    home = Path.home()
    candidates.extend([
        ROOT / ".dependencies" / "ComfyUI",
        home / "ComfyUI",
        home / "comfyui",
        home / "Documents" / "ComfyUI",
        home / "Applications" / "ComfyUI",
        Path("/Applications/ComfyUI.app/Contents/Resources/ComfyUI"),
    ])
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key not in seen:
            unique.append(resolved)
            seen.add(key)
    return unique


def discover_comfyui_home() -> Path | None:
    for path in _candidate_homes():
        if path.is_dir() and (path / "main.py").is_file():
            return path
    return None


def _python_for(home: Path) -> Path | None:
    for candidate in (
        home / ".venv" / "bin" / "python",
        home / "venv" / "bin" / "python",
        Path(sys.executable),
    ):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def _load_state() -> dict[str, Any]:
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_state(payload: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def _pid_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _command_for_pid(pid: int) -> str:
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _owned_process(state: dict[str, Any]) -> bool:
    try:
        pid = int(state.get("pid") or 0)
    except (TypeError, ValueError):
        return False
    if not _pid_alive(pid):
        return False
    home = str(state.get("home") or "")
    command = _command_for_pid(pid)
    return bool(command and "main.py" in command and home and home in command)


def _endpoint_connected(base_url: str, timeout: float = 0.35) -> bool:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(f"{base_url.rstrip('/')}/system_stats", method="GET"),
            timeout=timeout,
        ) as response:
            return 200 <= int(response.status) < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return False


def _tail_log(lines: int = 18) -> str:
    try:
        content = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-max(1, min(lines, 50)):])[-6000:]


def service_status(base_url: str, *, connected: bool | None = None) -> dict[str, Any]:
    home = discover_comfyui_home()
    state = _load_state()
    managed = _owned_process(state)
    pid = int(state.get("pid") or 0) if managed else None
    is_connected = _endpoint_connected(base_url) if connected is None else bool(connected)
    installed = home is not None
    if is_connected:
        state_name = "RUNNING"
        detail = "ComfyUI 服务已连接"
    elif managed:
        state_name = "STARTING"
        detail = "ComfyUI 进程已启动，服务尚未就绪"
    elif installed:
        state_name = "STOPPED"
        detail = "已检测到 ComfyUI，但服务未启动"
    else:
        state_name = "NOT_INSTALLED"
        detail = "未检测到 ComfyUI 安装目录；可设置 COMFYUI_HOME 指向包含 main.py 的目录"
    return {
        "state": state_name,
        "installed": installed,
        "managed": managed,
        "pid": pid,
        "home": str(home) if home else "",
        "base_url": base_url,
        "connected": is_connected,
        "detail": detail,
        "log_path": str(LOG_PATH.relative_to(ROOT)),
        "log_tail": _tail_log(12) if state_name in {"STARTING", "STOPPED"} else "",
    }


def start_service(base_url: str) -> dict[str, Any]:
    _, port = _loopback_endpoint(base_url)
    current = service_status(base_url)
    if current["connected"]:
        current["action"] = "ALREADY_RUNNING"
        return current
    if current["managed"]:
        current["action"] = "ALREADY_STARTING"
        return current

    home = discover_comfyui_home()
    if home is None:
        raise ComfyUIServiceError("未检测到 ComfyUI 安装目录；请先安装 ComfyUI，或设置 COMFYUI_HOME")
    python = _python_for(home)
    if python is None:
        raise ComfyUIServiceError("ComfyUI 安装目录存在，但没有可用 Python/.venv")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        str(python),
        str(home / "main.py"),
        "--listen",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    with LOG_PATH.open("ab") as log:
        log.write(f"\n=== VideoCreator ComfyUI start {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode())
        log.flush()
        try:
            process = subprocess.Popen(
                command,
                cwd=home,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as error:
            raise ComfyUIServiceError(f"启动 ComfyUI 失败: {error}") from error

    _write_state({
        "pid": process.pid,
        "home": str(home),
        "python": str(python),
        "base_url": base_url,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "managed_by": "videocreator",
    })
    time.sleep(0.2)
    if process.poll() is not None:
        STATE_PATH.unlink(missing_ok=True)
        detail = _tail_log(18)
        raise ComfyUIServiceError("ComfyUI 启动后立即退出" + (f":\n{detail}" if detail else ""))
    result = service_status(base_url, connected=False)
    result["action"] = "STARTED"
    return result


def stop_service(base_url: str) -> dict[str, Any]:
    state = _load_state()
    if not _owned_process(state):
        STATE_PATH.unlink(missing_ok=True)
        result = service_status(base_url)
        if result["connected"]:
            raise ComfyUIServiceError("检测到外部 ComfyUI 进程；VideoCreator 不会停止非本系统启动的进程")
        result["action"] = "NOT_RUNNING"
        return result

    pid = int(state["pid"])
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError) as error:
        raise ComfyUIServiceError(f"停止 ComfyUI 失败: {error}") from error

    for _ in range(20):
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    if _pid_alive(pid):
        raise ComfyUIServiceError("ComfyUI 未在安全终止时间内退出；未强制 SIGKILL，请检查日志")
    STATE_PATH.unlink(missing_ok=True)
    result = service_status(base_url, connected=False)
    result["action"] = "STOPPED"
    return result


__all__ = [
    "ComfyUIServiceError",
    "discover_comfyui_home",
    "service_status",
    "start_service",
    "stop_service",
]
