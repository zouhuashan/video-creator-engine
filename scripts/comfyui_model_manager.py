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

ROOT = Path(__file__).resolve().parents[1]
COMFYUI_DIR = ROOT / ".dependencies" / "ComfyUI"
CHECKPOINT_DIR = COMFYUI_DIR / "models" / "checkpoints"
LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "comfyui-model-install.log"
STATE_PATH = LOG_DIR / "comfyui-model-install.json"

DEFAULT_MODEL_ID = "animagine-xl-4.0"
MODEL_CATALOG: dict[str, dict[str, Any]] = {
    DEFAULT_MODEL_ID: {
        "id": DEFAULT_MODEL_ID,
        "label": "Animagine XL 4.0",
        "purpose": "动漫 / 国风动漫基础 checkpoint",
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


def _valid_target(model: dict[str, Any]) -> bool:
    path = _target(model)
    if not path.is_file():
        return False
    try:
        if path.stat().st_size != int(model["expected_bytes"]):
            return False
    except OSError:
        return False
    return _sha256(path) == str(model["sha256"])


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

    installed = _valid_target(model)
    if installed and state.get("status") != "RUNNING":
        state = {
            **state,
            "status": "PASS",
            "step": "COMPLETE",
            "detail": "checkpoint 已安装并通过 SHA256 校验",
        }

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


def _download_with_curl(model: dict[str, Any], log) -> None:
    curl = shutil.which("curl")
    if not curl:
        raise ComfyUIModelError("未找到 curl，无法安全下载 checkpoint")

    partial = _partial(model)
    command = [
        curl,
        "--location",
        "--fail",
        "--silent",
        "--show-error",
        "--retry",
        "4",
        "--retry-delay",
        "2",
        "--continue-at",
        "-",
        "--output",
        str(partial),
        str(model["download_url"]),
    ]
    log.write(("$ " + " ".join(command[:-1]) + " <fixed-model-url>\n").encode("utf-8"))
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
        return _write_state(
            "PASS",
            "COMPLETE",
            "checkpoint 已安装并通过 SHA256 校验",
            pid=None,
            model_id=model_id,
            filename=model["filename"],
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
