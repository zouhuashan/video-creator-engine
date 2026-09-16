#!/usr/bin/env python3
"""Run the local story storyboard path from keyframes to narrated MP4."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.video.video_use import _media_tool, video_use_environment  # noqa: E402
from adapters.video_generation import LocalKenBurnsVideo, VideoGenerationError, VideoGenerationRequest, normalize_image_paths  # noqa: E402


class LocalStoryboardError(RuntimeError):
    pass


def build_mux_command(video: Path, voice: Path, subtitles: Path, output: Path) -> list[str]:
    ffmpeg = _media_tool("ffmpeg") or "ffmpeg"
    style = "FontName=Hiragino Sans GB,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=180"
    return [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(voice),
        "-vf", f"subtitles={subtitles}:force_style='{style}'", "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(output),
    ]


def run_local_storyboard(
    project_dir: Path,
    output: Path,
    *,
    shot_duration: float = 3.1,
    transition: float = 0.4,
) -> dict[str, object]:
    project_dir = Path(project_dir).resolve()
    scene_dir = project_dir / "assets" / "scenes"
    image_paths = tuple(scene_dir / name for name in ("shot-01-chart-discovery.png", "shot-02-compass-clue.png", "shot-03-departure.png"))
    voice = project_dir / "voice" / "tang-xiaoshan-sample.wav"
    subtitles = project_dir / "subtitles.srt"
    for path in (*image_paths, voice, subtitles):
        if not path.is_file():
            raise LocalStoryboardError(f"required local storyboard asset is missing: {path}")
    output = Path(output).expanduser().resolve()
    if output.exists():
        raise LocalStoryboardError(f"refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    silent = output.with_name(f".{output.stem}.silent.mp4")
    request = VideoGenerationRequest(
        image_paths=normalize_image_paths(image_paths), output_path=silent,
        shot_duration_seconds=shot_duration, transition_seconds=transition,
        width=1080, height=1920, prompt_text="国风动漫连续分镜，镜头缓慢推进，保持人物与场景设计一致",
    )
    try:
        LocalKenBurnsVideo().generate(request)
        completed = subprocess.run(build_mux_command(silent, voice, subtitles, output), check=False, capture_output=True, text=True, env=video_use_environment())
        if completed.returncode != 0:
            raise LocalStoryboardError(completed.stderr[-1200:] or "ffmpeg narration merge failed")
    except VideoGenerationError as error:
        raise LocalStoryboardError(str(error)) from error
    finally:
        silent.unlink(missing_ok=True)
    if not output.is_file() or output.stat().st_size == 0:
        raise LocalStoryboardError("local storyboard produced no output")
    return {"status": "PASS", "provider": "local_ken_burns", "output": str(output), "image_count": len(image_paths), "voice": str(voice), "subtitles": str(subtitles)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shot-duration", type=float, default=3.1)
    parser.add_argument("--transition", type=float, default=0.4)
    args = parser.parse_args()
    try:
        print(run_local_storyboard(args.project_dir, args.output, shot_duration=args.shot_duration, transition=args.transition))
    except (LocalStoryboardError, OSError, ValueError) as error:
        print(f"local_storyboard_pipeline: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
