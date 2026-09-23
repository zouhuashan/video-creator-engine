"""Cost-free two-still hard-cut renderer.

Two approved final stills represent before/after action states. Each half gets
a restrained camera move and the boundary is a real edit cut: no xfade, no
optical-flow interpolation, and no attempt to synthesize missing body motion.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from .base import VideoGenerationError, VideoGenerationProvider, VideoGenerationRequest, VideoGenerationResult


class LocalTwoCutVideo(VideoGenerationProvider):
    name = "local_two_cut"
    remote_generation = False

    def __init__(self, *, ffmpeg: str = "ffmpeg", runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.ffmpeg = ffmpeg
        self.runner = runner

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        request.validate()
        if len(request.image_paths) != 2:
            raise VideoGenerationError("local two cut requires exactly two approved images")
        output = Path(request.output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        command = self._command(request, output)
        try:
            completed = self.runner(command, check=False, capture_output=True, text=True)
        except OSError as error:
            raise VideoGenerationError("ffmpeg is unavailable") from error
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown ffmpeg error").strip().splitlines()[-1:]
            raise VideoGenerationError(f"local two cut failed: {detail[0] if detail else 'unknown'}")
        if not output.is_file() or output.stat().st_size == 0:
            raise VideoGenerationError("local two cut produced no output")
        return VideoGenerationResult(
            output_path=output,
            provider=self.name,
            duration_seconds=request.shot_duration_seconds,
            image_count=2,
            remote_generation=False,
        )

    def _command(self, request: VideoGenerationRequest, output: Path) -> list[str]:
        total = float(request.shot_duration_seconds)
        fps = int(request.fps)
        width = int(request.width)
        height = int(request.height)
        first = round(total / 2.0, 6)
        second = round(total - first, 6)
        durations = (first, second)
        args: list[str] = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
        filters: list[str] = []
        for index, (image, duration) in enumerate(zip(request.image_paths, durations)):
            args.extend(["-loop", "1", "-framerate", str(fps), "-t", f"{duration:.6f}", "-i", str(image)])
            frame_count = max(1, round(duration * fps))
            zoom_step = 0.018 / frame_count
            direction = 1 if index == 0 else -1
            filters.append(
                f"[{index}:v]scale={width*2}:{height*2}:force_original_aspect_ratio=increase,"
                f"crop={width*2}:{height*2},"
                f"zoompan=z='min(1.018,1+on*{zoom_step:.10f})':"
                f"x='iw/2-(iw/zoom/2)+({direction})*sin(on/30)*5':"
                f"y='ih/2-(ih/zoom/2)+sin(on/38)*3':"
                f"d=1:s={width}x{height}:fps={fps},"
                f"trim=duration={duration:.6f},setpts=PTS-STARTPTS,format=yuv420p[v{index}]"
            )
        filters.append(
            f"[v0][v1]concat=n=2:v=1:a=0,trim=duration={total:.6f},setpts=PTS-STARTPTS[outv]"
        )
        return [
            *args,
            "-filter_complex", ";".join(filters),
            "-map", "[outv]", "-an", "-r", str(fps),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
        ]


__all__ = ["LocalTwoCutVideo"]
