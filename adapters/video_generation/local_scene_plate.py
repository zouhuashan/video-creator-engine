"""Cost-free local scene-plate renderer.

This provider animates exactly one environment/final still with a restrained
camera move. It never fabricates character motion and never calls a remote
service.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from .base import VideoGenerationError, VideoGenerationProvider, VideoGenerationRequest, VideoGenerationResult


class LocalScenePlateVideo(VideoGenerationProvider):
    name = "local_scene_plate"
    remote_generation = False

    def __init__(self, *, ffmpeg: str = "ffmpeg", runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.ffmpeg = ffmpeg
        self.runner = runner

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        request.validate()
        if len(request.image_paths) != 1:
            raise VideoGenerationError("local scene plate requires exactly one approved image")
        output = Path(request.output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        command = self._command(request, output)
        try:
            completed = self.runner(command, check=False, capture_output=True, text=True)
        except OSError as error:
            raise VideoGenerationError("ffmpeg is unavailable") from error
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown ffmpeg error").strip().splitlines()[-1:]
            raise VideoGenerationError(f"local scene plate failed: {detail[0] if detail else 'unknown'}")
        if not output.is_file() or output.stat().st_size == 0:
            raise VideoGenerationError("local scene plate produced no output")
        return VideoGenerationResult(
            output_path=output,
            provider=self.name,
            duration_seconds=request.shot_duration_seconds,
            image_count=1,
            remote_generation=False,
        )

    def _command(self, request: VideoGenerationRequest, output: Path) -> list[str]:
        duration = float(request.shot_duration_seconds)
        fps = int(request.fps)
        total_frames = max(1, round(duration * fps))
        width = int(request.width)
        height = int(request.height)
        zoom_step = 0.025 / max(1, total_frames)
        vf = (
            f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,"
            f"crop={width*2}:{height*2},"
            f"zoompan="
            f"z='min(1.025,1+on*{zoom_step:.10f})':"
            f"x='iw/2-(iw/zoom/2)+sin(on/42)*10':"
            f"y='ih/2-(ih/zoom/2)+sin(on/55)*5':"
            f"d=1:s={width}x{height}:fps={fps},"
            f"trim=duration={duration:.6f},setpts=PTS-STARTPTS,format=yuv420p"
        )
        return [
            self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-framerate", str(fps), "-t", f"{duration:.6f}",
            "-i", str(request.image_paths[0]),
            "-vf", vf, "-an", "-r", str(fps),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
        ]


__all__ = ["LocalScenePlateVideo"]
