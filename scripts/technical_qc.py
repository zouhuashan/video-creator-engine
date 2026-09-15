#!/usr/bin/env python3
"""Run reproducible technical quality checks on a rendered video."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "technical-qc.json"
sys.path.insert(0, str(ROOT))

from adapters.video.video_use import _media_tool, video_use_environment  # noqa: E402


class TechnicalQCError(ValueError):
    """Raised when technical QC cannot produce a trustworthy result."""


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TechnicalQCError(f"invalid technical QC config: {error}") from error
    if config.get("schema_version") != 1:
        raise TechnicalQCError("unsupported technical QC config")
    for key in ("output", "thresholds", "subtitle_safe_area", "reserved_ui_zones"):
        if key not in config:
            raise TechnicalQCError(f"technical QC config is missing {key}")
    return config


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=video_use_environment(),
        )
    except OSError as error:
        raise TechnicalQCError(f"cannot run media inspection tool: {command[0]}") from error


def probe_media(path: Path) -> dict[str, Any]:
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise TechnicalQCError(f"final video does not exist or is empty: {path}")
    ffprobe = _media_tool("ffprobe")
    if ffprobe is None:
        raise TechnicalQCError("ffprobe is required for technical QC")
    result = _run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    if result.returncode != 0:
        raise TechnicalQCError("ffprobe could not read the final video")
    try:
        payload = json.loads(result.stdout)
        streams = payload["streams"]
        video = next(item for item in streams if item.get("codec_type") == "video")
        audio = next(item for item in streams if item.get("codec_type") == "audio")
        fps = float(Fraction(video.get("avg_frame_rate") or video["r_frame_rate"]))
        format_duration = float(payload["format"]["duration"])
        return {
            "width": int(video["width"]),
            "height": int(video["height"]),
            "fps": fps,
            "video_codec": str(video["codec_name"]),
            "audio_codec": str(audio["codec_name"]),
            "duration_seconds": format_duration,
            "video_start_seconds": float(video.get("start_time", 0)),
            "audio_start_seconds": float(audio.get("start_time", 0)),
            "video_duration_seconds": float(video.get("duration", format_duration)),
            "audio_duration_seconds": float(audio.get("duration", format_duration)),
            "container": str(payload["format"].get("format_name", "")),
            "size_bytes": path.stat().st_size,
        }
    except (KeyError, StopIteration, TypeError, ValueError, ZeroDivisionError) as error:
        raise TechnicalQCError("final video is missing valid video or audio stream metadata") from error


def scan_media(path: Path) -> dict[str, Any]:
    ffmpeg = _media_tool("ffmpeg")
    if ffmpeg is None:
        raise TechnicalQCError("ffmpeg is required for technical QC")
    thresholds = load_config()["thresholds"]
    video_filter = (
        f"blackdetect=d={thresholds['max_black_frame_seconds']}:pix_th=0.10,"
        f"freezedetect=n=-50dB:d={thresholds['max_frozen_frame_seconds']}"
    )
    audio_filter = (
        f"silencedetect=n=-50dB:d={thresholds['max_silence_seconds']},volumedetect"
    )
    result = _run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(Path(path).resolve()), "-vf", video_filter,
         "-af", audio_filter, "-f", "null", "-"]
    )
    output = result.stderr
    black = [float(value) for value in re.findall(r"black_duration:([0-9.]+)", output)]
    frozen = [float(value) for value in re.findall(r"freeze_duration: ([0-9.]+)", output)]
    silence_starts = [float(value) for value in re.findall(r"silence_start: ([0-9.]+)", output)]
    silence_ends = [float(value) for value in re.findall(r"silence_end: [0-9.]+ \| silence_duration: ([0-9.]+)", output)]
    peak = re.search(r"max_volume: (-?(?:inf|[0-9.]+)) dB", output)
    peak_db = float("-inf") if peak and peak.group(1) == "-inf" else float(peak.group(1)) if peak else None
    return {
        "decode_exit_code": result.returncode,
        "black_durations": black,
        "frozen_durations": frozen,
        "silence_durations": silence_ends,
        "unclosed_silence_count": max(0, len(silence_starts) - len(silence_ends)),
        "max_volume_db": peak_db,
    }


def load_subtitle_layout(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TechnicalQCError(f"invalid subtitle layout: {error}") from error
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cues"), list):
        raise TechnicalQCError("subtitle layout must contain schema_version 1 and cues")
    return payload


def _valid_box(box: Any) -> bool:
    if not isinstance(box, dict) or set(box) != {"x", "y", "width", "height"}:
        return False
    try:
        x, y, width, height = (float(box[key]) for key in ("x", "y", "width", "height"))
    except (TypeError, ValueError):
        return False
    return x >= 0 and y >= 0 and width > 0 and height > 0 and x + width <= 1 and y + height <= 1


def _inside(inner: dict[str, Any], outer: dict[str, Any]) -> bool:
    return (
        inner["x"] >= outer["x"] and inner["y"] >= outer["y"]
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"]
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"]
    )


def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return not (
        left["x"] + left["width"] <= right["x"] or right["x"] + right["width"] <= left["x"]
        or left["y"] + left["height"] <= right["y"] or right["y"] + right["height"] <= left["y"]
    )


def evaluate_technical_qc(
    metadata: dict[str, Any], scan: dict[str, Any], subtitle_layout: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active = config or load_config()
    expected = active["output"]
    limits = active["thresholds"]
    cues = subtitle_layout.get("cues", [])
    malformed = [cue.get("cue_id", "unknown") for cue in cues if not _valid_box(cue.get("box"))]
    valid_cues = [(cue.get("cue_id", "unknown"), cue["box"]) for cue in cues if _valid_box(cue.get("box"))]
    outside = [cue_id for cue_id, box in valid_cues if not _inside(box, active["subtitle_safe_area"])]
    occluded = [
        cue_id for cue_id, box in valid_cues
        if any(_overlaps(box, zone) for zone in active["reserved_ui_zones"])
    ]
    try:
        width, height = int(metadata["width"]), int(metadata["height"])
        checks = {
            "resolution": width == expected["width"] and height == expected["height"],
            "aspect_ratio": width * 16 == height * 9,
            "fps": abs(float(metadata["fps"]) - expected["fps"]) <= limits["fps_tolerance"],
            "codec": metadata["video_codec"] == expected["video_codec"] and metadata["audio_codec"] == expected["audio_codec"],
            "duration": expected["duration_seconds"]["min"] <= float(metadata["duration_seconds"]) <= expected["duration_seconds"]["max"],
            "black_frames": max(scan.get("black_durations") or [0]) <= limits["max_black_frame_seconds"],
            "frozen_frames": max(scan.get("frozen_durations") or [0]) <= limits["max_frozen_frame_seconds"],
            "silence": max(scan.get("silence_durations") or [0]) <= limits["max_silence_seconds"] and scan.get("unclosed_silence_count", 0) == 0,
            "clipping": scan.get("max_volume_db") is not None and scan["max_volume_db"] < limits["clipping_peak_db"],
            "audio_video_sync": (
                abs(float(metadata["audio_start_seconds"]) - float(metadata["video_start_seconds"])) <= limits["max_audio_video_offset_seconds"]
                and abs(float(metadata["audio_duration_seconds"]) - float(metadata["video_duration_seconds"])) <= limits["max_audio_video_duration_difference_seconds"]
            ),
            "subtitle_bounds": bool(cues) and not malformed and not outside,
            "subtitle_occlusion": bool(cues) and not malformed and not occluded,
            "encoding_success": scan.get("decode_exit_code") == 0,
            "file_integrity": int(metadata.get("size_bytes", 0)) > 0 and scan.get("decode_exit_code") == 0,
        }
    except (KeyError, TypeError, ValueError) as error:
        raise TechnicalQCError("technical QC evidence is incomplete or invalid") from error
    details = {
        "black_durations": scan.get("black_durations", []),
        "frozen_durations": scan.get("frozen_durations", []),
        "silence_durations": scan.get("silence_durations", []),
        "max_volume_db": scan.get("max_volume_db"),
        "malformed_subtitle_cues": malformed,
        "out_of_bounds_subtitle_cues": outside,
        "occluded_subtitle_cues": occluded,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {"schema_version": 1, "status": "PASS" if not failed else "FAIL", "checks": checks,
            "failed_checks": failed, "metadata": metadata, "evidence": details}


def run_project_technical_qc(project_dir: Path, video: str = "final.mp4", layout: str = "subtitle-layout.json") -> dict[str, Any]:
    project_dir = Path(project_dir).resolve()
    report = evaluate_technical_qc(
        probe_media(project_dir / video), scan_media(project_dir / video),
        load_subtitle_layout(project_dir / layout),
    )
    report["video"] = video
    report["subtitle_layout"] = layout
    output = project_dir / "qc" / "technical-qc.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["output"] = str(output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--video", default="final.mp4")
    parser.add_argument("--layout", default="subtitle-layout.json")
    args = parser.parse_args()
    try:
        result = run_project_technical_qc(args.project_dir, args.video, args.layout)
    except TechnicalQCError as error:
        print(f"technical_qc: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
