#!/usr/bin/env python3
"""Voice-first timing layer for novel-anime production.

This module turns known script dialogue/narration into a deterministic timing
plan before expensive video generation.  It never uses ASR: subtitles are
written directly from the source script, while local macOS TTS is used only as
a zero-cost timing preview.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

from adapters.tts.macos_say import MacOSSayTTS
from adapters.tts.base import TTSProviderError
from scripts.novel_episode_script import load_script_package
from scripts.novel_shot_breakdown import load_shot_breakdown
from scripts.novel_voice_profiles import load_voice_profiles


OUTPUT = Path("audio/voice-timeline.json")
SHOT_TIMING_OUTPUT = Path("audio/shot-timing.json")
SUBTITLE_DIR = Path("subtitles/voice-timeline")


class VoiceTimelineError(RuntimeError):
    pass


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as stream:
            return round(stream.getnframes() / max(1, stream.getframerate()), 3)
    except (wave.Error, OSError) as error:
        raise VoiceTimelineError(f"cannot read generated timing audio: {path.name}") from error


def _srt_time(seconds: float) -> str:
    millis = max(0, round(float(seconds) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _ass_time(seconds: float) -> str:
    centis = max(0, round(float(seconds) * 100))
    hours, centis = divmod(centis, 360_000)
    minutes, centis = divmod(centis, 6_000)
    secs, centis = divmod(centis, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _ass_escape(text: str) -> str:
    return str(text).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _script_indexes(project: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    scripts = load_script_package(project)
    unit_index: dict[str, dict[str, Any]] = {}
    unit_scene: dict[str, str] = {}
    for episode in scripts["episode_scripts"]:
        for scene in episode["scenes"]:
            for unit in scene["units"]:
                unit_index[str(unit["id"])] = unit
                unit_scene[str(unit["id"])] = str(scene["id"])
    return unit_index, unit_scene


def _scene_shots(project: Path) -> dict[str, str]:
    package = load_shot_breakdown(project)
    result: dict[str, str] = {}
    for scene in package["scene_breakdowns"]:
        shots = scene.get("shots") or []
        if shots:
            result[str(scene["scene_id"])] = str(shots[0]["id"])
    return result


def _load_existing(project: Path) -> dict[str, dict[str, Any]]:
    path = project / OUTPUT
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        str(line.get("unit_id")): line
        for episode in payload.get("episodes", [])
        if isinstance(episode, dict)
        for line in episode.get("lines", [])
        if isinstance(line, dict) and line.get("unit_id")
    }


def _reflow_episode(episode: dict[str, Any]) -> None:
    cursor = 0.0
    for line in episode["lines"]:
        duration = max(
            0.35,
            float(line.get("audio_duration_seconds") or line.get("estimated_duration_seconds") or 1.0),
        )
        line["start_seconds"] = round(cursor, 3)
        line["duration_seconds"] = round(duration, 3)
        line["end_seconds"] = round(cursor + duration, 3)
        cursor += duration
    episode["duration_seconds"] = round(cursor, 3)
    episode["generated_line_count"] = sum(1 for line in episode["lines"] if line.get("status") == "READY")
    episode["line_count"] = len(episode["lines"])
    episode["status"] = "READY" if episode["lines"] and episode["generated_line_count"] == len(episode["lines"]) else ("EMPTY" if not episode["lines"] else "PLANNED")


def _shot_timing(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for episode in episodes:
        for line in episode["lines"]:
            shot_id = str(line.get("shot_id") or "")
            if not shot_id:
                continue
            key = (str(episode["episode_id"]), shot_id)
            item = grouped.setdefault(key, {
                "episode_id": str(episode["episode_id"]),
                "shot_id": shot_id,
                "scene_id": str(line.get("scene_id") or ""),
                "line_ids": [],
                "spoken_duration_seconds": 0.0,
            })
            item["line_ids"].append(str(line["unit_id"]))
            item["spoken_duration_seconds"] += float(line["duration_seconds"])
    result = []
    for item in grouped.values():
        spoken = round(float(item["spoken_duration_seconds"]), 3)
        result.append({
            **item,
            "spoken_duration_seconds": spoken,
            "recommended_duration_seconds": round(max(1.0, spoken + 0.6), 3),
            "timing_source": "ACTUAL_TTS" if all(
                line.get("status") == "READY"
                for episode in episodes if episode["episode_id"] == item["episode_id"]
                for line in episode["lines"] if line["unit_id"] in item["line_ids"]
            ) else "SCRIPT_ESTIMATE",
        })
    return sorted(result, key=lambda item: (item["episode_id"], item["shot_id"]))


def build_timeline(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    voices = load_voice_profiles(project)
    unit_index, unit_scene = _script_indexes(project)
    scene_shot = _scene_shots(project)
    existing = _load_existing(project)

    by_episode: dict[str, list[dict[str, Any]]] = {}
    for assignment in voices["line_assignments"]:
        unit_id = str(assignment["unit_id"])
        unit = unit_index.get(unit_id, {})
        scene_id = unit_scene.get(unit_id, "")
        old = existing.get(unit_id, {})
        line = {
            "unit_id": unit_id,
            "episode_id": str(assignment["episode_id"]),
            "kind": str(assignment["kind"]),
            "speaker_character_id": assignment.get("speaker_character_id"),
            "profile_id": assignment.get("profile_id"),
            "text": str(assignment["text"]),
            "emotion": str(assignment.get("emotion") or ""),
            "scene_id": scene_id,
            "shot_id": scene_shot.get(scene_id, ""),
            "estimated_duration_seconds": round(max(0.35, float(unit.get("estimated_duration_seconds") or 1.0)), 3),
            "audio_path": str(old.get("audio_path") or ""),
            "audio_duration_seconds": float(old.get("audio_duration_seconds") or 0.0),
            "provider": str(old.get("provider") or ""),
            "voice": str(old.get("voice") or ""),
            "status": "READY" if old.get("audio_path") and (project / str(old.get("audio_path"))).is_file() else "PLANNED",
        }
        by_episode.setdefault(line["episode_id"], []).append(line)

    episodes = []
    for episode_id, lines in sorted(by_episode.items()):
        episode = {
            "episode_id": episode_id,
            "provider": "macos_say",
            "voice": "",
            "subtitle_source": "SCRIPT_TTS_TIMING",
            "asr_round_trip": False,
            "lines": lines,
        }
        _reflow_episode(episode)
        episodes.append(episode)

    payload = {
        "schema_version": 1,
        "project_id": project.name,
        "mode": "TIMING_PREVIEW",
        "provider": "macos_say",
        "billable": False,
        "asr_round_trip": False,
        "episodes": episodes,
    }
    payload["shot_timing"] = _shot_timing(episodes)
    return payload


def _write_subtitles(project: Path, episode: dict[str, Any]) -> tuple[str, str]:
    output_dir = project / SUBTITLE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = str(episode["episode_id"]).lower()
    srt = output_dir / f"{stem}.srt"
    ass = output_dir / f"{stem}.ass"

    blocks = []
    for index, line in enumerate(episode["lines"], 1):
        blocks.extend([
            str(index),
            f"{_srt_time(line['start_seconds'])} --> {_srt_time(line['end_seconds'])}",
            str(line["text"]),
            "",
        ])
    srt.write_text("\n".join(blocks), encoding="utf-8")

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,PingFang SC,54,&H00FFFFFF,&H000000FF,&H00101010,&H70000000,0,0,0,0,100,100,0,0,1,3,1,2,72,72,150,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events = [
        f"Dialogue: 0,{_ass_time(line['start_seconds'])},{_ass_time(line['end_seconds'])},Default,,0,0,0,,{_ass_escape(line['text'])}"
        for line in episode["lines"]
    ]
    ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return srt.relative_to(project).as_posix(), ass.relative_to(project).as_posix()


def _synthesize_line(project: Path, line: dict[str, Any], voice: str) -> None:
    if shutil.which("ffmpeg") is None:
        raise VoiceTimelineError("本地 Timing Voice 需要 FFmpeg")
    provider = MacOSSayTTS()
    try:
        result = provider.synthesize(str(line["text"]), voice=voice, speed=1.0)
    except TTSProviderError as error:
        raise VoiceTimelineError(str(error)) from error

    directory = project / "audio" / "timing-preview" / str(line["episode_id"]).lower()
    directory.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(line["unit_id"])).strip("-._") or "line"
    source = directory / f"{safe}.aiff"
    output = directory / f"{safe}.wav"
    source.write_bytes(result.audio)
    completed = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-ar", "48000", "-ac", "1", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        source.unlink(missing_ok=True)
    except OSError:
        pass
    if completed.returncode != 0 or not output.is_file():
        raise VoiceTimelineError((completed.stderr or "FFmpeg failed to convert local timing voice")[-1200:])
    line["audio_path"] = output.relative_to(project).as_posix()
    line["audio_duration_seconds"] = _duration(output)
    line["provider"] = result.provider
    line["voice"] = voice
    line["status"] = "READY"


def generate_preview(project: Path, episode_id: str, *, voice: str = "Tingting") -> dict[str, Any]:
    project = Path(project).resolve()
    episode_id = str(episode_id or "").strip().upper()
    if not re.fullmatch(r"S\d{2}E\d{3}", episode_id):
        raise VoiceTimelineError("episode_id 格式必须为 S01E001")
    voice = str(voice or "Tingting").strip()
    if not voice or len(voice) > 80 or any(char in voice for char in "\r\n/\\"):
        raise VoiceTimelineError("本地 Timing Voice 名称无效")

    payload = build_timeline(project)
    episode = next((item for item in payload["episodes"] if item["episode_id"] == episode_id), None)
    if episode is None:
        raise VoiceTimelineError("当前项目没有该集的对白/旁白时间轴")
    for line in episode["lines"]:
        _synthesize_line(project, line, voice)
    episode["voice"] = voice
    _reflow_episode(episode)
    episode["srt_path"], episode["ass_path"] = _write_subtitles(project, episode)
    payload["shot_timing"] = _shot_timing(payload["episodes"])
    _atomic_json(project / OUTPUT, payload)
    _atomic_json(project / SHOT_TIMING_OUTPUT, {
        "schema_version": 1,
        "project_id": project.name,
        "source": "VOICE_TIMELINE",
        "shots": payload["shot_timing"],
    })
    return payload


def inventory(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    payload = build_timeline(project)
    path = project / OUTPUT
    if path.is_file():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = {}
        stored_episodes = {str(item.get("episode_id")): item for item in stored.get("episodes", []) if isinstance(item, dict)}
        for episode in payload["episodes"]:
            old = stored_episodes.get(str(episode["episode_id"]), {})
            if old.get("srt_path") and (project / str(old["srt_path"])).is_file():
                episode["srt_path"] = str(old["srt_path"])
            if old.get("ass_path") and (project / str(old["ass_path"])).is_file():
                episode["ass_path"] = str(old["ass_path"])
            if old.get("voice"):
                episode["voice"] = str(old["voice"])
    return payload


__all__ = ["VoiceTimelineError", "build_timeline", "generate_preview", "inventory"]
