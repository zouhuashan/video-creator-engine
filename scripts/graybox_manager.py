#!/usr/bin/env python3
"""Manage deterministic Blender graybox renders for the local Web console."""

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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.graybox_shot_spec import DEFAULT_SPEC_ID, ensure_default_spec, load_spec, spec_path

LOG_DIR = ROOT / "logs"
BLENDER_SCRIPT = ROOT / "scripts" / "blender_graybox_scene.py"


class GrayboxRenderError(RuntimeError):
    pass


def _blender_candidates() -> list[str]:
    candidates: list[str] = []
    env = str(os.environ.get("BLENDER_BIN") or "").strip()
    if env:
        candidates.append(env)
    found = shutil.which("blender")
    if found:
        candidates.append(found)
    for path in (
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/Applications/Blender 4.5.app/Contents/MacOS/Blender",
        "/Applications/Blender 4.4.app/Contents/MacOS/Blender",
        "/Applications/Blender 4.3.app/Contents/MacOS/Blender",
    ):
        candidates.append(path)
    unique: list[str] = []
    for item in candidates:
        if item not in unique:
            unique.append(item)
    return unique


def blender_executable() -> Path | None:
    for item in _blender_candidates():
        path = Path(item).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path.resolve()
    return None


def _spec_sha256(project_dir: Path, spec_id: str = DEFAULT_SPEC_ID) -> str:
    path = spec_path(Path(project_dir).resolve(), spec_id)
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _state_path(project_dir: Path) -> Path:
    return Path(project_dir).resolve() / "graybox" / "render-status.json"


def _output_path(project_dir: Path, spec_id: str = DEFAULT_SPEC_ID) -> Path:
    return Path(project_dir).resolve() / "graybox" / "renders" / f"{spec_id}.mp4"


def _log_path(project_dir: Path) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR / f"graybox-{Path(project_dir).resolve().name}.log"


def _write_state(project_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path = _state_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        **payload,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return body


def _load_state(project_dir: Path) -> dict[str, Any]:
    path = _state_path(project_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
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


def status(project_dir: Path, spec_id: str = DEFAULT_SPEC_ID) -> dict[str, Any]:
    project_dir = Path(project_dir).resolve()
    blender = blender_executable()
    spec_file = spec_path(project_dir, spec_id)
    spec = load_spec(project_dir, spec_id) if spec_file.is_file() else None
    output = _output_path(project_dir, spec_id)
    current_spec_sha256 = _spec_sha256(project_dir, spec_id)
    state = _load_state(project_dir)
    try:
        pid = int(state.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if state.get("status") == "RUNNING" and pid and not _pid_alive(pid):
        if output.is_file() and output.stat().st_size > 1024:
            state = _write_state(project_dir, {
                **state,
                "status": "PASS",
                "step": "COMPLETE",
                "detail": "Blender 白模渲染完成",
                "pid": None,
            })
        else:
            state = _write_state(project_dir, {
                **state,
                "status": "FAIL",
                "step": "INTERRUPTED",
                "detail": "Blender 白模渲染进程已退出，未检测到有效 MP4",
                "pid": None,
            })
    render_matches_spec = bool(
        output.is_file()
        and output.stat().st_size > 1024
        and current_spec_sha256
        and str(state.get("spec_sha256") or "") == current_spec_sha256
    )
    return {
        **state,
        "blender_installed": blender is not None,
        "blender_path": str(blender) if blender else "",
        "spec_ready": spec is not None,
        "spec": spec,
        "output_ready": render_matches_spec,
        "render_stale": output.is_file() and output.stat().st_size > 1024 and not render_matches_spec,
        "spec_sha256": current_spec_sha256,
        "output_path": str(output.relative_to(project_dir)) if output.is_file() else "",
        "output_bytes": output.stat().st_size if output.is_file() else 0,
        "log_path": str(_log_path(project_dir).relative_to(ROOT)),
    }


def ensure_spec(project_dir: Path) -> dict[str, Any]:
    path = ensure_default_spec(project_dir)
    return {
        "status": "SPEC_READY",
        "spec_id": DEFAULT_SPEC_ID,
        "spec_path": str(path.relative_to(Path(project_dir).resolve())),
        "spec": load_spec(project_dir),
    }


def start_render(project_dir: Path, spec_id: str = DEFAULT_SPEC_ID) -> dict[str, Any]:
    project_dir = Path(project_dir).resolve()
    blender = blender_executable()
    if blender is None:
        raise GrayboxRenderError(
            "未检测到 Blender。请安装 Blender，或设置 BLENDER_BIN 指向 Blender 可执行文件。"
        )
    spec_file = ensure_default_spec(project_dir)
    spec = load_spec(project_dir, spec_id)
    output = _output_path(project_dir, spec_id)
    output.parent.mkdir(parents=True, exist_ok=True)

    current = status(project_dir, spec_id)
    if current.get("status") == "RUNNING":
        return {**current, "action": "ALREADY_RUNNING"}

    log_path = _log_path(project_dir)
    command = [
        str(blender),
        "--background",
        "--factory-startup",
        "--python",
        str(BLENDER_SCRIPT),
        "--",
        str(spec_file),
        str(output),
    ]
    with log_path.open("ab") as log:
        log.write(("\n=== Graybox render " + time.strftime("%Y-%m-%d %H:%M:%S") + " ===\n").encode("utf-8"))
        log.write(("$ " + " ".join(command[:6]) + " -- <spec> <output>\n").encode("utf-8"))
        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as error:
            raise GrayboxRenderError(f"无法启动 Blender: {error}") from error

    state = _write_state(project_dir, {
        "status": "RUNNING",
        "step": "BLENDER_RENDER",
        "detail": f"正在渲染 {spec_id} · {spec['duration_seconds']}s · {spec['fps']}fps",
        "pid": process.pid,
        "spec_id": spec_id,
        "spec_sha256": _spec_sha256(project_dir, spec_id),
        "output_path": str(output.relative_to(project_dir)),
    })
    return {**state, "action": "STARTED"}


def reset(project_dir: Path) -> dict[str, Any]:
    project_dir = Path(project_dir).resolve()
    state = status(project_dir)
    if state.get("status") == "RUNNING":
        raise GrayboxRenderError("白模正在渲染，不能重置")
    path = _state_path(project_dir)
    if path.exists():
        path.unlink()
    return status(project_dir)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: graybox_manager.py <project-dir>")
    print(json.dumps(status(Path(sys.argv[1])), ensure_ascii=False, indent=2))
