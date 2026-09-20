#!/usr/bin/env python3
"""Safe local ComfyUI service manager for VideoCreator Engine.

Only manages a ComfyUI process started by this module. It never kills an
unmanaged/external ComfyUI process and never executes user supplied commands.
"""

from __future__ import annotations

import hashlib
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
INSTALL_STATE_PATH = LOG_DIR / "comfyui-install.json"
PROJECT_COMFYUI_HOME = ROOT / ".dependencies" / "ComfyUI"


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
        Path("/Applications/Comfy Desktop.app/Contents/Resources/ComfyUI"),
    ])
    installs_root = home / "ComfyUI-Installs"
    if installs_root.is_dir():
        candidates.extend(sorted(installs_root.glob("*/ComfyUI")))
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


def _desktop_base_path() -> tuple[Path | None, Path | None]:
    support = Path.home() / "Library" / "Application Support"
    for config_path in (
        support / "ComfyUI" / "config.json",
        support / "Comfy Desktop" / "config.json",
    ):
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        raw = str(payload.get("basePath") or payload.get("base_path") or "").strip()
        if not raw:
            continue
        path = Path(raw).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.is_dir():
            return resolved, config_path
    return None, None


def _python_for(home: Path) -> Path | None:
    desktop_base, _ = _desktop_base_path()
    candidates = [
        home / ".venv" / "bin" / "python",
        home / "venv" / "bin" / "python",
    ]
    if desktop_base is not None:
        candidates.insert(0, desktop_base / ".venv" / "bin" / "python")
    candidates.append(Path(sys.executable))
    for candidate in candidates:
        # Critical: never resolve a venv/bin/python symlink to its base
        # interpreter. Python discovers pyvenv.cfg from the invoked venv path;
        # resolving the symlink destroys venv semantics and can hit PEP 668.
        expanded = candidate.expanduser()
        if expanded.is_file() and os.access(expanded, os.X_OK):
            return expanded.absolute()
    return None


