"""Local FFmpeg image-to-video provider with deterministic motion."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from .base import VideoGenerationError, VideoGenerationProvider, VideoGenerationRequest, VideoGenerationResult


class LocalKenBurnsVideo(VideoGenerationProvider):
    name = "local_ken_burns"
    remote_generation = False

    def __init__(self, *, ffmpeg: str = "ffmpeg", runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.ffmpeg = ffmpeg
        self.runner = runner

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        request.validate()
        if not request.image_paths:
            raise VideoGenerationError("local Ken Burns generation requires at least one image")
        output = Path(request.output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        command = self._command(request, output)
        try:
            completed = self.runner(command, check=False, capture_output=True, text=True)
        except OSError as error:
            raise VideoGenerationError("ffmpeg is unavailable") from error
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip().splitlines()[-1:] or ["unknown ffmpeg error"]
            raise VideoGenerationError(f"local video generation failed: {detail[0]}")
        if not output.is_file() or output.stat().st_size == 0:
            raise VideoGenerationError("local video generation produced no output")
        duration = len(request.image_paths) * request.shot_duration_seconds - max(0, len(request.image_paths) - 1) * request.transition_seconds
        return VideoGenerationResult(output, self.name, duration, len(request.image_paths), self.remote_generation)

    def _command(self, request: VideoGenerationRequest, output: Path) -> list[str]:
        inputs: list[str] = []
        filters: list[str] = []
        for index, image in enumerate(request.image_paths):
            inputs.extend(["-loop", "1", "-framerate", str(request.fps), "-t", str(request.shot_duration_seconds), "-i", str(image)])
            filters.append(
                f"[{index}:v]scale={request.width}:{request.height}:force_original_aspect_ratio=increase,"
                f"crop={request.width}:{request.height},zoompan=z='min(zoom+0.00032,1.05)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={request.width}x{request.height}:fps={request.fps},"
                f"trim=duration={request.shot_duration_seconds},setpts=PTS-STARTPTS,format=yuv420p[v{index}]"
            )
        last = "v0"
        for index in range(1, len(request.image_paths)):
            # ``xfade``'s offset is relative to the first input of the
            # current pair.  After the first transition that input already
            # contains the previous crossfade, so each additional boundary
            # subtracts one more transition duration.
            offset = request.shot_duration_seconds * index - request.transition_seconds * index
            out = f"xf{index}"
            filters.append(f"[{last}][v{index}]xfade=transition=fade:duration={request.transition_seconds}:offset={offset}[{out}]")
            last = out
        return [self.ffmpeg, "-y", *inputs, "-filter_complex", ";".join(filters), "-map", f"[{last}]", "-r", str(request.fps), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
