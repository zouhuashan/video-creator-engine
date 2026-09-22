#!/usr/bin/env python3
"""P35 GPT Keyframe bridge: Blender control frames -> AI redraw -> local smooth video.

The first implementation deliberately keeps ChatGPT Web manual.  VideoCreator
prepares deterministic Blender control frames and prompts, accepts the returned
AI keyframes, normalizes them to the approved 9:16 shot size, and uses local
FFmpeg motion interpolation to assemble a 24 fps preview.  No remote provider
is called by this module.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from scripts.graybox_manager import status as graybox_render_status
from scripts.graybox_reference_binding import resolve_bound_paths as resolve_graybox_reference_paths
from scripts.graybox_shot_spec import load_spec as load_graybox_spec


ROOT_RELATIVE = Path("graybox/gpt-keyframes")
MANIFEST_NAME = "manifest.json"
ALLOWED_KEYFRAME_COUNTS = {9, 17}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_UPLOAD_BYTES = 16 * 1024 * 1024


class GPTKeyframeError(RuntimeError):
    pass


def _clean_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "GB-SHOT-001")).strip("-._") or "GB-SHOT-001"


def _shot_root(project: Path, spec_id: str) -> Path:
    return Path(project).resolve() / ROOT_RELATIVE / _clean_id(spec_id)


def _manifest_path(project: Path, spec_id: str) -> Path:
    return _shot_root(project, spec_id) / MANIFEST_NAME


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _relative(project: Path, path: Path) -> str:
    return Path(path).resolve().relative_to(Path(project).resolve()).as_posix()


def _require_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise GPTKeyframeError("P35 本地关键帧路线需要 FFmpeg")
    return executable


def _run(command: list[str], *, label: str) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or label)[-1600:]
        raise GPTKeyframeError(f"{label}失败：{detail}")


def _image_magic_valid(path: Path) -> bool:
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return False
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if head.startswith(b"\xff\xd8\xff"):
        return True
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return True
    return False


def _frame_prompt(index: int, timestamp: float, *, anchor_reset: bool) -> str:
    continuity = (
        "This is a CANONICAL RESET frame. Do not inherit visual drift from prior frames; re-lock identity and environment from references 1 and 2."
        if anchor_reset
        else "Use the previous accepted final keyframe as reference 4 for temporal continuity, but references 1 and 2 remain the canonical identity/environment truth."
    )
    return (
        "This is one frame in a controlled VideoCreator keyframe-to-video sequence, not a new composition. "
        "Reference 1 = CHARACTER identity: keep exactly the same face, age, hairstyle, body proportions, costume structure, colors and accessories. "
        "Reference 2 = SCENE identity: keep exactly the same ancient-Chinese architecture, gate, lantern positions, materials, palette, atmosphere and lighting language. "
        "Reference 3 = CURRENT BLENDER CONTROL FRAME: it is the sole authority for camera framing, actor screen position, pose, gaze, occlusion and spatial layout. "
        f"{continuity} "
        "Redraw only the final visual appearance as premium cinematic semi-realistic 3D Chinese donghua with dimensional hair, layered cloth, PBR/NPR materials, warm lantern light, cool night fill, atmospheric depth and filmic depth of field. "
        "Do not redesign the camera. Do not move the actor. Do not invent a new pose. Do not add characters or props. "
        "Keep all important character and architectural content inside the central 84% of image width so the result can be center-cropped safely from 2:3 to 9:16. "
        f"Frame index {index:03d}, target timeline time {timestamp:.3f}s. Output one clean frame only, no text, no UI, no collage, no watermark."
    )


def load_manifest(project: Path) -> dict[str, Any] | None:
    project = Path(project).resolve()
    spec = load_graybox_spec(project)
    path = _manifest_path(project, str(spec.get("id") or "GB-SHOT-001"))
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GPTKeyframeError(f"P35 manifest 无法读取：{error}") from error
    if not isinstance(payload, dict):
        raise GPTKeyframeError("P35 manifest 格式无效")
    return payload


def prepare(project: Path, *, keyframe_count: int = 9) -> dict[str, Any]:
    project = Path(project).resolve()
    if keyframe_count not in ALLOWED_KEYFRAME_COUNTS:
        raise GPTKeyframeError("P35 首版只允许 9 或 17 张关键帧")
    ffmpeg = _require_ffmpeg()

    render = graybox_render_status(project)
    if not render.get("output_ready") or render.get("render_stale"):
        raise GPTKeyframeError("必须先完成当前 Shot Spec 对应的有效 Blender 白模")
    relative_video = str(render.get("output_path") or "")
    source_video = project / relative_video
    if not source_video.is_file():
        raise GPTKeyframeError("Blender 白模 MP4 不存在")

    spec = load_graybox_spec(project)
    review = spec.get("review") if isinstance(spec.get("review"), dict) else {}
    if str(review.get("status") or "").upper() != "APPROVED":
        raise GPTKeyframeError("必须先人工通过 Blender 白模，才能准备 P35 控制帧")
    character_reference, scene_reference, binding = resolve_graybox_reference_paths(project, require_complete=True)

    spec_id = str(spec.get("id") or "GB-SHOT-001")
    duration = float(spec.get("duration_seconds") or 8.0)
    fps = int(spec.get("fps") or 24)
    width = int(spec.get("width") or 720)
    height = int(spec.get("height") or 1280)
    if duration <= 0 or fps <= 0 or width <= 0 or height <= 0:
        raise GPTKeyframeError("Shot Spec 的 duration/fps/size 无效")

    root = _shot_root(project, spec_id)
    if root.exists():
        shutil.rmtree(root)
    control_dir = root / "control"
    generated_dir = root / "generated"
    normalized_dir = root / "normalized"
    output_dir = root / "output"
    for directory in (control_dir, generated_dir, normalized_dir, output_dir):
        directory.mkdir(parents=True, exist_ok=True)

    interval = duration / float(keyframe_count - 1)
    frames: list[dict[str, Any]] = []
    for index in range(keyframe_count):
        timeline_time = round(interval * index, 6)
        seek_time = min(timeline_time, max(0.0, duration - (1.0 / fps)))
        control = control_dir / f"KF-{index:03d}.png"
        _run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{seek_time:.6f}", "-i", str(source_video),
                "-frames:v", "1", str(control),
            ],
            label=f"抽取控制帧 {index:03d}",
        )
        if not control.is_file() or control.stat().st_size < 128:
            raise GPTKeyframeError(f"控制帧 {index:03d} 未生成")
        # Every ~2 seconds re-lock from canonical character + scene instead of
        # chaining the previous AI image forever.
        anchor_reset = index == 0 or (timeline_time > 0 and abs((timeline_time / 2.0) - round(timeline_time / 2.0)) < 0.08)
        frames.append({
            "id": f"GPT-KF-{index:03d}",
            "index": index,
            "timestamp_seconds": timeline_time,
            "seek_seconds": round(seek_time, 6),
            "control_path": _relative(project, control),
            "status": "CONTROL_READY",
            "reference_mode": "CANONICAL_RESET" if anchor_reset else "PREVIOUS_CONTINUITY",
            "previous_index": None if anchor_reset or index == 0 else index - 1,
            "prompt": _frame_prompt(index, timeline_time, anchor_reset=anchor_reset),
            "source_upload_path": "",
            "generated_path": "",
        })

    payload = {
        "schema_version": 1,
        "route": "CHATGPT_WEB_KEYFRAMES",
        "automation": "MANUAL_WEB_BRIDGE",
        "remote_generation": False,
        "project_id": project.name,
        "shot_spec_id": spec_id,
        "source_video": relative_video,
        "duration_seconds": duration,
        "target_fps": fps,
        "width": width,
        "height": height,
        "keyframe_count": keyframe_count,
        "keyframe_rate": round((keyframe_count - 1) / duration, 6),
        "character_reference": str((binding.get("character_reference") or {}).get("path") or _relative(project, character_reference)),
        "scene_reference": str((binding.get("scene_reference") or {}).get("path") or _relative(project, scene_reference)),
        "status": "CONTROL_READY",
        "generated_count": 0,
        "frames": frames,
        "interpolation": {
            "backend": "FFMPEG_MINTERPOLATE",
            "status": "NOT_RUN",
            "output": "",
        },
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _atomic_json(_manifest_path(project, spec_id), payload)
    return payload


def upload_generated_frame(
    project: Path,
    *,
    index: int,
    filename: str,
    content: bytes,
) -> dict[str, Any]:
    project = Path(project).resolve()
    payload = load_manifest(project)
    if payload is None:
        raise GPTKeyframeError("请先准备 P35 Blender 控制帧")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < int(payload["keyframe_count"]):
        raise GPTKeyframeError("关键帧 index 无效")
    if not isinstance(content, (bytes, bytearray)) or not content or len(content) > MAX_UPLOAD_BYTES:
        raise GPTKeyframeError("关键帧图片必须在 1 byte 到 16 MB 之间")
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise GPTKeyframeError("只支持 PNG / JPEG / WebP 关键帧")

    frame = next((item for item in payload["frames"] if int(item["index"]) == index), None)
    if not isinstance(frame, dict):
        raise GPTKeyframeError("关键帧不存在")
    root = _shot_root(project, str(payload["shot_spec_id"]))
    raw = root / "generated" / f"KF-{index:03d}{suffix}"
    raw.write_bytes(bytes(content))
    if not _image_magic_valid(raw):
        raw.unlink(missing_ok=True)
        raise GPTKeyframeError("上传内容不是有效 PNG / JPEG / WebP")

    ffmpeg = _require_ffmpeg()
    normalized = root / "normalized" / f"KF-{index:03d}.png"
    width = int(payload["width"])
    height = int(payload["height"])
    _run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw),
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
            "-frames:v", "1", str(normalized),
        ],
        label=f"规范化关键帧 {index:03d}",
    )
    if not normalized.is_file() or normalized.stat().st_size < 128:
        raise GPTKeyframeError("规范化后的关键帧未生成")

    frame["source_upload_path"] = _relative(project, raw)
    frame["generated_path"] = _relative(project, normalized)
    frame["status"] = "READY"
    payload["generated_count"] = sum(1 for item in payload["frames"] if item.get("status") == "READY")
    payload["status"] = "READY" if payload["generated_count"] == payload["keyframe_count"] else "PARTIAL"
    payload["interpolation"] = {"backend": "FFMPEG_MINTERPOLATE", "status": "NOT_RUN", "output": ""}
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _atomic_json(_manifest_path(project, str(payload["shot_spec_id"])), payload)
    return payload


def interpolate(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    payload = load_manifest(project)
    if payload is None:
        raise GPTKeyframeError("请先准备 P35 Blender 控制帧")
    if any(item.get("status") != "READY" for item in payload.get("frames", [])):
        raise GPTKeyframeError("必须先上传全部 AI 最终关键帧，才能本地插帧")
    ffmpeg = _require_ffmpeg()

    root = _shot_root(project, str(payload["shot_spec_id"]))
    normalized_pattern = root / "normalized" / "KF-%03d.png"
    output_dir = root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    count = int(payload["keyframe_count"])
    duration = float(payload["duration_seconds"])
    target_fps = int(payload["target_fps"])
    source_rate = (count - 1) / duration
    output = output_dir / f"{_clean_id(str(payload['shot_spec_id']))}-{count}kf-{target_fps}fps.mp4"
    filters = (
        f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
        f"trim=duration={duration:.6f},setpts=PTS-STARTPTS,format=yuv420p"
    )
    _run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-framerate", f"{source_rate:.8f}", "-start_number", "0",
            "-i", str(normalized_pattern),
            "-vf", filters,
            "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
        ],
        label="P35 本地插帧",
    )
    if not output.is_file() or output.stat().st_size < 1024:
        raise GPTKeyframeError("P35 本地视频未生成")

    payload["status"] = "VIDEO_READY"
    payload["interpolation"] = {
        "backend": "FFMPEG_MINTERPOLATE",
        "status": "PASS",
        "source_keyframe_rate": round(source_rate, 6),
        "target_fps": target_fps,
        "output": _relative(project, output),
        "output_bytes": output.stat().st_size,
    }
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _atomic_json(_manifest_path(project, str(payload["shot_spec_id"])), payload)
    return payload


def inventory(project: Path) -> dict[str, Any]:
    payload = load_manifest(project)
    if payload is None:
        spec = load_graybox_spec(project)
        return {
            "schema_version": 1,
            "route": "CHATGPT_WEB_KEYFRAMES",
            "automation": "MANUAL_WEB_BRIDGE",
            "project_id": Path(project).resolve().name,
            "shot_spec_id": str(spec.get("id") or "GB-SHOT-001"),
            "status": "NOT_PREPARED",
            "keyframe_count": 9,
            "generated_count": 0,
            "frames": [],
            "interpolation": {"backend": "FFMPEG_MINTERPOLATE", "status": "NOT_RUN", "output": ""},
        }
    return payload


__all__ = [
    "ALLOWED_KEYFRAME_COUNTS",
    "GPTKeyframeError",
    "MAX_UPLOAD_BYTES",
    "interpolate",
    "inventory",
    "load_manifest",
    "prepare",
    "upload_generated_frame",
]