def _requirements_fingerprint(home: Path) -> str:
    path = home / "requirements.txt"
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_install_state() -> dict[str, Any]:
    try:
        payload = json.loads(INSTALL_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_install_state(payload: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INSTALL_STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(INSTALL_STATE_PATH)


def _venv_identity(python: Path, home: Path) -> tuple[bool, str]:
    check = (
        "import json,sys;"
        "print(json.dumps({'prefix':sys.prefix,'base_prefix':sys.base_prefix,'executable':sys.executable}))"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", check],
            capture_output=True,
            text=True,
            cwd=home,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "venv identity probe failed").strip()[-2000:]
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return False, "venv identity probe returned invalid JSON"
    prefix = str(payload.get("prefix") or "")
    base_prefix = str(payload.get("base_prefix") or "")
    executable = str(payload.get("executable") or "")
    if not prefix or not base_prefix:
        return False, "Python prefix metadata missing"
    if prefix == base_prefix:
        return False, f"not a virtual environment: executable={executable or python}"
    try:
        expected = (home / ".venv").resolve()
        actual = Path(prefix).resolve()
    except OSError:
        expected = home / ".venv"
        actual = Path(prefix)
    if home.resolve() == PROJECT_COMFYUI_HOME.resolve() and actual != expected:
        return False, f"unexpected venv prefix: {actual} (expected {expected})"
    return True, ""


def _runtime_dependency_smoke(python: Path, home: Path) -> tuple[bool, str]:
    requirements = home / "requirements.txt"
    if not requirements.is_file():
        return False, "requirements.txt missing"
    check = (
        "import json;"
        "from importlib.metadata import version,PackageNotFoundError;"
        "from packaging.requirements import Requirement;"
        "from pathlib import Path;"
        "issues=[];"
        "lines=Path('requirements.txt').read_text(encoding='utf-8').splitlines();"
        "\nfor raw in lines:\n"
        " line=raw.strip()\n"
        " if not line or line.startswith('#') or line.startswith('-'): continue\n"
        " try: req=Requirement(line)\n"
        " except Exception: continue\n"
        " if req.marker is not None and not req.marker.evaluate(): continue\n"
        " try: installed=version(req.name)\n"
        " except PackageNotFoundError: issues.append([req.name,'MISSING','']); continue\n"
        " if req.specifier and installed not in req.specifier: issues.append([req.name,'VERSION',installed+' not in '+str(req.specifier)])\n"
        "mods=['filelock','sqlalchemy','alembic','aiohttp','yaml','PIL','numpy','torch'];"
        "\nfor m in mods:\n"
        " try: __import__(m)\n"
        " except Exception as e: issues.append([m,type(e).__name__,str(e)])\n"
        "print(json.dumps({'issues':issues}))"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", check],
            capture_output=True,
            text=True,
            cwd=home,
            check=False,
            timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "dependency smoke failed").strip()[-3000:]
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return False, "dependency smoke returned invalid JSON"
    issues = payload.get("issues") if isinstance(payload, dict) else None
    if issues:
        return False, "; ".join(f"{item[0]}: {item[1]} {item[2]}" for item in issues[:12])
    return True, ""


def _dependency_env() -> dict[str, str]:
    env = dict(os.environ)
    state = _load_install_state()
    ca_source = str(state.get("ca_source") or "").strip()
    if ca_source:
        path = Path(ca_source)
        if path.is_file():
            env["SSL_CERT_FILE"] = str(path)
            env["PIP_CERT"] = str(path)
            env["REQUESTS_CA_BUNDLE"] = str(path)
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def _sync_project_dependencies(home: Path, python: Path, log) -> dict[str, Any]:
    try:
        managed_home = PROJECT_COMFYUI_HOME.resolve()
        resolved_home = home.resolve()
    except OSError as error:
        raise ComfyUIServiceError(f"无法解析 ComfyUI 安装目录: {error}") from error
    if resolved_home != managed_home:
        return {"repaired": False, "managed": False, "detail": "external ComfyUI dependencies left untouched"}

    requirements = home / "requirements.txt"
    if not requirements.is_file():
        raise ComfyUIServiceError("项目 ComfyUI requirements.txt 不存在")

    venv_ok, venv_detail = _venv_identity(python, home)
    if not venv_ok:
        raise ComfyUIServiceError(
            "拒绝修改非项目虚拟环境 Python；"
            + (venv_detail or "venv identity check failed")
        )

    install_state = _load_install_state()
    current_sha = _requirements_fingerprint(home)
    recorded_sha = str(install_state.get("requirements_sha256") or "")
    healthy, smoke_detail = _runtime_dependency_smoke(python, home)
    if healthy and recorded_sha == current_sha:
        log.write(b"dependency_sync=SKIP already-current\n")
        log.flush()
        return {"repaired": False, "managed": True, "requirements_sha256": current_sha}

    reasons = []
    if recorded_sha != current_sha:
        reasons.append("requirements fingerprint changed")
    if not healthy:
        reasons.append(smoke_detail or "dependency smoke failed")
    log.write(("dependency_sync=RUN reason=" + "; ".join(reasons) + "\n").encode("utf-8", errors="replace"))
    log.flush()

    command = [str(python), "-m", "pip", "install", "-r", str(requirements)]
    result = subprocess.run(
        command,
        cwd=home,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        env=_dependency_env(),
        check=False,
    )
    if result.returncode != 0:
        raise ComfyUIServiceError(f"ComfyUI 官方 requirements 自动同步失败，pip 退出码 {result.returncode}")

    healthy, smoke_detail = _runtime_dependency_smoke(python, home)
    if not healthy:
        raise ComfyUIServiceError(f"ComfyUI requirements 同步后依赖自检仍失败: {smoke_detail}")

    install_state.update({
        "requirements_sha256": current_sha,
        "dependencies_verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    if install_state:
        _write_install_state(install_state)
    log.write(b"dependency_sync=PASS\n")
    log.flush()
    return {"repaired": True, "managed": True, "requirements_sha256": current_sha}


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
        "desktop_base_path": str(_desktop_base_path()[0] or ""),
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
    desktop_base, desktop_config = _desktop_base_path()
    if desktop_base is not None and "Contents/Resources/ComfyUI" in str(home):
        command.extend(["--base-directory", str(desktop_base)])
        if desktop_config is not None:
            extra_models = desktop_config.parent / "extra_models_config.yaml"
            if extra_models.is_file():
                command.extend(["--extra-model-paths-config", str(extra_models)])
    with LOG_PATH.open("ab") as log:
        log.write(f"\n=== VideoCreator ComfyUI start {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode())
        log.write(f"python={python}\n".encode("utf-8", errors="replace"))
        log.write(f"home={home}\n".encode("utf-8", errors="replace"))
        log.flush()
        try:
            dependency_sync = _sync_project_dependencies(home, python, log)
        except ComfyUIServiceError:
            raise
        except Exception as error:
            raise ComfyUIServiceError(f"ComfyUI 启动前依赖自检失败: {error}") from error
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
    result["dependency_sync"] = dependency_sync
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
