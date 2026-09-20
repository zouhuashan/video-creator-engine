#!/usr/bin/env python3
"""Managed ComfyUI checkpoint installer for VideoCreator Engine.

Only fixed, reviewed model entries may be installed. No arbitrary URL input.
Downloads are resumable, checksum-verified, and installed into the managed
ComfyUI checkpoints directory only after verification succeeds.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
COMFYUI_DIR = ROOT / ".dependencies" / "ComfyUI"
CHECKPOINT_DIR = COMFYUI_DIR / "models" / "checkpoints"
LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "comfyui-model-install.log"
STATE_PATH = LOG_DIR / "comfyui-model-install.json"
INSTALL_STATE_PATH = LOG_DIR / "comfyui-install.json"

DEFAULT_MODEL_ID = "animagine-xl-4.0"
MODEL_CATALOG: dict[str, dict[str, Any]] = {
    DEFAULT_MODEL_ID: {
        "id": DEFAULT_MODEL_ID,
        "label": "Animagine XL 4.0",
        "purpose": "动漫基础 checkpoint（国风由系统风格锁 / 可选 LoRA 加强）",
        "filename": "animagine-xl-4.0.safetensors",
        "source": "CagliostroLab / Hugging Face",
        "source_page": "https://huggingface.co/cagliostrolab/animagine-xl-4.0",
        "download_url": "https://huggingface.co/cagliostrolab/animagine-xl-4.0/resolve/main/animagine-xl-4.0.safetensors?download=true",
        "license": "openrail++",
        "expected_bytes": 6938434056,
        "sha256": "1d5b43ff75b6ab598502d4c779d2fbfa3dceca51c60c3b609640a60772333916",
    }
}
MIN_FREE_EXTRA_BYTES = 2 * 1024 * 1024 * 1024


class ComfyUIModelError(RuntimeError):
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


def _sync_core_install_model_state(*, installed: bool, model: dict[str, Any] | None = None) -> None:
    try:
        payload = json.loads(INSTALL_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    payload["models_installed"] = bool(installed)
    payload["model_checkpoint_present"] = bool(installed)
    if installed and model is not None:
        payload["checkpoint_model_id"] = str(model.get("id") or "")
        payload["checkpoint_filename"] = str(model.get("filename") or "")
        payload["checkpoint_sha256"] = str(model.get("sha256") or "")
        payload["checkpoint_verified_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    elif not installed:
        for key in ("checkpoint_model_id", "checkpoint_filename", "checkpoint_sha256", "checkpoint_verified_at"):
            payload.pop(key, None)
    tmp = INSTALL_STATE_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(INSTALL_STATE_PATH)
    except OSError:
        tmp.unlink(missing_ok=True)


def _load_state() -> dict[str, Any]:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _pid_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _model(model_id: str) -> dict[str, Any]:
    try:
        return MODEL_CATALOG[model_id]
    except KeyError as error:
        raise ComfyUIModelError("unsupported checkpoint model") from error


def _target(model: dict[str, Any]) -> Path:
    return CHECKPOINT_DIR / str(model["filename"])


def _partial(model: dict[str, Any]) -> Path:
    return CHECKPOINT_DIR / (str(model["filename"]) + ".part")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _target_size_matches(model: dict[str, Any]) -> bool:
    path = _target(model)
    if not path.is_file():
        return False
    try:
        return path.stat().st_size == int(model["expected_bytes"])
    except OSError:
        return False


def _valid_target(model: dict[str, Any]) -> bool:
    if not _target_size_matches(model):
        return False
    return _sha256(_target(model)) == str(model["sha256"])


def _progress(model: dict[str, Any]) -> dict[str, Any]:
    target = _target(model)
    partial = _partial(model)
    expected = int(model["expected_bytes"])
    downloaded = 0
    if target.is_file():
        try:
            downloaded = target.stat().st_size
        except OSError:
            downloaded = 0
    elif partial.is_file():
        try:
            downloaded = partial.stat().st_size
        except OSError:
            downloaded = 0
    percent = round(min(100.0, downloaded * 100.0 / expected), 2) if expected else 0.0
    return {
        "downloaded_bytes": downloaded,
        "expected_bytes": expected,
        "progress_percent": percent,
    }


def status(model_id: str = DEFAULT_MODEL_ID) -> dict[str, Any]:
    model = _model(model_id)
    state = _load_state()
    try:
        pid = int(state.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0

    if state.get("status") == "RUNNING" and pid and not _pid_alive(pid):
        state = _write_state(
            "FAIL",
            "INTERRUPTED",
            "模型下载进程已退出；可重新点击安装继续断点下载",
            pid=None,
            model_id=model_id,
        )

    installed = bool(
        _target_size_matches(model)
        and state.get("status") == "PASS"
        and state.get("model_id") == model_id
        and state.get("sha256") == model["sha256"]
    )
    if installed:
        _sync_core_install_model_state(installed=True, model=model)

    return {
        **state,
        "model": {
            "id": model["id"],
            "label": model["label"],
            "purpose": model["purpose"],
            "filename": model["filename"],
            "source": model["source"],
            "source_page": model["source_page"],
            "license": model["license"],
            "expected_bytes": model["expected_bytes"],
            "sha256": model["sha256"],
        },
        "installed": installed,
        "checkpoint_path": str(_target(model).relative_to(ROOT)),
        "log_path": str(LOG_PATH.relative_to(ROOT)),
        **_progress(model),
    }


def _normalize_proxy(value: str) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None
    if "://" not in value:
        value = "http://" + value
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https", "socks5", "socks5h"}:
        return None
    if not parsed.hostname or not port:
        return None
    return value


def _macos_system_proxies() -> list[str]:
    if sys.platform != "darwin" or not shutil.which("scutil"):
        return []
    try:
        result = subprocess.run(
            ["scutil", "--proxy"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []

    values: dict[str, str] = {}
    for raw in result.stdout.splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        values[key.strip()] = value.strip()

    proxies: list[str] = []
    for prefix, scheme in (("HTTPS", "http"), ("HTTP", "http"), ("SOCKS", "socks5h")):
        if values.get(prefix + "Enable") != "1":
            continue
        host = values.get(prefix + "Proxy", "").strip()
        port = values.get(prefix + "Port", "").strip()
        if host and port.isdigit():
            proxies.append(f"{scheme}://{host}:{port}")
    return proxies


def _clash_verge_proxies() -> list[str]:
    curl = shutil.which("curl")
    if not curl:
        return []
    sockets: list[Path] = []
    exact = [
        Path("/tmp/verge/verge-mihomo.sock"),
        Path("/tmp/verge/mihomo.sock"),
    ]
    for item in exact:
        if item.exists():
            sockets.append(item)
    verge_dir = Path("/tmp/verge")
    if verge_dir.is_dir():
        for item in verge_dir.glob("*.sock"):
            if item not in sockets:
                sockets.append(item)

    for socket_path in sockets:
        try:
            result = subprocess.run(
                [
                    curl,
                    "--silent",
                    "--show-error",
                    "--fail",
                    "--max-time",
                    "3",
                    "--unix-socket",
                    str(socket_path),
                    "http://localhost/configs",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue

        proxies: list[str] = []
        for key, scheme in (
            ("mixed-port", "http"),
            ("port", "http"),
            ("socks-port", "socks5h"),
        ):
            try:
                port = int(payload.get(key) or 0)
            except (TypeError, ValueError):
                port = 0
            if 1 <= port <= 65535:
                proxies.append(f"{scheme}://127.0.0.1:{port}")
        if proxies:
            return proxies
    return []


def _proxy_candidates() -> list[str]:
    candidates: list[str] = []
    for key in (
        "HTTPS_PROXY", "https_proxy",
        "ALL_PROXY", "all_proxy",
        "HTTP_PROXY", "http_proxy",
    ):
        proxy = _normalize_proxy(os.environ.get(key, ""))
        if proxy:
            candidates.append(proxy)
    candidates.extend(_clash_verge_proxies())
    candidates.extend(_macos_system_proxies())

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_proxy(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _redact_proxy(proxy: str | None) -> str:
    if not proxy:
        return "DIRECT"
    try:
        parsed = urlsplit(proxy)
    except ValueError:
        return "PROXY"
    host = parsed.hostname or "proxy"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}"


def _probe_download_route(curl: str, url: str, proxy: str | None, log) -> bool:
    command = [
        curl,
        "--location",
        "--fail",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "8",
        "--max-time",
        "20",
        "--range",
        "0-0",
        "--output",
        "/dev/null",
    ]
    if proxy:
        command.extend(["--proxy", proxy])
    command.append(url)

    log.write(f"probe_route={_redact_proxy(proxy)}\n".encode("utf-8"))
    log.flush()
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=25,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _select_download_proxy(curl: str, url: str, log) -> str | None:
    proxies = _proxy_candidates()
    # Prefer an explicitly configured/system proxy on machines where direct
    # access to Hugging Face is blocked. Direct is only the final fallback.
    for proxy in proxies:
        if _probe_download_route(curl, url, proxy, log):
            log.write(f"download_route={_redact_proxy(proxy)}\n".encode("utf-8"))
            log.flush()
            return proxy
    if _probe_download_route(curl, url, None, log):
        log.write(b"download_route=DIRECT\n")
        log.flush()
        return None
    detail = ", ".join(_redact_proxy(item) for item in proxies) or "none detected"
    raise ComfyUIModelError(
        "无法连接 Hugging Face；已尝试 macOS/环境代理和直连。"
        f" 检测到的代理: {detail}"
    )


def _download_with_curl(model: dict[str, Any], log) -> None:
    curl = shutil.which("curl")
    if not curl:
        raise ComfyUIModelError("未找到 curl，无法安全下载 checkpoint")

    partial = _partial(model)
    try:
        resume_at = partial.stat().st_size
    except OSError:
        resume_at = 0
    proxy = _select_download_proxy(curl, str(model["download_url"]), log)
    route = _redact_proxy(proxy)
    _write_state(
        "RUNNING",
        "DOWNLOADING",
        f"正在通过 {route} 下载 checkpoint；支持断点续传",
        pid=os.getpid(),
        model_id=str(model["id"]),
        filename=str(model["filename"]),
        network_route=route,
    )
    command = [
        curl,
        "--location",
        "--fail",
        "--silent",
        "--show-error",
        "--retry",
        "8",
        "--retry-delay",
        "3",
        "--connect-timeout",
        "15",
        "--continue-at",
        str(resume_at),
        "--output",
        str(partial),
    ]
    if proxy:
        command.extend(["--proxy", proxy])
    command.append(str(model["download_url"]))
    logged = [item if item != proxy else _redact_proxy(proxy) for item in command[:-1]]
    log.write(("$ " + " ".join(logged) + " <fixed-model-url>\n").encode("utf-8"))
    log.flush()
    result = subprocess.run(
        command,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise ComfyUIModelError(f"checkpoint 下载失败，curl 退出码 {result.returncode}")


def install(model_id: str = DEFAULT_MODEL_ID) -> dict[str, Any]:
    model = _model(model_id)
    if not (COMFYUI_DIR / "main.py").is_file():
        raise ComfyUIModelError("ComfyUI 核心尚未安装")

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if _valid_target(model):
        _sync_core_install_model_state(installed=True, model=model)
        return _write_state(
            "PASS",
            "COMPLETE",
            "checkpoint 已安装并通过 SHA256 校验",
            pid=None,
            model_id=model_id,
            filename=model["filename"],
            sha256=model["sha256"],
        )

    expected = int(model["expected_bytes"])
    partial = _partial(model)
    existing_partial = partial.stat().st_size if partial.is_file() else 0
    required = max(0, expected - existing_partial) + MIN_FREE_EXTRA_BYTES
    try:
        free = shutil.disk_usage(CHECKPOINT_DIR).free
    except OSError:
        free = required
    if free < required:
        raise ComfyUIModelError(
            f"磁盘空间不足：还需要约 {required / (1024 ** 3):.1f} GB 可用空间"
        )

    with LOG_PATH.open("ab") as log:
        log.write(f"\n=== ComfyUI model install {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode())
        log.write(f"model_id={model_id}\nfilename={model['filename']}\n".encode())
        log.flush()
        try:
            _write_state(
                "RUNNING",
                "DOWNLOADING",
                "正在下载 checkpoint；支持断点续传",
                pid=os.getpid(),
                model_id=model_id,
                filename=model["filename"],
            )
            _download_with_curl(model, log)

            try:
                size = partial.stat().st_size
            except OSError as error:
                raise ComfyUIModelError("checkpoint 下载完成后文件不存在") from error
            if size != expected:
                raise ComfyUIModelError(
                    f"checkpoint 文件大小不匹配：expected={expected}, actual={size}"
                )

            _write_state(
                "RUNNING",
                "VERIFYING",
                "正在执行 SHA256 校验",
                pid=os.getpid(),
                model_id=model_id,
                filename=model["filename"],
            )
            actual_sha = _sha256(partial)
            if actual_sha != str(model["sha256"]):
                invalid = partial.with_name(partial.name + f".invalid-{int(time.time())}")
                partial.replace(invalid)
                raise ComfyUIModelError(
                    f"checkpoint SHA256 不匹配；异常文件已隔离为 {invalid.name}"
                )

            target = _target(model)
            partial.replace(target)
            _sync_core_install_model_state(installed=True, model=model)
            return _write_state(
                "PASS",
                "COMPLETE",
                "checkpoint 已安装并通过 SHA256 校验",
                pid=None,
                model_id=model_id,
                filename=model["filename"],
                sha256=actual_sha,
            )
        except Exception as error:
            _write_state(
                "FAIL",
                "FAILED",
                str(error),
                pid=None,
                model_id=model_id,
                filename=model["filename"],
            )
            if isinstance(error, ComfyUIModelError):
                raise
            raise ComfyUIModelError(str(error)) from error


def start_background_install(model_id: str = DEFAULT_MODEL_ID) -> dict[str, Any]:
    _model(model_id)
    current = status(model_id)
    if current.get("installed"):
        return {**current, "action": "ALREADY_INSTALLED"}
    if current.get("status") == "RUNNING":
        return {**current, "action": "ALREADY_RUNNING"}

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("ab") as log:
        try:
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--install", model_id],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as error:
            raise ComfyUIModelError(f"无法启动 checkpoint 下载进程: {error}") from error

    state = _write_state(
        "RUNNING",
        "STARTING",
        "checkpoint 下载器已启动",
        pid=process.pid,
        model_id=model_id,
        filename=_model(model_id)["filename"],
    )
    return {**state, "action": "STARTED", **_progress(_model(model_id))}


def main() -> int:
    if "--install" not in sys.argv:
        print(json.dumps(status(), ensure_ascii=False))
        return 0
    index = sys.argv.index("--install")
    model_id = sys.argv[index + 1] if len(sys.argv) > index + 1 else DEFAULT_MODEL_ID
    try:
        print(json.dumps(install(model_id), ensure_ascii=False))
        return 0
    except ComfyUIModelError as error:
        print(f"comfyui_model_manager: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
