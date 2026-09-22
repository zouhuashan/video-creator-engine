#!/usr/bin/env python3
"""P35 Codex image-generation batch runner.

This module deliberately uses the user's already-authenticated local Codex CLI.
It does not store or request an API key.  Each frame is generated in an
ephemeral non-interactive Codex run using the built-in $imagegen skill.

Scheduling is dependency-aware:
- canonical reset frames can run in parallel;
- continuity frames wait until their previous accepted frame is READY;
- already READY frames are skipped;
- failed frames are retriable without regenerating successful frames.

The runner writes a small local status file plus per-frame logs under the P35
shot directory.  Remote reference upload and Codex quota usage require explicit
Web confirmation before a batch starts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from scripts import gpt_keyframe_pipeline as p35


ROOT = Path(__file__).resolve().parents[1]
STATUS_NAME = "codex-batch-status.json"
LOG_DIR_NAME = "codex-logs"
RAW_DIR_NAME = "codex-raw"
MAX_CONCURRENCY = 3
DEFAULT_CONCURRENCY = 2
FRAME_TIMEOUT_SECONDS = 15 * 60

_LOCK = threading.RLock()
_ACTIVE: dict[str, dict[str, Any]] = {}


class CodexKeyframeBatchError(RuntimeError):
    pass


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _key(project: Path, spec_id: str) -> str:
    return f"{Path(project).resolve()}::{spec_id}"


def _shot_root(project: Path, spec_id: str) -> Path:
    return p35._shot_root(Path(project).resolve(), spec_id)


def _status_path(project: Path, spec_id: str) -> Path:
    return _shot_root(project, spec_id) / STATUS_NAME


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def codex_executable() -> str:
    return str(shutil.which("codex") or "")


def environment_status() -> dict[str, Any]:
    executable = codex_executable()
    return {
        "installed": bool(executable),
        "executable": executable,
        "auth_mode": "EXISTING_CODEX_LOGIN",
        "api_key_required": False,
        "image_skill": "$imagegen",
        "max_concurrency": MAX_CONCURRENCY,
        "default_concurrency": DEFAULT_CONCURRENCY,
    }


def _read_status(project: Path, spec_id: str) -> dict[str, Any]:
    path = _status_path(project, spec_id)
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_status(project: Path, spec_id: str, **changes: Any) -> dict[str, Any]:
    with _LOCK:
        current = _read_status(project, spec_id)
        payload = {
            "schema_version": 1,
            "backend": "CODEX_IMAGEGEN_BATCH",
            "status": "IDLE",
            "completed_count": 0,
            "failed_count": 0,
            "active_indices": [],
            "wave": 0,
            "message": "",
            **current,
            **changes,
            "updated_at": _now(),
        }
        _atomic_json(_status_path(project, spec_id), payload)
        return payload


def status(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    manifest = p35.load_manifest(project)
    env = environment_status()
    if manifest is None:
        return {
            **env,
            "backend": "CODEX_IMAGEGEN_BATCH",
            "status": "NOT_PREPARED",
            "completed_count": 0,
            "failed_count": 0,
            "active_indices": [],
            "wave": 0,
            "message": "先准备 P35 Blender 控制帧",
        }

    spec_id = str(manifest.get("shot_spec_id") or "GB-SHOT-001")
    current = _read_status(project, spec_id)
    run = _ACTIVE.get(_key(project, spec_id))
    active = bool(run and run.get("thread") and run["thread"].is_alive())

    # A Web-server restart cannot preserve in-process worker threads.  Keep the
    # already generated frames, but mark the batch itself interrupted.
    if current.get("status") in {"RUNNING", "CANCEL_REQUESTED"} and not active:
        current = _write_status(
            project,
            spec_id,
            status="INTERRUPTED",
            active_indices=[],
            message="Web 服务已重启；已完成关键帧会保留，可点击 Codex 批量生成继续剩余帧。",
        )

    ready = sum(1 for frame in manifest.get("frames", []) if frame.get("status") == "READY")
    failed = sum(1 for frame in manifest.get("frames", []) if frame.get("status") == "FAILED")
    return {
        **env,
        "backend": "CODEX_IMAGEGEN_BATCH",
        "status": str(current.get("status") or "IDLE"),
        "completed_count": ready,
        "failed_count": failed,
        "active_indices": list(current.get("active_indices") or []),
        "wave": int(current.get("wave") or 0),
        "message": str(current.get("message") or ""),
        "started_at": str(current.get("started_at") or ""),
        "finished_at": str(current.get("finished_at") or ""),
        "concurrency": int(current.get("concurrency") or DEFAULT_CONCURRENCY),
        "total_count": int(manifest.get("keyframe_count") or len(manifest.get("frames", []))),
        "updated_at": str(current.get("updated_at") or ""),
    }


def _manifest_update_frame(
    project: Path,
    index: int,
    *,
    status_value: str,
    error: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with _LOCK:
        manifest = p35.load_manifest(project)
        if manifest is None:
            raise CodexKeyframeBatchError("P35 manifest 不存在")
        frame = next((item for item in manifest.get("frames", []) if int(item.get("index", -1)) == int(index)), None)
        if not isinstance(frame, dict):
            raise CodexKeyframeBatchError(f"关键帧 {index:03d} 不存在")
        frame["status"] = status_value
        if error:
            frame["codex_error"] = str(error)[-1200:]
        else:
            frame.pop("codex_error", None)
        if extra:
            frame.update(extra)
        manifest["generated_count"] = sum(1 for item in manifest.get("frames", []) if item.get("status") == "READY")
        if manifest["generated_count"] == int(manifest.get("keyframe_count") or 0):
            manifest["status"] = "READY"
        elif manifest["generated_count"]:
            manifest["status"] = "PARTIAL"
        else:
            manifest["status"] = "CONTROL_READY"
        manifest["automation"] = "CODEX_IMAGEGEN_BATCH"
        manifest["updated_at"] = _now()
        p35._atomic_json(p35._manifest_path(project, str(manifest["shot_spec_id"])), manifest)
        return manifest


def _frame_references(project: Path, manifest: dict[str, Any], frame: dict[str, Any]) -> list[tuple[str, Path]]:
    refs: list[tuple[str, Path]] = []
    character = project / str(manifest.get("character_reference") or "")
    scene = project / str(manifest.get("scene_reference") or "")
    control = project / str(frame.get("control_path") or "")
    for label, path in (("Reference 1 CHARACTER", character), ("Reference 2 SCENE", scene), ("Reference 3 BLENDER CONTROL", control)):
        if not path.is_file():
            raise CodexKeyframeBatchError(f"{label} 不存在：{path}")
        refs.append((label, path.resolve()))

    previous_index = frame.get("previous_index")
    if previous_index is not None:
        previous = next(
            (item for item in manifest.get("frames", []) if int(item.get("index", -1)) == int(previous_index)),
            None,
        )
        if not isinstance(previous, dict) or previous.get("status") != "READY":
            raise CodexKeyframeBatchError(f"前序关键帧 KF-{int(previous_index):03d} 尚未 READY")
        previous_path = project / str(previous.get("generated_path") or "")
        if not previous_path.is_file():
            raise CodexKeyframeBatchError(f"前序最终帧不存在：{previous_path}")
        refs.append(("Reference 4 PREVIOUS FINAL", previous_path.resolve()))
    return refs


def _codex_prompt(
    manifest: dict[str, Any],
    frame: dict[str, Any],
    refs: list[tuple[str, Path]],
    output_path: Path,
) -> str:
    reference_lines = "\n".join(f"- {label}: {path}" for label, path in refs)
    return f"""$imagegen

