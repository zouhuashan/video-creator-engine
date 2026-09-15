"""Pinned video-use integration and EDL boundary validation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "video-use.json"
VIDEO_USE_DIR = ROOT / ".dependencies" / "video-use"
LOCAL_BIN_DIR = ROOT / ".dependencies" / "bin"
VIDEO_USE_CAPABILITIES = (
    "source_understanding",
    "pause_removal",
    "filler_removal",
    "crop",
    "subtitles",
    "audio_sync",
    "b_roll",
    "overlay",
    "self_evaluation",
)


class VideoUseError(ValueError):
    """Raised when the video-use installation or edit boundary is invalid."""


def _media_tool(name: str) -> str | None:
    local = LOCAL_BIN_DIR / name
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which(name)


def video_use_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PATH"] = str(LOCAL_BIN_DIR) + os.pathsep + environment.get("PATH", "")
    return environment


def _expected_commit() -> str:
    try:
        manifest = json.loads((ROOT / "dependency-manifest.json").read_text(encoding="utf-8"))
        dependency = next(
            item for item in manifest["dependencies"] if item.get("name") == "video-use"
        )
        return dependency["commit"]
    except (OSError, json.JSONDecodeError, KeyError, StopIteration, TypeError) as error:
        raise VideoUseError("video-use dependency pin is missing or invalid") from error


def load_video_use_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VideoUseError(f"invalid video-use config: {error}") from error
    if config.get("schema_version") != 1 or config.get("dependency") != "video-use":
        raise VideoUseError("unsupported video-use config")
    capabilities = config.get("capabilities")
    if not isinstance(capabilities, dict) or tuple(capabilities) != VIDEO_USE_CAPABILITIES:
        raise VideoUseError("video-use config must declare all editing capabilities in order")
    rules = config.get("production_rules")
    required_rules = {
        "subtitles_last",
        "cut_on_word_boundaries",
        "cut_edge_padding_ms",
        "audio_fade_ms",
        "overlay_pts_shift",
        "transcript_cache_per_source",
        "max_self_eval_passes",
    }
    if not isinstance(rules, dict) or not required_rules.issubset(rules):
        raise VideoUseError("video-use production rules are incomplete")
    if rules["subtitles_last"] is not True or rules["audio_fade_ms"] != 30:
        raise VideoUseError("video-use subtitle order and audio fade safeguards must remain enabled")
    helpers = config.get("helpers")
    if not isinstance(helpers, dict) or "render" not in helpers or "timeline_view" not in helpers:
        raise VideoUseError("video-use helper mapping is incomplete")
    return config


def verify_video_use_installation(video_use_dir: Path = VIDEO_USE_DIR) -> dict[str, Any]:
    if _media_tool("ffmpeg") is None or _media_tool("ffprobe") is None:
        raise VideoUseError("video-use requires ffmpeg and ffprobe on PATH")
    python = video_use_dir / ".venv" / "bin" / "python"
    if not python.is_file():
        raise VideoUseError("video-use Python environment is missing; run uv sync in the pinned checkout")
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=video_use_dir,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise VideoUseError("video-use checkout is not readable") from error
    expected_commit = _expected_commit()
    if commit != expected_commit:
        raise VideoUseError(f"video-use commit mismatch: expected {expected_commit}, found {commit}")
    config = load_video_use_config()
    missing = [
        relative for relative in config["helpers"].values() if not (video_use_dir / relative).is_file()
    ]
    if missing:
        raise VideoUseError(f"video-use helper is missing: {missing[0]}")
    return {
        "status": "PASS",
        "commit": commit,
        "python": str(python),
        "capabilities": list(VIDEO_USE_CAPABILITIES),
    }


def probe_source(
    source: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    source = Path(source).resolve()
    if not source.is_file():
        raise VideoUseError(f"video source does not exist: {source}")
    try:
        completed = runner(
            [
                _media_tool("ffprobe") or "ffprobe", "-v", "error", "-show_streams", "-show_format",
                "-of", "json", str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise VideoUseError(f"cannot probe video source: {source.name}") from error
    streams = payload.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video is None:
        raise VideoUseError(f"source has no video stream: {source.name}")
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    try:
        duration = float(payload.get("format", {}).get("duration") or video.get("duration"))
        width = int(video["width"])
        height = int(video["height"])
    except (TypeError, ValueError, KeyError) as error:
        raise VideoUseError(f"source metadata is incomplete: {source.name}") from error
    return {
        "path": str(source),
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "frame_rate": video.get("avg_frame_rate") or video.get("r_frame_rate"),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name") if audio else None,
        "has_audio": audio is not None,
    }


def build_edit_plan(sources: list[Path], edit_dir: Path) -> dict[str, Any]:
    if not sources:
        raise VideoUseError("video-use edit plan requires at least one source")
    edit_dir = Path(edit_dir).resolve()
    if edit_dir.name != "edit":
        raise VideoUseError("video-use outputs must use a directory named edit")
    inventory = [probe_source(source) for source in sources]
    return {
        "engine": "video-use",
        "edit_dir": str(edit_dir),
        "inventory": inventory,
        "capabilities": list(VIDEO_USE_CAPABILITIES),
        "workflow": [
            "inventory_sources",
            "transcribe_verbatim",
            "pack_transcripts",
            "decide_word_boundary_cuts",
            "write_edl",
            "render_preview",
            "self_evaluate",
            "render_final",
        ],
    }


def _resolve(path: str, base: Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()


def validate_edl(edl: dict[str, Any], edit_dir: Path) -> dict[str, Any]:
    edit_dir = Path(edit_dir).resolve()
    if edl.get("version") != 1:
        raise VideoUseError("video-use EDL version must be 1")
    sources = edl.get("sources")
    ranges = edl.get("ranges")
    if not isinstance(sources, dict) or not sources or not isinstance(ranges, list) or not ranges:
        raise VideoUseError("video-use EDL requires sources and ranges")
    for source_id, source_path in sources.items():
        if not isinstance(source_id, str) or not source_id or not isinstance(source_path, str):
            raise VideoUseError("video-use EDL source entries are invalid")
        if not _resolve(source_path, edit_dir).is_file():
            raise VideoUseError(f"video-use EDL source is missing: {source_id}")

    total = 0.0
    for index, item in enumerate(ranges):
        if not isinstance(item, dict) or item.get("source") not in sources:
            raise VideoUseError(f"video-use EDL range {index} has an unknown source")
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError) as error:
            raise VideoUseError(f"video-use EDL range {index} has invalid timing") from error
        if start < 0 or end <= start:
            raise VideoUseError(f"video-use EDL range {index} must have start < end")
        total += end - start

    declared_total = edl.get("total_duration_s")
    if declared_total is not None:
        try:
            mismatch = abs(float(declared_total) - total) > 0.05
        except (TypeError, ValueError) as error:
            raise VideoUseError("video-use EDL total_duration_s is invalid") from error
        if mismatch:
            raise VideoUseError("video-use EDL total_duration_s does not match its ranges")
    for index, overlay in enumerate(edl.get("overlays") or []):
        try:
            start = float(overlay["start_in_output"])
            duration = float(overlay["duration"])
            file_path = _resolve(overlay["file"], edit_dir)
        except (KeyError, TypeError, ValueError) as error:
            raise VideoUseError(f"video-use overlay {index} is invalid") from error
        if start < 0 or duration <= 0 or start + duration > total + 0.05:
            raise VideoUseError(f"video-use overlay {index} exceeds the output timeline")
        if not file_path.is_file():
            raise VideoUseError(f"video-use overlay file is missing: {file_path.name}")
    return {"status": "PASS", "range_count": len(ranges), "duration_seconds": round(total, 3)}


def render_command(
    edl_path: Path,
    output_path: Path,
    *,
    preview: bool = False,
    build_subtitles: bool = True,
    video_use_dir: Path = VIDEO_USE_DIR,
) -> list[str]:
    edl_path = Path(edl_path).resolve()
    output_path = Path(output_path).resolve()
    edit_dir = edl_path.parent
    if not edl_path.is_file():
        raise VideoUseError(f"EDL does not exist: {edl_path}")
    if edit_dir.name != "edit" or output_path.parent != edit_dir:
        raise VideoUseError("video-use render output must stay beside the EDL in edit/")
    command = [
        str(video_use_dir / ".venv" / "bin" / "python"),
        str(video_use_dir / "helpers" / "render.py"),
        str(edl_path),
        "-o",
        str(output_path),
    ]
    if preview:
        command.append("--preview")
    if build_subtitles:
        command.append("--build-subtitles")
    return command


def build_self_eval_plan(edl: dict[str, Any]) -> dict[str, Any]:
    ranges = edl.get("ranges")
    if not isinstance(ranges, list) or not ranges:
        raise VideoUseError("self-evaluation requires EDL ranges")
    try:
        durations = [float(item["end"]) - float(item["start"]) for item in ranges]
    except (KeyError, TypeError, ValueError) as error:
        raise VideoUseError("self-evaluation EDL ranges have invalid timing") from error
    if any(duration <= 0 for duration in durations):
        raise VideoUseError("self-evaluation EDL ranges must have positive duration")
    total = sum(durations)
    cuts: list[float] = []
    elapsed = 0.0
    for duration in durations[:-1]:
        elapsed += duration
        cuts.append(elapsed)
    windows = [{"start": 0.0, "end": min(2.0, total), "reason": "opening"}]
    windows.extend(
        {
            "start": max(0.0, cut - 1.5),
            "end": min(total, cut + 1.5),
            "reason": "cut_boundary",
        }
        for cut in cuts
    )
    windows.append({"start": max(0.0, total - 2.0), "end": total, "reason": "closing"})
    return {"max_passes": 3, "duration_seconds": round(total, 3), "windows": windows}
