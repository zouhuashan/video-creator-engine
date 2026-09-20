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
CERT_DIR = DEPENDENCIES / "certs"
MACOS_CA_BUNDLE = CERT_DIR / "macos-trust.pem"
PYPI_PROBE_URL = "https://pypi.org/simple/pip/"


class ComfyUIInstallError(RuntimeError):
    pass


class ComfyUITorchUnavailable(ComfyUIInstallError):
    pass


class ComfyUIRequirementsUnavailable(ComfyUIInstallError):
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


def _apple_silicon_host() -> bool:
    if platform.system() != "Darwin":
        return False
    if platform.machine().lower() in {"arm64", "aarch64"}:
        return True
    if shutil.which("sysctl"):
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.optional.arm64"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            return result.returncode == 0 and result.stdout.strip() == "1"
        except (OSError, subprocess.SubprocessError):
            pass
    return False


def _python_machine(executable: str) -> str:
    try:
        result = subprocess.run(
            [executable, "-c", "import platform;print(platform.machine())"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip().lower() if result.returncode == 0 else ""


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


def _python_candidates() -> list[str]:
    candidates: list[str] = []
    for name in ("python3.13", "python3.12", "python3.14", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    candidates.append(sys.executable)
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = str(Path(candidate).resolve())
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        version = _python_version(resolved)
        if not (version and (3, 10) <= version <= (3, 14)):
            continue
        if _apple_silicon_host():
            machine = _python_machine(resolved)
            if machine not in {"arm64", "aarch64"}:
                continue
        unique.append(resolved)
    return unique


def _export_macos_trust_bundle() -> Path | None:
    if platform.system() != "Darwin" or shutil.which("security") is None:
        return None
    keychains = [
        Path("/System/Library/Keychains/SystemRootCertificates.keychain"),
        Path("/Library/Keychains/System.keychain"),
        Path.home() / "Library" / "Keychains" / "login.keychain-db",
    ]
    chunks: list[bytes] = []
    for keychain in keychains:
        if not keychain.is_file():
            continue
        try:
            result = subprocess.run(
                ["security", "find-certificate", "-a", "-p", str(keychain)],
                capture_output=True,
                check=False,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0 and b"BEGIN CERTIFICATE" in result.stdout:
            chunks.append(result.stdout)
    if not chunks:
        return None
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = MACOS_CA_BUNDLE.with_suffix(".tmp")
    temporary.write_bytes(b"\n".join(chunks))
    temporary.replace(MACOS_CA_BUNDLE)
    return MACOS_CA_BUNDLE


def _candidate_ca_bundles() -> list[Path]:
    values = [
        os.environ.get("SSL_CERT_FILE"),
        os.environ.get("PIP_CERT"),
        os.environ.get("REQUESTS_CA_BUNDLE"),
        str(MACOS_CA_BUNDLE) if MACOS_CA_BUNDLE.is_file() else None,
        "/etc/ssl/cert.pem",
        "/opt/local/share/curl/curl-ca-bundle.crt",
        "/opt/local/etc/openssl/cert.pem",
        "/opt/local/etc/openssl3/cert.pem",
        "/opt/homebrew/etc/ca-certificates/cert.pem",
        "/usr/local/etc/ca-certificates/cert.pem",
    ]
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        path = Path(value).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen or not resolved.is_file():
            continue
        seen.add(key)
        result.append(resolved)
    return result


def _network_env(ca_bundle: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    if ca_bundle is not None:
        value = str(ca_bundle)
        env["SSL_CERT_FILE"] = value
        env["PIP_CERT"] = value
        env["REQUESTS_CA_BUNDLE"] = value
    return env


def _default_ca_bundle(executable: str) -> Path | None:
    script = "import ssl; p=ssl.get_default_verify_paths(); print(p.cafile or '')"
    try:
        result = subprocess.run(
            [executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if not value:
        return None
    try:
        path = Path(value).expanduser().resolve()
    except OSError:
        return None
    return path if path.is_file() else None


def _https_probe(executable: str, env: dict[str, str]) -> tuple[bool, str]:
    script = (
        "import urllib.request;"
        "r=urllib.request.urlopen('" + PYPI_PROBE_URL + "',timeout=8);"
        "print(getattr(r,'status',200));r.close()"
    )
    try:
        result = subprocess.run(
            [executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    if result.returncode == 0:
        return True, ""
    detail = (result.stderr or result.stdout or "HTTPS probe failed").strip()
    return False, detail[-1200:]


def choose_bootstrap_runtime(exclude: set[str] | None = None) -> tuple[str, dict[str, str], str]:
    excluded = exclude or set()
    candidates = [item for item in _python_candidates() if item not in excluded]
    if not candidates:
        raise ComfyUIInstallError("未找到 Python 3.10–3.14；建议安装 Homebrew python@3.13 或 python@3.12")

    failures: list[str] = []
    exported: Path | None = None
    cached_bundles: list[Path] | None = None

    # Preserve Python preference order. ComfyUI currently recommends 3.13,
    # with 3.12 as a fallback; 3.14 works but may have custom-node issues.
    # Therefore repair TLS for each preferred interpreter before considering
    # the next interpreter.
    for executable in candidates:
        env = _network_env()
        ok, detail = _https_probe(executable, env)
        if ok:
            default_bundle = _default_ca_bundle(executable)
            if default_bundle is not None:
                return executable, _network_env(default_bundle), str(default_bundle)
            return executable, env, "python-default"
        failures.append(f"{executable}: {detail.splitlines()[-1] if detail else 'TLS failed'}")

        if cached_bundles is None:
            exported = _export_macos_trust_bundle()
            cached_bundles = _candidate_ca_bundles()
            if exported is not None and exported not in cached_bundles:
                cached_bundles.insert(0, exported)

        for bundle in cached_bundles:
            repaired_env = _network_env(bundle)
            repaired, repaired_detail = _https_probe(executable, repaired_env)
            if repaired:
                return executable, repaired_env, str(bundle)
            failures.append(
                f"{executable} + {bundle}: "
                f"{repaired_detail.splitlines()[-1] if repaired_detail else 'TLS failed'}"
            )

    summary = " | ".join(failures[-8:])
    raise ComfyUIInstallError(
        "所有可用 Python 都无法通过 PyPI HTTPS 证书校验。"
        "已尝试 macOS Keychain 与常见 CA bundle；不会使用 --trusted-host 或关闭 SSL。"
        + (f" 最近错误: {summary}" if summary else "")
    )


def choose_bootstrap_python() -> str:
    return choose_bootstrap_runtime()[0]


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
        _run(["git", "-C", str(INSTALL_DIR), "pull", "--ff-only"], cwd=None, log=log, label="UPDATE_SOURCE")
        return
    if INSTALL_DIR.exists():
        broken = DEPENDENCIES / f"ComfyUI.broken-{int(time.time())}"
        INSTALL_DIR.rename(broken)
        log.write(f"moved incomplete install to {broken}\n".encode())
        log.flush()
    _run(["git", "clone", "--depth", "1", SOURCE_URL, str(INSTALL_DIR)], cwd=DEPENDENCIES, log=log, label="CLONE")


def _venv_python() -> Path:
    return INSTALL_DIR / ".venv" / "bin" / "python"


def _python_identity(executable: str) -> tuple[int, int, str] | None:
    try:
        result = subprocess.run(
            [executable, "-c", "import json,sys;print(json.dumps({'major':sys.version_info.major,'minor':sys.version_info.minor,'base':sys.base_prefix}))"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        payload = json.loads(result.stdout.strip())
        return int(payload["major"]), int(payload["minor"]), str(Path(payload["base"]).resolve())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError):
        return None


def _venv_matches_bootstrap(venv_python: Path, bootstrap_python: str, env: dict[str, str]) -> tuple[bool, str]:
    if not venv_python.is_file():
        return False, "venv python missing"
    bootstrap = _python_identity(bootstrap_python)
    existing = _python_identity(str(venv_python))
    if bootstrap is None or existing is None:
        return False, "cannot identify Python runtime"
    if bootstrap[:2] != existing[:2]:
        return False, f"Python version changed: venv={existing[0]}.{existing[1]} bootstrap={bootstrap[0]}.{bootstrap[1]}"
    if bootstrap[2] != existing[2]:
        return False, f"Python runtime changed: venv_base={existing[2]} bootstrap_base={bootstrap[2]}"
    ok, detail = _https_probe(str(venv_python), env)
    if not ok:
        return False, f"existing venv TLS probe failed: {detail.splitlines()[-1] if detail else 'unknown TLS failure'}"
    return True, ""


def _rebuild_venv(log, reason: str) -> None:
    venv_dir = INSTALL_DIR / ".venv"
    if not venv_dir.exists():
        return
    log.write(f"rebuilding venv: {reason}\n".encode("utf-8", errors="replace"))
    log.write(b"removing disposable stale venv\n")
    log.flush()
    try:
        shutil.rmtree(venv_dir)
    except OSError as error:
        raise ComfyUIInstallError(f"无法重建旧虚拟环境: {error}") from error


def _ensure_venv(bootstrap_python: str, log, env: dict[str, str]) -> Path:
    python = _venv_python()
    if python.is_file():
        matches, reason = _venv_matches_bootstrap(python, bootstrap_python, env)
        if not matches:
            _rebuild_venv(log, reason)
            python = _venv_python()

    if not python.is_file():
        _run([bootstrap_python, "-m", "venv", str(INSTALL_DIR / ".venv")], cwd=INSTALL_DIR, log=log, label="CREATE_VENV", env=env)

    if not python.is_file():
        raise ComfyUIInstallError("虚拟环境创建失败")

    ok, detail = _https_probe(str(python), env)
    if not ok:
        raise ComfyUIInstallError(
            "新虚拟环境仍无法通过 PyPI HTTPS 校验"
            + (f": {detail.splitlines()[-1]}" if detail else "")
        )

    _run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=INSTALL_DIR, log=log, label="UPGRADE_PIP", env=env)
    return python


def _python_platform_signature(python: Path) -> str:
    script = (
        "import json,platform,sys,sysconfig;"
        "print(json.dumps({'python':platform.python_version(),"
        "'machine':platform.machine(),'platform':sysconfig.get_platform(),"
        "'soabi':sysconfig.get_config_var('SOABI'),'abiflags':getattr(sys,'abiflags','')}))"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", script],
            capture_output=True,
            text=True,
            cwd=INSTALL_DIR,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _pip_dry_run(command: list[str], *, log, env: dict[str, str], label: str) -> tuple[bool, str]:
    probe = [*command, "--dry-run"]
    log.write(("$ " + " ".join(probe) + "\n").encode("utf-8", errors="replace"))
    log.flush()
    try:
        result = subprocess.run(
            probe,
            cwd=INSTALL_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    output = result.stdout or ""
    log.write(output.encode("utf-8", errors="replace"))
    log.flush()
    if result.returncode == 0:
        return True, output
    detail = "\n".join(output.splitlines()[-20:])
    return False, detail


def _install_torch(python: Path, log, env: dict[str, str]) -> str:
    is_apple = platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}
    if not is_apple:
        return "system"

    nightly = [
        str(python), "-m", "pip", "install", "--pre", "--only-binary=:all:",
        "torch", "torchvision", "torchaudio",
        "--extra-index-url", "https://download.pytorch.org/whl/nightly/cpu",
    ]
    stable = [
        str(python), "-m", "pip", "install", "--only-binary=:all:",
        "torch", "torchvision", "torchaudio",
    ]

    log.write(f"python_platform={_python_platform_signature(python)}\n".encode("utf-8", errors="replace"))
    log.flush()

    nightly_ok, nightly_detail = _pip_dry_run(nightly, log=log, env=env, label="PROBE_TORCH_NIGHTLY")
    if nightly_ok:
        _run(nightly, cwd=INSTALL_DIR, log=log, label="INSTALL_TORCH_NIGHTLY", env=env)
        return "nightly"

    log.write(b"nightly torch has no compatible wheel for this Python runtime; probing stable PyPI\n")
    log.flush()
    stable_ok, stable_detail = _pip_dry_run(stable, log=log, env=env, label="PROBE_TORCH_STABLE")
    if stable_ok:
        _run(stable, cwd=INSTALL_DIR, log=log, label="INSTALL_TORCH_STABLE", env=env)
        return "stable"

    combined = (stable_detail or nightly_detail or "no compatible torch wheel").strip()
    raise ComfyUITorchUnavailable(
        "当前 Python runtime 没有可安装的 PyTorch wheel"
        + (f": {combined.splitlines()[-1]}" if combined else "")
    )


def _probe_requirements(python: Path, log, env: dict[str, str]) -> None:
    requirements = INSTALL_DIR / "requirements.txt"
    if not requirements.is_file():
        raise ComfyUIInstallError("ComfyUI requirements.txt 不存在")
    command = [str(python), "-m", "pip", "install", "-r", str(requirements)]
    ok, detail = _pip_dry_run(command, log=log, env=env, label="PROBE_REQUIREMENTS")
    if ok:
        return
    raise ComfyUIRequirementsUnavailable(
        "当前 Python runtime 无法满足 ComfyUI requirements"
        + (f": {detail.splitlines()[-1]}" if detail else "")
    )


def _install_requirements(python: Path, log, env: dict[str, str]) -> None:
    requirements = INSTALL_DIR / "requirements.txt"
    if not requirements.is_file():
        raise ComfyUIInstallError("ComfyUI requirements.txt 不存在")
    _run([str(python), "-m", "pip", "install", "-r", str(requirements)], cwd=INSTALL_DIR, log=log, label="INSTALL_REQUIREMENTS", env=env)


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

    with LOG_PATH.open("ab") as log:
        log.write(f"\n=== ComfyUI install {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode())
        log.flush()
        try:
            _write_state("RUNNING", "CHECK_PREREQS", "准备安装", pid=os.getpid(), install_dir=str(INSTALL_DIR))
            _clone_or_repair(log)

            excluded: set[str] = set()
            torch_failures: list[str] = []
            while True:
                try:
                    bootstrap_python, install_env, ca_source = choose_bootstrap_runtime(excluded)
                except ComfyUIInstallError as error:
                    if torch_failures:
                        raise ComfyUIInstallError(
                            "所有可用 Python runtime 都无法满足 ComfyUI/PyTorch 平台依赖："
                            + " | ".join(torch_failures[-4:])
                        ) from error
                    raise

                log.write(f"bootstrap_python={bootstrap_python}\n".encode())
                log.write(f"ca_source={ca_source}\n".encode())
                log.flush()

                python = _ensure_venv(bootstrap_python, log, install_env)
                try:
                    _probe_requirements(python, log, install_env)
                except ComfyUIRequirementsUnavailable as error:
                    torch_failures.append(f"{bootstrap_python}: {error}")
                    excluded.add(bootstrap_python)
                    log.write(
                        f"requirements incompatible for {bootstrap_python}; trying next Python runtime\n".encode(
                            "utf-8", errors="replace"
                        )
                    )
                    log.flush()
                    continue

                try:
                    torch_channel = _install_torch(python, log, install_env)
                except ComfyUITorchUnavailable as error:
                    torch_failures.append(f"{bootstrap_python}: {error}")
                    excluded.add(bootstrap_python)
                    log.write(
                        f"torch wheel unavailable for {bootstrap_python}; trying next Python runtime\n".encode(
                            "utf-8", errors="replace"
                        )
                    )
                    log.flush()
                    continue
                break

            _install_requirements(python, log, install_env)
            info = _verify(python, log)
            return _write_state(
                "PASS",
                "COMPLETE",
                "ComfyUI 核心安装完成；尚未下载 checkpoint 模型",
                pid=None,
                install_dir=str(INSTALL_DIR),
                python=str(python),
                ca_source=ca_source,
                torch_channel=torch_channel,
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
