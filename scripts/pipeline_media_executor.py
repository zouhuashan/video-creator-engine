#!/usr/bin/env python3
"""FFmpeg assembly helpers for the software-first pipeline."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class PipelineMediaError(RuntimeError):
    pass


def _subtitle_filter(path: Path) -> str:
    escaped = str(Path(path).resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    style = (
        "FontName=PingFang SC,FontSize=18,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H80000000,BorderStyle=1,Outline=2,Shadow=0,"
        "MarginL=70,MarginR=70,MarginV=180,Alignment=2,WrapStyle=2"
    )
    return f"subtitles='{escaped}':force_style='{style}'"


def build_ffmpeg_command(
    video_path: Path,
    output_path: Path,
    *,
    voice_path: Path | None = None,
    subtitles_path: Path | None = None,
    ffmpeg: str | None = None,
) -> list[str]:
    binary = ffmpeg or shutil.which("ffmpeg") or "ffmpeg"
    video = Path(video_path).resolve()
    output = Path(output_path).resolve()
    command = [binary, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    if voice_path is not None:
        command += ["-i", str(Path(voice_path).resolve())]
    if subtitles_path is not None:
        command += ["-vf", _subtitle_filter(Path(subtitles_path))]
    command += ["-map", "0:v:0"]
    if voice_path is not None:
        command += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        command += ["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"]
    command += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ]
    return command


def assemble(
    video_path: Path,
    output_path: Path,
    *,
    voice_path: Path | None = None,
    subtitles_path: Path | None = None,
    ffmpeg: str | None = None,
) -> dict[str, object]:
    video = Path(video_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    voice = Path(voice_path).expanduser().resolve() if voice_path is not None else None
    subtitles = Path(subtitles_path).expanduser().resolve() if subtitles_path is not None else None
    if not video.is_file():
        raise PipelineMediaError(f"video input is missing: {video}")
    if voice is not None and not voice.is_file():
        raise PipelineMediaError(f"voice input is missing: {voice}")
    if subtitles is not None and not subtitles.is_file():
        raise PipelineMediaError(f"subtitle input is missing: {subtitles}")
    binary = ffmpeg or shutil.which("ffmpeg")
    if not binary:
        raise PipelineMediaError("ffmpeg is required for pipeline assembly")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.tmp{output.suffix}")
    command = build_ffmpeg_command(video, temporary, voice_path=voice, subtitles_path=subtitles, ffmpeg=binary)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        temporary.unlink(missing_ok=True)
        raise PipelineMediaError((completed.stderr or "ffmpeg assembly failed")[-1600:])
    if not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise PipelineMediaError("ffmpeg produced no output")
    temporary.replace(output)
    return {
        "output": str(output),
        "video": str(video),
        "voice": str(voice) if voice else "",
        "subtitles": str(subtitles) if subtitles else "",
        "ffmpeg": str(binary),
    }


__all__ = ["PipelineMediaError", "assemble", "build_ffmpeg_command"]
