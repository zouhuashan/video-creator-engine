#!/usr/bin/env python3
"""Managed ComfyUI core installer for VideoCreator Engine.

Installs only ComfyUI core/runtime dependencies into .dependencies/ComfyUI.
It intentionally does not download image checkpoints/models.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = ROOT / ".dependencies"
INSTALL_DIR = DEPENDENCIES / "ComfyUI"
LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "comfyui-install.log"
STATE_PATH = LOG_DIR / "comfyui-install.json"
SOURCE_URL = "https://github.com/Comfy-Org/ComfyUI.git"
MIN_FREE_BYTES = 6 * 1024 * 1024 * 1024


class ComfyUIInstallError(RuntimeError):
    pass


def _write_state(status: str, step: str, detail: str, **extra: Any) -> dict[str, Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "step": step,
        "detail": detail,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **extra,
    }
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)
    return payload


def _load_state() -> dict[str, Any]:
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _pid_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _tail_log(lines: int = 24) -> str:
    try:
        content = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-max(1, min(lines, 60)):])[-8000:]


def _python_version(executable: str) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            [executable, "-c", "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        major, minor = result.stdout.strip().split(".", 1)
        value = (int(major), int(minor))
        return value if value[0] == 3 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def choose_bootstrap_python() -> str:
    candidates: list[str] = []
    for name in ("python3.13", "python3.12", "python3.14", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    candidates.append(sys.executable)
    seen: set[str] = set()
    for candidate in candidates:
        resolved = str(Path(candidate).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        version = _python_version(resolved)
        if version and (3, 10) <= version <= (3, 14):
            return resolved
    raise ComfyUIInstallError("未找到 Python 3.10–3.14；建议安装 Homebrew python@3.13 或 python@3.12")


def _run(command: list[str], *, cwd: Path | None, log, label: str, env: dict[str, str] | None = None) -> None:
    _write_state("RUNNING", label, "执行中", pid=os.getpid(), install_dir=str(INSTALL_DIR))
    log.write(("$ " + " ".join(command) + "\n").encode("utf-8", errors="replace"))
    log.flush()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            check=False,
        )
    except OSError as error:
        raise ComfyUIInstallError(f"{label} 启动失败: {error}") from error
    if result.returncode != 0:
        raise ComfyUIInstallError(f"{label} 失败，退出码 {result.returncode}")


def _clone_or_repair(log) -> None:
    DEPENDENCIES.mkdir(parents=True, exist_ok=True)
    if (INSTALL_DIR / ".git").is_dir() and (INSTALL_DIR / "main.py").is_file():
        _run(["git", "-C", str(INSTALL_DIR), "fetch", "--depth", "1", "origin", "master"], cwd=None, log=log, label="UPDATE_SOURCE")
        _run(["git", "-C", str(INSTALL_DIR), "reset", "--hard", "FETCH_HEAD"], cwd=None, log=log, label="UPDATE_SOURCE")
        return
    if INSTALL_DIR.exists():
        broken = DEPENDENCIES / f"ComfyUI.broken-{int(time.time())}"
        INSTALL_DIR.rename(broken)
        log.write(f"moved incomplete install to {broken}\n".encode())
        log.flush()
    _run(["git", "clone", "--depth", "1", SOURCE_URL, str(INSTALL_DIR)], cwd=DEPENDENCIES, log=log, label="CLONE")


def _venv_python() -> Path:
    return INSTALL_DIR / ".venv" / "bin" / "python"


def _ensure_venv(bootstrap_python: str, log) -> Path:
    python = _venv_python()
    if not python.is_file():
        _run([bootstrap_python, "-m", "venv", str(INSTALL_DIR / ".venv")], cwd=INSTALL_DIR, log=log, label="CREATE_VENV")
    if not python.is_file():
        raise ComfyUIInstallError("虚拟环境创建失败")
    _run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=INSTALL_DIR, log=log, label="UPGRADE_PIP")
    return python


def _install_torch(python: Path, log) -> None:
    is_apple = platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}
    if not is_apple:
        return
    nightly = [str(python), "-m", "pip", "install", "--pre", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/nightly/cpu"]
    try:
        _run(nightly, cwd=INSTALL_DIR, log=log, label="INSTALL_TORCH_NIGHTLY")
    except ComfyUIInstallError:
        log.write(b"nightly torch failed; falling back to stable PyPI torch\n")
        log.flush()
        _run([str(python), "-m", "pip", "install", "torch", "torchvision", "torchaudio"], cwd=INSTALL_DIR, log=log, label="INSTALL_TORCH_STABLE")


def _install_requirements(python: Path, log) -> None:
    requirements = INSTALL_DIR / "requirements.txt"
    if not requirements.is_file():
        raise ComfyUIInstallError("ComfyUI requirements.txt 不存在")
    _run([str(python), "-m", "pip", "install", "-r", str(requirements)], cwd=INSTALL_DIR, log=log, label="INSTALL_REQUIREMENTS")


def _verify(python: Path, log) -> dict[str, Any]:
    check = (
        "import json,torch;"
        "print(json.dumps({'torch':torch.__version__,"
        "'mps_built':bool(getattr(torch.backends,'mps',None) and torch.backends.mps.is_built()),"
        "'mps_available':bool(getattr(torch.backends,'mps',None) and torch.backends.mps.is_available())}))"
    )
    result = subprocess.run([str(python), "-c", check], capture_output=True, text=True, cwd=INSTALL_DIR, check=False, timeout=30)
    log.write((result.stdout + result.stderr).encode("utf-8", errors="replace"))
    log.flush()
    if result.returncode != 0:
        raise ComfyUIInstallError("PyTorch/ComfyUI Python 自检失败")
    try:
        info = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        info = {}
    if not (INSTALL_DIR / "main.py").is_file():
        raise ComfyUIInstallError("ComfyUI main.py 不存在")
    return info if isinstance(info, dict) else {}


def install() -> dict[str, Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not shutil.which("git"):
        raise ComfyUIInstallError("未找到 git")
    try:
        free = shutil.disk_usage(ROOT).free
    except OSError:
        free = MIN_FREE_BYTES
    if free < MIN_FREE_BYTES:
        raise ComfyUIInstallError("可用磁盘空间不足 6 GB；ComfyUI 核心环境安装需要更多空间")

    bootstrap_python = choose_bootstrap_python()
    with LOG_PATH.open("ab") as log:
        log.write(f"\n=== ComfyUI install {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode())
        log.write(f"bootstrap_python={bootstrap_python}\n".encode())
        log.flush()
        try:
            _write_state("RUNNING", "CHECK_PREREQS", "准备安装", pid=os.getpid(), install_dir=str(INSTALL_DIR))
            _clone_or_repair(log)
            python = _ensure_venv(bootstrap_python, log)
            _install_torch(python, log)
            _install_requirements(python, log)
            info = _verify(python, log)
            return _write_state(
                "PASS",
                "COMPLETE",
                "ComfyUI 核心安装完成；尚未下载 checkpoint 模型",
                pid=None,
                install_dir=str(INSTALL_DIR),
                python=str(python),
                torch=str(info.get("torch") or ""),
                mps_built=bool(info.get("mps_built")),
                mps_available=bool(info.get("mps_available")),
                models_installed=False,
            )
        except Exception as error:
            _write_state(
                "FAIL",
                "FAILED",
                str(error),
                pid=None,
                install_dir=str(INSTALL_DIR),
                log_tail=_tail_log(),
            )
            if isinstance(error, ComfyUIInstallError):
                raise
            raise ComfyUIInstallError(str(error)) from error


def status() -> dict[str, Any]:
    state = _load_state()
    try:
        pid = int(state.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if state.get("status") == "RUNNING" and pid and not _pid_alive(pid):
        state = _write_state("FAIL", "INTERRUPTED", "安装进程已退出；可点击重新安装/修复", pid=None, install_dir=str(INSTALL_DIR), log_tail=_tail_log())
    installed = (INSTALL_DIR / "main.py").is_file() and _venv_python().is_file()
    return {
        **state,
        "installed": installed,
        "install_dir": str(INSTALL_DIR),
        "log_path": str(LOG_PATH.relative_to(ROOT)),
        "log_tail": _tail_log(16) if state.get("status") in {"RUNNING", "FAIL"} else "",
        "model_checkpoint_present": any((INSTALL_DIR / "models" / "checkpoints").glob("*")) if (INSTALL_DIR / "models" / "checkpoints").is_dir() else False,
    }


def start_background_install() -> dict[str, Any]:
    current = status()
    if current.get("status") == "RUNNING":
        return {**current, "action": "ALREADY_RUNNING"}
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("ab") as log:
        try:
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--install"],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as error:
            raise ComfyUIInstallError(f"无法启动 ComfyUI 安装进程: {error}") from error
    state = _write_state("RUNNING", "STARTING", "安装器已启动", pid=process.pid, install_dir=str(INSTALL_DIR))
    return {**state, "action": "STARTED", "installed": False, "log_path": str(LOG_PATH.relative_to(ROOT))}


def main() -> int:
    if "--install" not in sys.argv:
        print(json.dumps(status(), ensure_ascii=False))
        return 0
    try:
        print(json.dumps(install(), ensure_ascii=False))
        return 0
    except ComfyUIInstallError as error:
        print(f"comfyui_installer: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