Execute one VideoCreator P35 final-keyframe render. This is an image-generation task, not a coding task.

Read and use these LOCAL IMAGE REFERENCES with their exact roles:
{reference_lines}

Frame contract:
{frame.get("prompt") or ""}

Hard requirements:
1. Actually invoke the image-generation skill; do not merely describe the image.
2. Use Reference 1 for character identity/face/hair/costume, Reference 2 for scene identity/materials/lighting, and Reference 3 as the sole camera/pose/layout/occlusion authority.
3. If Reference 4 is present, use it only for temporal visual continuity. Canonical character and scene references remain authoritative.
4. Generate exactly ONE clean final frame. No collage, captions, UI, borders, watermark, or alternate versions.
5. Write the final PNG EXACTLY to this path:
   {output_path}
6. Do not modify source code, manifest.json, AGENTS.md, task files, reference images, or any other repository file.
7. If the image tool writes the asset to another temporary path, copy/move the chosen final image to the exact path above.
8. Before finishing, verify that the exact output path exists and contains a PNG. If generation fails, return a concise error and do not fabricate a placeholder.

Only the image file at the required output path counts as success.
"""


def _tail(path: Path, max_chars: int = 1800) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-max_chars:]


def _run_one_frame(project: Path, spec_id: str, index: int, cancel: threading.Event, run: dict[str, Any]) -> tuple[int, bool, str]:
    if cancel.is_set():
        return index, False, "cancelled"

    manifest = p35.load_manifest(project)
    if manifest is None:
        return index, False, "manifest missing"
    frame = next((item for item in manifest.get("frames", []) if int(item.get("index", -1)) == index), None)
    if not isinstance(frame, dict):
        return index, False, "frame missing"
    if frame.get("status") == "READY":
        return index, True, "already ready"

    try:
        refs = _frame_references(project, manifest, frame)
    except CodexKeyframeBatchError as error:
        _manifest_update_frame(project, index, status_value="FAILED", error=str(error))
        return index, False, str(error)

    root = _shot_root(project, spec_id)
    raw_dir = root / RAW_DIR_NAME
    log_dir = root / LOG_DIR_NAME
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    raw = raw_dir / f"KF-{index:03d}.png"
    log_path = log_dir / f"KF-{index:03d}.log"
    final_message_path = log_dir / f"KF-{index:03d}-final.txt"
    raw.unlink(missing_ok=True)
    final_message_path.unlink(missing_ok=True)

    attempts = int(frame.get("codex_attempts") or 0) + 1
    _manifest_update_frame(
        project,
        index,
        status_value="CODEX_GENERATING",
        extra={
            "generator": "CODEX_IMAGEGEN",
            "codex_attempts": attempts,
            "codex_started_at": _now(),
            "codex_log_path": str(log_path.relative_to(project)),
        },
    )

    executable = codex_executable()
    if not executable:
        error = "未检测到 codex CLI"
        _manifest_update_frame(project, index, status_value="FAILED", error=error)
        return index, False, error

    prompt = _codex_prompt(manifest, frame, refs, raw.resolve())
    command = [executable]
    for _, reference_path in refs:
        command.extend(["--image", str(reference_path)])
    command.extend([
        "exec",
        "--sandbox",
        "workspace-write",
        "--ephemeral",
        "-o",
        str(final_message_path.resolve()),
        prompt,
    ])

    started = time.time()
    with log_path.open("w", encoding="utf-8") as log:
        log.write("=== VideoCreator P35 Codex ImageGen ===\n")
        log.write(f"frame=KF-{index:03d}\n")
        log.write(f"started_at={_now()}\n")
        log.write(f"reference_count={len(refs)}\n")
        log.flush()
        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                env=os.environ.copy(),
                start_new_session=True,
            )
        except OSError as error:
            detail = f"无法启动 Codex：{error}"
            _manifest_update_frame(project, index, status_value="FAILED", error=detail)
            return index, False, detail

        with _LOCK:
            run.setdefault("processes", {})[index] = process
        try:
            while process.poll() is None:
                if cancel.wait(0.5):
                    try:
                        process.terminate()
                    except OSError:
                        pass
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            process.kill()
                        except OSError:
                            pass
                    _manifest_update_frame(project, index, status_value="CONTROL_READY", error="")
                    return index, False, "cancelled"
                if time.time() - started > FRAME_TIMEOUT_SECONDS:
                    try:
                        process.terminate()
                    except OSError:
                        pass
                    detail = f"Codex 生成 KF-{index:03d} 超过 {FRAME_TIMEOUT_SECONDS // 60} 分钟"
                    _manifest_update_frame(project, index, status_value="FAILED", error=detail)
                    return index, False, detail
            return_code = int(process.returncode or 0)
        finally:
            with _LOCK:
                run.get("processes", {}).pop(index, None)

    if return_code != 0:
        detail = _tail(log_path) or f"Codex exit={return_code}"
        _manifest_update_frame(project, index, status_value="FAILED", error=detail)
        return index, False, detail

    if not raw.is_file() or raw.stat().st_size < 128:
        final_message = _tail(final_message_path, 1000)
        detail = "Codex 已结束但没有写出要求的 PNG"
        if final_message:
            detail += "：" + final_message
        _manifest_update_frame(project, index, status_value="FAILED", error=detail)
        return index, False, detail

    try:
        with _LOCK:
            result = p35.upload_generated_frame(
                project,
                index=index,
                filename=f"KF-{index:03d}.png",
                content=raw.read_bytes(),
            )
            frame_after = next(item for item in result["frames"] if int(item["index"]) == index)
            frame_after["generator"] = "CODEX_IMAGEGEN"
            frame_after["codex_attempts"] = attempts
            frame_after["codex_completed_at"] = _now()
            frame_after["codex_elapsed_seconds"] = round(time.time() - started, 1)
            frame_after["codex_log_path"] = str(log_path.relative_to(project))
            frame_after.pop("codex_error", None)
            result["automation"] = "CODEX_IMAGEGEN_BATCH"
            result["updated_at"] = _now()
            p35._atomic_json(p35._manifest_path(project, spec_id), result)
    except Exception as error:
        detail = f"Codex 图片已生成，但 VideoCreator 入库失败：{error}"
        _manifest_update_frame(project, index, status_value="FAILED", error=detail)
        return index, False, detail

    return index, True, "ready"


def _eligible_frames(manifest: dict[str, Any]) -> list[int]:
    ready = {int(item["index"]) for item in manifest.get("frames", []) if item.get("status") == "READY"}
    result: list[int] = []
    for frame in manifest.get("frames", []):
        index = int(frame.get("index", -1))
        if index < 0 or frame.get("status") == "READY":
            continue
        previous = frame.get("previous_index")
        if previous is None or int(previous) in ready:
            result.append(index)
    return result


def _run_batch(project: Path, spec_id: str, concurrency: int, cancel: threading.Event, run: dict[str, Any]) -> None:
    wave = 0
    try:
        while not cancel.is_set():
            manifest = p35.load_manifest(project)
            if manifest is None:
                raise CodexKeyframeBatchError("P35 manifest 不存在")
            remaining = [item for item in manifest.get("frames", []) if item.get("status") != "READY"]
            if not remaining:
                _write_status(
                    project,
                    spec_id,
                    status="PASS",
                    active_indices=[],
                    completed_count=int(manifest.get("keyframe_count") or len(manifest.get("frames", []))),
                    failed_count=0,
                    wave=wave,
                    finished_at=_now(),
                    message="Codex 批量关键帧全部 READY；可以检查关键帧后执行本地 24fps 插帧。",
                )
                return

            eligible = _eligible_frames(manifest)
            if not eligible:
                failed = [item for item in remaining if item.get("status") == "FAILED"]
                blocked = [int(item.get("index", -1)) for item in remaining if item.get("status") != "FAILED"]
                _write_status(
                    project,
                    spec_id,
                    status="PARTIAL" if failed else "FAIL",
                    active_indices=[],
                    completed_count=sum(1 for item in manifest.get("frames", []) if item.get("status") == "READY"),
                    failed_count=len(failed),
                    wave=wave,
                    finished_at=_now(),
                    message=(
                        f"{len(failed)} 张失败；其后依赖帧已暂停。点击 Codex 批量生成可只重试失败/剩余帧。"
                        if failed
                        else f"依赖无法继续：{blocked}"
                    ),
                )
                return

            # Failed frames become eligible again only on a new user-initiated
            # batch. Within one batch, do not silently retry and burn more quota.
            eligible = [
                index for index in eligible
                if next(item for item in manifest["frames"] if int(item["index"]) == index).get("status") != "FAILED"
            ]
            if not eligible:
                _write_status(
                    project,
                    spec_id,
                    status="PARTIAL",
                    active_indices=[],
                    completed_count=sum(1 for item in manifest.get("frames", []) if item.get("status") == "READY"),
                    failed_count=sum(1 for item in manifest.get("frames", []) if item.get("status") == "FAILED"),
                    wave=wave,
                    finished_at=_now(),
                    message="存在失败帧；为避免额外消耗 Codex 图像额度，本轮不自动重试。再次点击批量生成即可重试。",
                )
                return

            wave += 1
            batch = eligible[: max(1, concurrency)]
            _write_status(
                project,
                spec_id,
                status="RUNNING",
                active_indices=batch,
                wave=wave,
                message=f"第 {wave} 波：正在生成 " + ", ".join(f"KF-{index:03d}" for index in batch),
            )
            with ThreadPoolExecutor(max_workers=max(1, concurrency), thread_name_prefix="p35-codex") as executor:
                futures = {
                    executor.submit(_run_one_frame, project, spec_id, index, cancel, run): index
                    for index in batch
                }
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as error:
                        index = futures[future]
                        _manifest_update_frame(project, index, status_value="FAILED", error=str(error))

        _write_status(
            project,
            spec_id,
            status="CANCELLED",
            active_indices=[],
            finished_at=_now(),
            message="Codex 批量生成已停止；已完成帧保留，可稍后继续剩余帧。",
        )
    except Exception as error:
        _write_status(
            project,
            spec_id,
            status="FAIL",
            active_indices=[],
            finished_at=_now(),
            message=str(error)[-1600:],
        )
    finally:
        with _LOCK:
            _ACTIVE.pop(_key(project, spec_id), None)


def start(
    project: Path,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    confirm_codex_usage: bool = False,
    confirm_reference_upload: bool = False,
) -> dict[str, Any]:
    project = Path(project).resolve()
    if confirm_codex_usage is not True:
        raise CodexKeyframeBatchError("需要确认 Codex 图像生成会消耗 Codex 套餐用量")
    if confirm_reference_upload is not True:
        raise CodexKeyframeBatchError("需要确认允许将人物/场景/Blender 控制帧发送给 Codex 图像生成")
    if not codex_executable():
        raise CodexKeyframeBatchError("未检测到 codex CLI；请先在本机 Codex 登录并确保 codex 命令可用")
    try:
        concurrency = int(concurrency)
    except (TypeError, ValueError) as error:
        raise CodexKeyframeBatchError("Codex 并发数无效") from error
    if concurrency < 1 or concurrency > MAX_CONCURRENCY:
        raise CodexKeyframeBatchError(f"Codex 并发数必须为 1-{MAX_CONCURRENCY}")

    manifest = p35.load_manifest(project)
    if manifest is None or not manifest.get("frames"):
        raise CodexKeyframeBatchError("请先抽取 P35 Blender 控制帧")
    spec_id = str(manifest.get("shot_spec_id") or "GB-SHOT-001")
    run_key = _key(project, spec_id)

    with _LOCK:
        active = _ACTIVE.get(run_key)
        if active and active.get("thread") and active["thread"].is_alive():
            return status(project)

        # Explicit user retry: clear FAILED only; READY frames are never re-billed.
        changed = False
        for frame in manifest.get("frames", []):
            if frame.get("status") in {"FAILED", "CODEX_GENERATING"}:
                frame["status"] = "CONTROL_READY"
                frame.pop("codex_error", None)
                changed = True
        if changed:
            manifest["updated_at"] = _now()
            p35._atomic_json(p35._manifest_path(project, spec_id), manifest)

        cancel = threading.Event()
        run = {"cancel": cancel, "processes": {}}
        thread = threading.Thread(
            target=_run_batch,
            args=(project, spec_id, concurrency, cancel, run),
            name=f"p35-codex-{project.name}-{spec_id}",
            daemon=True,
        )
        run["thread"] = thread
        _ACTIVE[run_key] = run
        _write_status(
            project,
            spec_id,
            status="RUNNING",
            concurrency=concurrency,
            active_indices=[],
            wave=0,
            started_at=_now(),
            finished_at="",
            message="Codex 批量生成已启动；先并发 canonical reset，再按 continuity 依赖逐波推进。",
        )
        thread.start()
    return status(project)


def stop(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    manifest = p35.load_manifest(project)
    if manifest is None:
        raise CodexKeyframeBatchError("P35 manifest 不存在")
    spec_id = str(manifest.get("shot_spec_id") or "GB-SHOT-001")
    run_key = _key(project, spec_id)
    with _LOCK:
        run = _ACTIVE.get(run_key)
        if not run:
            return status(project)
        run["cancel"].set()
        for process in list(run.get("processes", {}).values()):
            try:
                process.terminate()
            except OSError:
                pass
        _write_status(
            project,
            spec_id,
            status="CANCEL_REQUESTED",
            message="正在停止 Codex 批量生成；已完成关键帧不会删除。",
        )
    return status(project)


__all__ = [
    "CodexKeyframeBatchError",
    "DEFAULT_CONCURRENCY",
    "MAX_CONCURRENCY",
    "environment_status",
    "start",
    "status",
    "stop",
]
