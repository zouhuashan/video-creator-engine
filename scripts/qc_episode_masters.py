#!/usr/bin/env python3
"""Run objective technical QC for locally assembled novel-anime episodes."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.video.video_use import _media_tool, video_use_environment


SRT_TIMING = re.compile(r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2},\d{3})")


def _seconds(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_srt(path: Path) -> list[dict[str, Any]]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip())
    entries = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        if len(lines) < 3:
            continue
        match = SRT_TIMING.fullmatch(lines[1].strip())
        if not match:
            raise ValueError(f"invalid SRT timing in {path}: {lines[1]}")
        entries.append({"start_seconds": _seconds(match.group("start")), "end_seconds": _seconds(match.group("end")), "lines": lines[2:]})
    return entries


def validate_subtitles(path: Path) -> dict[str, Any]:
    entries = parse_srt(path)
    monotonic = all(item["start_seconds"] < item["end_seconds"] for item in entries) and all(entries[index]["end_seconds"] <= entries[index + 1]["start_seconds"] + 0.002 for index in range(len(entries) - 1))
    safe_lines = all(1 <= len(item["lines"]) <= 2 and all(0 < len(line) <= 16 for line in item["lines"]) for item in entries)
    return {"status": "PASS" if entries and monotonic and safe_lines else "FAIL", "entry_count": len(entries), "monotonic": monotonic, "portrait_safe_lines": safe_lines, "max_line_chars": max((len(line) for item in entries for line in item["lines"]), default=0)}


def _probe(path: Path) -> dict[str, Any]:
    ffprobe = _media_tool("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is unavailable")
    command = [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,pix_fmt,avg_frame_rate", "-show_entries", "format=duration", "-of", "json", str(path)]
    return json.loads(subprocess.run(command, check=True, text=True, capture_output=True, env=video_use_environment()).stdout)


def _decode_ok(path: Path) -> bool:
    ffmpeg = _media_tool("ffmpeg")
    return bool(ffmpeg) and subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, env=video_use_environment()).returncode == 0


def _audio_max_volume(path: Path) -> float | None:
    ffmpeg = _media_tool("ffmpeg")
    if not ffmpeg:
        return None
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], text=True, capture_output=True, env=video_use_environment())
    match = re.search(r"max_volume:\s*(-?(?:\d+(?:\.\d+)?|inf)) dB", result.stderr)
    if not match or match.group(1) == "-inf":
        return None
    return float(match.group(1))


def _subtitle_burn_difference(clean: Path, final: Path, at_seconds: float) -> float:
    ffmpeg = _media_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is unavailable")
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        frames = []
        for index, source in enumerate((clean, final)):
            output = directory_path / f"frame-{index}.png"
            subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", f"{at_seconds:.3f}", "-i", str(source), "-frames:v", "1", str(output)], check=True, capture_output=True, env=video_use_environment())
            frames.append(Image.open(output).convert("RGB"))
        width, height = frames[0].size
        crop = (0, int(height * 0.60), width, int(height * 0.99))
        difference = ImageChops.difference(frames[0].crop(crop), frames[1].crop(crop))
        return round(sum(ImageStat.Stat(difference).mean) / 3, 3)


def _fps(value: str) -> float:
    numerator, denominator = value.split("/", 1)
    return float(numerator) / max(float(denominator), 1.0)


def qc_episode(project: Path, episode: dict[str, Any]) -> dict[str, Any]:
    final = project / str(episode["output"])
    clean = project / str(episode["clean_output"])
    subtitle = project / str(episode["subtitle"])
    subtitle_result = validate_subtitles(subtitle)
    probe = _probe(final)
    streams = probe.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    actual_duration = float(probe.get("format", {}).get("duration") or 0.0)
    format_ok = video.get("codec_name") == "h264" and video.get("width") == 1080 and video.get("height") == 1920 and video.get("pix_fmt") == "yuv420p" and abs(_fps(str(video.get("avg_frame_rate") or "0/1")) - 24.0) < 0.05
    duration_ok = abs(actual_duration - float(episode.get("duration_seconds") or 0.0)) <= 0.10
    max_volume = _audio_max_volume(final)
    first_subtitle = parse_srt(subtitle)[0]
    burn_difference = _subtitle_burn_difference(clean, final, (first_subtitle["start_seconds"] + first_subtitle["end_seconds"]) / 2)
    checks = {
        "full_decode": "PASS" if _decode_ok(final) else "FAIL",
        "video_format": "PASS" if format_ok else "FAIL",
        "audio_stream": "PASS" if audio.get("codec_name") == "aac" and max_volume is not None and max_volume > -50 else "FAIL",
        "duration": "PASS" if duration_ok else "FAIL",
        "subtitle_timing_and_safe_area": subtitle_result["status"],
        "subtitle_burn_detected": "PASS" if burn_difference >= 1.5 else "FAIL",
    }
    return {
        "episode_id": episode["episode_id"],
        "status": "PASS" if all(value == "PASS" for value in checks.values()) else "FAIL",
        "checks": checks,
        "metrics": {
            "duration_seconds": round(actual_duration, 3),
            "duration_delta_seconds": round(actual_duration - float(episode.get("duration_seconds") or 0.0), 3),
            "video_codec": video.get("codec_name"),
            "resolution": f"{video.get('width')}x{video.get('height')}",
            "fps": round(_fps(str(video.get("avg_frame_rate") or "0/1")), 3),
            "audio_codec": audio.get("codec_name"),
            "audio_max_volume_db": max_volume,
            "subtitle_entry_count": subtitle_result["entry_count"],
            "subtitle_max_line_chars": subtitle_result["max_line_chars"],
            "subtitle_burn_difference": burn_difference,
        },
    }


def run(project: Path) -> dict[str, Any]:
    project = project.expanduser().resolve()
    manifest_path = project / "renders" / "episodes" / "episode-masters.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    episodes = [qc_episode(project, episode) for episode in manifest.get("episodes", [])]
    report = {
        "schema_version": 1,
        "project_id": project.name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "PASS" if len(episodes) == 5 and all(item["status"] == "PASS" for item in episodes) else "FAIL",
        "episode_count": len(episodes),
        "passed_episode_count": sum(item["status"] == "PASS" for item in episodes),
        "episodes": episodes,
        "human_review": {"required": True, "status": "PENDING"},
    }
    output = project / "renders" / "episodes" / "episode-technical-qc.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    result = run(args.project_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
