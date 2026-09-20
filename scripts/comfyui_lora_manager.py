#!/usr/bin/env python3
"""Managed ComfyUI LoRA installer for VideoCreator Engine.

Only fixed, reviewed LoRA entries may be installed. Downloads are resumable,
checksum-verified, and written to the managed ComfyUI models/loras directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from scripts.comfyui_model_manager import _redact_proxy, _select_download_proxy

ROOT = Path(__file__).resolve().parents[1]
COMFYUI_DIR = ROOT / ".dependencies" / "ComfyUI"
LORA_DIR = COMFYUI_DIR / "models" / "loras"
LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "comfyui-lora-install.log"
STATE_PATH = LOG_DIR / "comfyui-lora-install.json"

DEFAULT_LORA_ID = "sdxl-chinese-style-illustration"
LORA_CATALOG: dict[str, dict[str, Any]] = {
    DEFAULT_LORA_ID: {
        "id": DEFAULT_LORA_ID,
        "label": "SDXL 中国国风插画 LoRA",
        "purpose": "中国古风 / 仙侠 / 武侠 / 水墨风格增强",
        "filename": "sdxl-chinese-style-illustration.safetensors",
        "source": "Muapi / Hugging Face",
        "source_page": "https://huggingface.co/Muapi/sdxl-chinese-style-illustration",
        "download_url": "https://huggingface.co/Muapi/sdxl-chinese-style-illustration/resolve/main/sdxl-chinese-style-illustration.safetensors?download=true",
        "license": "openrail++",
        "base_model": "SDXL 1.0",
        "trigger_words": ["guofeng", "chinese style"],
        "expected_bytes": 340768396,
        "sha256": "5bc9ce5e0767a1dc2973056d32b1ca604408ff2c7cca38d145ae74d3742df584",
        "default_strength": 0.72,
    }
}
MIN_FREE_EXTRA_BYTES = 512 * 1024 * 1024


class ComfyUILoraError(RuntimeError):
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


def _lora(lora_id: str) -> dict[str, Any]:
    try:
        return LORA_CATALOG[lora_id]
    except KeyError as error:
        raise ComfyUILoraError("unsupported LoRA") from error


def lora_descriptor(lora_id: str = DEFAULT_LORA_ID) -> dict[str, Any]:
    return dict(_lora(lora_id))


def _target(lora: dict[str, Any]) -> Path:
    return LORA_DIR / str(lora["filename"])


def _partial(lora: dict[str, Any]) -> Path:
    return LORA_DIR / (str(lora["filename"]) + ".part")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _size_matches(lora: dict[str, Any]) -> bool:
    target = _target(lora)
    if not target.is_file():
        return False
    try:
        return target.stat().st_size == int(lora["expected_bytes"])
    except OSError:
        return False


def _valid_target(lora: dict[str, Any]) -> bool:
    return _size_matches(lora) and _sha256(_target(lora)) == str(lora["sha256"])


def _progress(lora: dict[str, Any]) -> dict[str, Any]:
    expected = int(lora["expected_bytes"])
    candidate = _target(lora) if _target(lora).is_file() else _partial(lora)
    try:
        downloaded = candidate.stat().st_size
    except OSError:
        downloaded = 0
    return {
        "downloaded_bytes": downloaded,
        "expected_bytes": expected,
        "progress_percent": round(min(100.0, downloaded * 100.0 / expected), 2) if expected else 0.0,
    }


def status(lora_id: str = DEFAULT_LORA_ID) -> dict[str, Any]:
    lora = _lora(lora_id)
    state = _load_state()
    try:
        pid = int(state.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if state.get("status") == "RUNNING" and pid and not _pid_alive(pid):
        state = _write_state(
            "FAIL",
            "INTERRUPTED",
            "LoRA 下载进程已退出；可重新点击安装继续断点下载",
            pid=None,
            lora_id=lora_id,
        )

    installed = bool(
        _size_matches(lora)
        and state.get("status") == "PASS"
        and state.get("lora_id") == lora_id
        and state.get("sha256") == lora["sha256"]
    )
    return {
        **state,
        "lora": {
            key: lora[key]
            for key in (
                "id", "label", "purpose", "filename", "source", "source_page",
                "license", "base_model", "trigger_words", "expected_bytes",
                "sha256", "default_strength",
            )
        },
        "installed": installed,
        "lora_path": str(_target(lora).relative_to(ROOT)),
        "log_path": str(LOG_PATH.relative_to(ROOT)),
        **_progress(lora),
    }


def _download_with_curl(lora: dict[str, Any], log) -> None:
    curl = shutil.which("curl")
    if not curl:
        raise ComfyUILoraError("未找到 curl，无法安全下载 LoRA")

    partial = _partial(lora)
    try:
        resume_at = partial.stat().st_size
    except OSError:
        resume_at = 0
    proxy = _select_download_proxy(curl, str(lora["download_url"]), log)
    route = _redact_proxy(proxy)
    _write_state(
        "RUNNING",
        "DOWNLOADING",
        f"正在通过 {route} 下载国风 LoRA；支持断点续传",
        pid=os.getpid(),
        lora_id=str(lora["id"]),
        filename=str(lora["filename"]),
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
    command.append(str(lora["download_url"]))
    log.write(("$ curl --location --continue-at " + str(resume_at) + " <fixed-lora-url>\n").encode("utf-8"))
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
        raise ComfyUILoraError(f"LoRA 下载失败，curl 退出码 {result.returncode}")


def install(lora_id: str = DEFAULT_LORA_ID) -> dict[str, Any]:
    lora = _lora(lora_id)
    if not (COMFYUI_DIR / "main.py").is_file():
        raise ComfyUILoraError("ComfyUI 核心尚未安装")

    LORA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if _valid_target(lora):
        return _write_state(
            "PASS",
            "COMPLETE",
            "国风 LoRA 已安装并通过 SHA256 校验",
            pid=None,
            lora_id=lora_id,
            filename=lora["filename"],
            sha256=lora["sha256"],
        )

    expected = int(lora["expected_bytes"])
    partial = _partial(lora)
    try:
        partial_bytes = partial.stat().st_size
    except OSError:
        partial_bytes = 0
    required = max(0, expected - partial_bytes) + MIN_FREE_EXTRA_BYTES
    try:
        free = shutil.disk_usage(LORA_DIR).free
    except OSError:
        free = required
    if free < required:
        raise ComfyUILoraError(
            f"磁盘空间不足：还需要约 {required / (1024 ** 3):.1f} GB 可用空间"
        )

    with LOG_PATH.open("ab") as log:
        log.write(f"\n=== ComfyUI LoRA install {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode())
        try:
            _download_with_curl(lora, log)
            try:
                size = partial.stat().st_size
            except OSError as error:
                raise ComfyUILoraError("LoRA 下载完成后文件不存在") from error
            if size != expected:
                raise ComfyUILoraError(
                    f"LoRA 文件大小不匹配：expected={expected}, actual={size}"
                )

            _write_state(
                "RUNNING",
                "VERIFYING",
                "正在执行 LoRA SHA256 校验",
                pid=os.getpid(),
                lora_id=lora_id,
                filename=lora["filename"],
            )
            actual_sha = _sha256(partial)
            if actual_sha != str(lora["sha256"]):
                invalid = partial.with_name(partial.name + f".invalid-{int(time.time())}")
                partial.replace(invalid)
                raise ComfyUILoraError(
                    f"LoRA SHA256 不匹配；异常文件已隔离为 {invalid.name}"
                )
            partial.replace(_target(lora))
            return _write_state(
                "PASS",
                "COMPLETE",
                "国风 LoRA 已安装并通过 SHA256 校验",
                pid=None,
                lora_id=lora_id,
                filename=lora["filename"],
                sha256=actual_sha,
            )
        except Exception as error:
            _write_state(
                "FAIL",
                "FAILED",
                str(error),
                pid=None,
                lora_id=lora_id,
                filename=lora["filename"],
            )
            if isinstance(error, ComfyUILoraError):
                raise
            raise ComfyUILoraError(str(error)) from error


def start_background_install(lora_id: str = DEFAULT_LORA_ID) -> dict[str, Any]:
    _lora(lora_id)
    current = status(lora_id)
    if current.get("installed"):
        return {**current, "action": "ALREADY_INSTALLED"}
    if current.get("status") == "RUNNING":
        return {**current, "action": "ALREADY_RUNNING"}

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("ab") as log:
        try:
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--install", lora_id],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as error:
            raise ComfyUILoraError(f"无法启动 LoRA 下载进程: {error}") from error

    state = _write_state(
        "RUNNING",
        "STARTING",
        "国风 LoRA 下载器已启动",
        pid=process.pid,
        lora_id=lora_id,
        filename=_lora(lora_id)["filename"],
    )
    return {**state, "action": "STARTED", **_progress(_lora(lora_id))}


def main() -> int:
    if "--install" not in sys.argv:
        print(json.dumps(status(), ensure_ascii=False))
        return 0
    index = sys.argv.index("--install")
    lora_id = sys.argv[index + 1] if len(sys.argv) > index + 1 else DEFAULT_LORA_ID
    try:
        print(json.dumps(install(lora_id), ensure_ascii=False))
        return 0
    except ComfyUILoraError as error:
        print(f"comfyui-lora-error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
