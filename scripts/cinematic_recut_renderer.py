"""Render an honest local motion-comic edit from reviewed story frames.

Each beat is a distinct shot with a small camera move. Frames are cut rather
than blended, so changing geometry never produces the ghosting seen in the
earlier keyframe interpolation test.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


class CinematicRecutError(RuntimeError):
    pass


def _inside_project(project: Path, relative: str) -> Path:
    candidate = (project / relative).resolve()
    if not candidate.is_relative_to(project):
        raise CinematicRecutError(f"片段路径越出项目目录：{relative}")
    if not candidate.is_file():
        raise CinematicRecutError(f"缺少镜头图：{relative}")
    return candidate


def _camera_frame(source: Image.Image, progress: float, shot: dict[str, Any], size: tuple[int, int]) -> Image.Image:
    width, height = size
    ease = progress * progress * (3.0 - 2.0 * progress)
    zoom = float(shot.get("zoom_start", 1.0)) + (
        float(shot.get("zoom_end", 1.06)) - float(shot.get("zoom_start", 1.0))
    ) * ease
    if not 1.0 <= zoom <= 1.35:
        raise CinematicRecutError("镜头推拉必须在 1.0–1.35 之间")
    crop_width = round(width / zoom)
    crop_height = round(height / zoom)
    anchor_x = float(shot.get("anchor_x", 0.5))
    anchor_y = float(shot.get("anchor_y", 0.5))
    drift_x = float(shot.get("drift_x", 0.0)) * ease
    drift_y = float(shot.get("drift_y", 0.0)) * ease
    left = round((width - crop_width) * anchor_x + drift_x * width)
    top = round((height - crop_height) * anchor_y + drift_y * height)
    left = max(0, min(width - crop_width, left))
    top = max(0, min(height - crop_height, top))
    return source.crop((left, top, left + crop_width, top + crop_height)).resize(size, Image.Resampling.BICUBIC)


def _rain_overlay(size: tuple[int, int], frame: int, particles: list[tuple[float, float, float, float]]) -> Image.Image:
    width, height = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for x0, y0, speed, alpha in particles:
        x = (x0 - frame * speed * 0.18) % (width + 30) - 15
        y = (y0 + frame * speed) % (height + 30) - 15
        draw.line((x, y, x - 3, y + 14), fill=(175, 202, 222, int(alpha)), width=1)
    return overlay


def render_cinematic_recut(project_dir: Path, spec_id: str = "GB-SHOT-001") -> dict[str, Any]:
    project = Path(project_dir).resolve()
    output_dir = project / "graybox" / "quality-recuts"
    plan_path = output_dir / f"{spec_id}-edit-plan.json"
    if not plan_path.is_file():
        raise CinematicRecutError(f"缺少镜头剪辑计划：{plan_path.relative_to(project)}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    width, height = int(plan.get("width", 720)), int(plan.get("height", 1280))
    fps = int(plan.get("fps", 24))
    if (width, height, fps) != (720, 1280, 24):
        raise CinematicRecutError("当前试片固定为 720×1280 / 24fps")
    shots = plan.get("shots")
    if not isinstance(shots, list) or not 2 <= len(shots) <= 12:
        raise CinematicRecutError("剪辑计划需要 2–12 个镜头")
    prepared = []
    total_frames = 0
    for shot in shots:
        if not isinstance(shot, dict):
            raise CinematicRecutError("镜头内容必须为对象")
        relative = str(shot.get("image") or "")
        path = _inside_project(project, relative)
        frames = round(float(shot.get("duration_seconds") or 0) * fps)
        if not 12 <= frames <= 240:
            raise CinematicRecutError(f"镜头时长无效：{relative}")
        source = Image.open(path).convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
        prepared.append((shot, source, frames, relative))
        total_frames += frames
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise CinematicRecutError("未找到 FFmpeg")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{spec_id}-cinematic-recut-v1.mp4"
    command = [
        ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{width}x{height}", "-framerate", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(output),
    ]
    rng = random.Random(39038)
    particles = [
        (rng.uniform(0, width), rng.uniform(0, height), rng.uniform(10, 21), rng.uniform(15, 42))
        for _ in range(75)
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    frame_index = 0
    try:
        assert process.stdin is not None
        for shot, source, frames, _ in prepared:
            for local_index in range(frames):
                progress = local_index / max(1, frames - 1)
                canvas = _camera_frame(source, progress, shot, (width, height)).convert("RGBA")
                canvas = Image.alpha_composite(canvas, _rain_overlay((width, height), frame_index, particles))
                process.stdin.write(canvas.convert("RGB").tobytes())
                frame_index += 1
        process.stdin.close()
        stderr = process.stderr.read() if process.stderr else b""
        returncode = process.wait(timeout=120)
    except Exception:
        process.kill()
        process.wait()
        output.unlink(missing_ok=True)
        raise
    if returncode != 0 or not output.is_file() or output.stat().st_size < 1024:
        raise CinematicRecutError("本地重剪渲染失败：" + stderr.decode("utf-8", "replace")[-1500:])
    metadata = {
        "schema_version": 1,
        "status": "VISUAL_REVIEW_PENDING",
        "review_status": "PENDING",
        "project_id": project.name,
        "shot_id": spec_id,
        "provider": "codex_local_cinematic_edit",
        "output": str(output.relative_to(project)),
        "edit_plan": str(plan_path.relative_to(project)),
        "source_frames": [relative for _, _, _, relative in prepared],
        "duration_seconds": round(total_frames / fps, 3),
        "fps": fps,
        "width": width,
        "height": height,
        "local_only": True,
        "billable": False,
        "images_uploaded": False,
        "limitations": ["这是多镜头动态漫剪辑，人物和布料没有连续逐帧动作", "暂无正式配音和对白；音频需单独验收"],
    }
    output.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--spec-id", default="GB-SHOT-001")
    options = parser.parse_args()
    print(json.dumps(render_cinematic_recut(options.project, options.spec_id), ensure_ascii=False, indent=2))
