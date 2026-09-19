#!/usr/bin/env python3
"""Executable local media stages for the software-first pipeline.

This module deliberately reuses project artifacts before generating anything.
It provides a local TTS bridge, deterministic subtitle creation from known
script/timeline text, and FFmpeg assembly without any ASR round-trip.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class PipelineMediaError(RuntimeError):
    pass


def _relative(project: Path, path: Path | None) -> str:
    if path is None:
        return ""
    return path.resolve().relative_to(project.resolve()).as_posix()


def _existing(project: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        matches = [item for item in sorted(project.glob(pattern)) if item.is_file()]
        if matches:
            return matches[-1]
    return None


def _timeline(project: Path) -> list[dict[str, Any]]:
    path = project / "dynamic" / "mouth-cues.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PipelineMediaError("mouth-cues.json is invalid") from error
    timeline = payload.get("timeline", []) if isinstance(payload, dict) else []
    return [item for item in timeline if isinstance(item, dict)]


def ensure_tts(project: Path) -> dict[str, Any]:
    """Reuse project audio or synthesize known timeline text with local macOS TTS."""
    project = project.resolve()
    existing = _existing(project, ("voice/*.wav", "audio/**/*.wav", "audio/**/*.mp3"))
    if existing:
        return {"status": "PASS", "reused": True, "asset": _relative(project, existing), "provider": "existing"}

    timeline = _timeline(project)
    spoken = [item for item in timeline if str(item.get("text") or "").strip()]
    if not spoken:
        return {
            "status": "SKIPPED",
            "reused": False,
            "asset": "",
            "provider": "none",
            "reason": "no spoken timeline text; audio is optional for this shot",
        }
    if shutil.which("say") is None:
        raise PipelineMediaError("local TTS requires macOS say when no reusable audio exists")
    if shutil.which("ffmpeg") is None:
        raise PipelineMediaError("local TTS requires ffmpeg")

    from scripts.generate_local_tts import generate

    result = generate(project)
    audio = _existing(project, ("audio/tts-local/*.wav",))
    if audio is None:
        raise PipelineMediaError("local TTS completed without producing an audio file")
    return {
        "status": "PASS",
        "reused": False,
        "asset": _relative(project, audio),
        "provider": "macos_say",
        "generated_count": int(result.get("count") or 0),
        "timeline": str(result.get("output") or ""),
    }


def _srt_time(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def ensure_subtitles(project: Path) -> dict[str, Any]:
    """Build subtitles directly from known script/timeline text; never call ASR."""
    project = project.resolve()
    existing = _existing(project, ("*.srt", "*.ass", "subtitles/**/*.srt", "subtitles/**/*.ass", "renders/**/*.srt"))
    if existing:
        return {
            "status": "PASS",
            "reused": True,
            "asset": _relative(project, existing),
            "source": "existing",
            "asr_round_trip": False,
        }

    timeline = _timeline(project)
    lines = [item for item in timeline if str(item.get("text") or "").strip()]
    if not lines:
        return {
            "status": "SKIPPED",
            "reused": False,
            "asset": "",
            "source": "SCRIPT_TTS_TIMING",
            "asr_round_trip": False,
            "reason": "no spoken timeline text; subtitles are optional for this shot",
        }

    output = project / "pipeline" / "subtitles" / "pipeline.srt"
    output.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    cursor = 0.0
    for index, item in enumerate(lines, 1):
        start = float(item.get("start_seconds") or 0.0)
        end = float(item.get("end_seconds") or 0.0)
        duration = max(0.8, end - start)
        blocks.extend([
            str(index),
            f"{_srt_time(cursor)} --> {_srt_time(cursor + duration)}",
            str(item.get("text") or "").strip(),
            "",
        ])
        cursor += duration
    output.write_text("\n".join(blocks), encoding="utf-8")
    return {
        "status": "PASS",
        "reused": False,
        "asset": _relative(project, output),
        "source": "SCRIPT_TTS_TIMING",
        "asr_round_trip": False,
        "line_count": len(lines),
        "duration_seconds": round(cursor, 3),
    }


def assemble_final(
    project: Path,
    video: Path,
    *,
    audio: Path | None = None,
    subtitles: Path | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    """Mux available video/audio/subtitles into a standard MP4 using FFmpeg."""
    project = project.resolve()
    video = video.resolve()
    if not video.is_file():
        raise PipelineMediaError("assembly video input is missing")
    if shutil.which("ffmpeg") is None:
        raise PipelineMediaError("FFmpeg is required for assembly")
    output = (output or (project / "final.mp4")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    audio_index: int | None = None
    subtitle_index: int | None = None
    next_index = 1
    if audio is not None and audio.is_file():
        command += ["-i", str(audio)]
        audio_index = next_index
        next_index += 1
    if subtitles is not None and subtitles.is_file() and subtitles.stat().st_size > 0:
        command += ["-i", str(subtitles)]
        subtitle_index = next_index

    command += ["-map", "0:v:0"]
    if audio_index is not None:
        command += ["-map", f"{audio_index}:a:0"]
    else:
        command += ["-map", "0:a?"]
    if subtitle_index is not None:
        command += ["-map", f"{subtitle_index}:s:0"]

    command += ["-c:v", "copy"]
    if audio_index is not None:
        command += ["-c:a", "aac", "-b:a", "192k"]
    else:
        command += ["-c:a", "copy"]
    if subtitle_index is not None:
        command += ["-c:s", "mov_text", "-metadata:s:s:0", "language=zho"]
    command += ["-movflags", "+faststart", str(output)]

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise PipelineMediaError((completed.stderr or "ffmpeg assembly failed")[-1600:])
    if not output.is_file() or output.stat().st_size == 0:
        raise PipelineMediaError("FFmpeg assembly produced no output")
    return {
        "status": "PASS",
        "output": _relative(project, output),
        "video": _relative(project, video),
        "audio": _relative(project, audio) if audio and audio.is_file() else "",
        "subtitles": _relative(project, subtitles) if subtitles and subtitles.is_file() else "",
        "finalizer": "ffmpeg",
    }


__all__ = ["PipelineMediaError", "assemble_final", "ensure_subtitles", "ensure_tts"]
