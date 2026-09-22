#!/usr/bin/env python3
"""Final voice locks and local final-mix assembly for novel-anime production.

P33 establishes timing with zero-cost local speech. This module keeps that
timing immutable while allowing billable final TTS to replace the temporary
voice. Final TTS audio is time-conformed to the approved Voice Timeline before
mixing, so a provider change never silently changes shot timing.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from adapters.tts import FishAudioTTS, TTSProviderError
from scripts.novel_story_bible import load_bible
from scripts.novel_voice_profiles import load_voice_profiles


LOCKS_PATH = Path("audio/voice-locks.json")
TIMELINE_PATH = Path("audio/voice-timeline.json")
FINAL_VOICE_ROOT = Path("audio/final-voice")
FINAL_MIX_ROOT = Path("audio/final-mix")
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".aif", ".aiff", ".flac"}


class FinalAudioError(RuntimeError):
    pass


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-._") or "item"


def _media_duration(path: Path) -> float:
    if shutil.which("ffprobe") is None:
        raise FinalAudioError("Final Voice / Mix 需要 FFprobe")
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise FinalAudioError((completed.stderr or f"cannot probe {path.name}")[-1200:])
    try:
        return round(float(completed.stdout.strip()), 3)
    except ValueError as error:
        raise FinalAudioError(f"cannot read audio duration: {path.name}") from error


def _load_timeline(project: Path) -> dict[str, Any]:
    path = project / TIMELINE_PATH
    if not path.is_file():
        raise FinalAudioError("请先在 P33 生成 Timing Voice")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FinalAudioError("voice-timeline.json 无法读取") from error
    if not isinstance(payload, dict):
        raise FinalAudioError("voice-timeline.json 格式无效")
    return payload


def _character_names(project: Path) -> dict[str, str]:
    try:
        bible = load_bible(project)
    except (ValueError, OSError):
        return {}
    return {
        str(item.get("id") or ""): str(item.get("name") or item.get("id") or "")
        for item in bible.get("characters", [])
        if isinstance(item, dict)
    }


def _default_locks(project: Path) -> dict[str, Any]:
    voices = load_voice_profiles(project)
    names = _character_names(project)
    characters = []
    for profile in voices.get("profiles", []):
        character_id = str(profile.get("character_id") or "")
        if not character_id:
            continue
        characters.append({
            "character_id": character_id,
            "character_name": names.get(character_id, character_id),
            "provider": "fish_audio",
            "voice_id": "",
            "speed": float(profile.get("speed") or 1.0),
            "emotion_default": "",
            "status": "UNLOCKED",
        })
    return {
        "schema_version": 1,
        "provider_policy": "EXPLICIT_LOCK_ONLY",
        "narrator": {
            "character_id": "NARRATOR",
            "character_name": "旁白",
            "provider": "fish_audio",
            "voice_id": "",
            "speed": 1.0,
            "emotion_default": "calm",
            "status": "UNLOCKED",
        },
        "characters": characters,
    }


def load_voice_locks(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    defaults = _default_locks(project)
    path = project / LOCKS_PATH
    if not path.is_file():
        return defaults
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(stored, dict):
        return defaults

    by_id = {
        str(item.get("character_id") or ""): item
        for item in stored.get("characters", [])
        if isinstance(item, dict)
    }
    characters = []
    for default in defaults["characters"]:
        item = {**default, **by_id.get(default["character_id"], {})}
        item["status"] = "LOCKED" if str(item.get("voice_id") or "").strip() else "UNLOCKED"
        characters.append(item)

    narrator = {**defaults["narrator"], **(stored.get("narrator") if isinstance(stored.get("narrator"), dict) else {})}
    narrator["status"] = "LOCKED" if str(narrator.get("voice_id") or "").strip() else "UNLOCKED"
    return {
        "schema_version": 1,
        "provider_policy": "EXPLICIT_LOCK_ONLY",
        "narrator": narrator,
        "characters": characters,
    }


def save_voice_lock(
    project: Path,
    *,
    character_id: str,
    voice_id: str,
    speed: float = 1.0,
    emotion_default: str = "",
    provider: str = "fish_audio",
) -> dict[str, Any]:
    project = Path(project).resolve()
    character_id = str(character_id or "").strip()
    voice_id = str(voice_id or "").strip()
    provider = str(provider or "fish_audio").strip().lower()
    if provider != "fish_audio":
        raise FinalAudioError("当前 Final Voice 首个正式 Provider 固定为 fish_audio")
    if not character_id:
        raise FinalAudioError("character_id is required")
    if len(voice_id) > 256 or any(char in voice_id for char in "\r\n/\\"):
        raise FinalAudioError("Fish Audio voice_id 无效")
    if isinstance(speed, bool) or not 0.5 <= float(speed) <= 2.0:
        raise FinalAudioError("speed must be between 0.5 and 2.0")
    emotion_default = str(emotion_default or "").strip()
    if any(char in emotion_default for char in "[]\r\n"):
        raise FinalAudioError("emotion_default 必须是纯文本")

    locks = load_voice_locks(project)
    if character_id == "NARRATOR":
        target = locks["narrator"]
    else:
        target = next((item for item in locks["characters"] if item["character_id"] == character_id), None)
        if target is None:
            raise FinalAudioError("character_id 不存在于当前 voice profiles")
    target.update({
        "provider": provider,
        "voice_id": voice_id,
        "speed": float(speed),
        "emotion_default": emotion_default,
        "status": "LOCKED" if voice_id else "UNLOCKED",
    })
    _atomic_json(project / LOCKS_PATH, locks)
    return locks


def _line_lock(locks: dict[str, Any], line: dict[str, Any]) -> dict[str, Any]:
    if str(line.get("kind") or "") == "NARRATION":
        return locks["narrator"]
    character_id = str(line.get("speaker_character_id") or "")
    lock = next((item for item in locks["characters"] if item["character_id"] == character_id), None)
    if lock is None:
        raise FinalAudioError(f"找不到角色声线锁：{character_id or 'UNKNOWN'}")
    return lock


def _atempo_chain(ratio: float) -> str:
    if not math.isfinite(ratio) or ratio <= 0:
        raise FinalAudioError("invalid TTS duration ratio")
    factors: list[float] = []
    value = ratio
    while value > 2.0:
        factors.append(2.0)
        value /= 2.0
    while value < 0.5:
        factors.append(0.5)
        value /= 0.5
    factors.append(value)
    return ",".join(f"atempo={factor:.6f}" for factor in factors)


def _conform_audio(source: Path, output: Path, target_seconds: float) -> dict[str, float]:
    if shutil.which("ffmpeg") is None:
        raise FinalAudioError("Final Voice 时长对齐需要 FFmpeg")
    actual = _media_duration(source)
    target = max(0.35, float(target_seconds))
    ratio = actual / target
    output.parent.mkdir(parents=True, exist_ok=True)
    filters = f"{_atempo_chain(ratio)},apad=whole_dur={target:.3f},atrim=duration={target:.3f},asetpts=N/SR/TB"
    completed = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-vn", "-af", filters,
            "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not output.is_file():
        raise FinalAudioError((completed.stderr or "Final Voice conform failed")[-1200:])
    return {
        "source_duration_seconds": actual,
        "target_duration_seconds": round(target, 3),
        "speed_ratio": round(ratio, 5),
        "output_duration_seconds": _media_duration(output),
    }


def _episode(project: Path, episode_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    timeline = _load_timeline(project)
    episode_id = str(episode_id or "").strip().upper()
    episode = next((item for item in timeline.get("episodes", []) if item.get("episode_id") == episode_id), None)
    if not isinstance(episode, dict):
        raise FinalAudioError("episode_id 不存在于 Voice Timeline")
    if episode.get("status") != "READY":
        raise FinalAudioError("必须先完成本集 Timing Voice，才能生成正式角色配音")
    return timeline, episode


def _manifest_path(project: Path, episode_id: str) -> Path:
    return project / FINAL_VOICE_ROOT / episode_id.lower() / "manifest.json"


def _load_manifest(project: Path, episode_id: str) -> dict[str, Any]:
    path = _manifest_path(project, episode_id)
    if not path.is_file():
        return {"schema_version": 1, "episode_id": episode_id, "lines": [], "status": "NOT_RUN"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "episode_id": episode_id, "lines": [], "status": "INVALID"}
    return payload if isinstance(payload, dict) else {"schema_version": 1, "episode_id": episode_id, "lines": [], "status": "INVALID"}


def generate_final_voice_line(
    project: Path,
    episode_id: str,
    unit_id: str,
    *,
    api_key: str,
    confirm_billable: bool,
    text_upload_authorized: bool,
) -> dict[str, Any]:
    project = Path(project).resolve()
    if not confirm_billable:
        raise FinalAudioError("正式 Fish Audio 配音是计费调用，必须勾选付费确认")
    if not text_upload_authorized:
        raise FinalAudioError("必须确认允许将本句文本发送给 Fish Audio")
    if not str(api_key or "").strip():
        raise FinalAudioError("Fish Audio API Key 尚未配置")

    _, episode = _episode(project, episode_id)
    unit_id = str(unit_id or "").strip()
    line = next((item for item in episode.get("lines", []) if str(item.get("unit_id")) == unit_id), None)
    if not isinstance(line, dict):
        raise FinalAudioError("unit_id 不存在于该集 Voice Timeline")

    locks = load_voice_locks(project)
    lock = _line_lock(locks, line)
    voice_id = str(lock.get("voice_id") or "").strip()
    if not voice_id:
        raise FinalAudioError(f"{lock.get('character_name') or lock.get('character_id')} 尚未锁定 Fish Audio voice_id")

    emotion = str(line.get("emotion") or lock.get("emotion_default") or "").strip() or None
    provider = FishAudioTTS(api_key=api_key)
    try:
        synthesized = provider.synthesize(
            str(line.get("text") or ""),
            voice=voice_id,
            speed=float(lock.get("speed") or 1.0),
            emotion=emotion,
        )
    except TTSProviderError as error:
        raise FinalAudioError(str(error)) from error

    directory = project / FINAL_VOICE_ROOT / str(episode["episode_id"]).lower()
    directory.mkdir(parents=True, exist_ok=True)
    stem = _safe_id(unit_id)
    source = directory / f"{stem}.source.{synthesized.audio_format}"
    aligned = directory / f"{stem}.wav"
    source.write_bytes(synthesized.audio)
    timing = _conform_audio(source, aligned, float(line.get("duration_seconds") or 0.0))

    manifest = _load_manifest(project, str(episode["episode_id"]))
    previous = {
        str(item.get("unit_id")): item
        for item in manifest.get("lines", [])
        if isinstance(item, dict) and item.get("unit_id")
    }
    item = {
        "unit_id": unit_id,
        "kind": str(line.get("kind") or ""),
        "speaker_character_id": line.get("speaker_character_id"),
        "character_id": str(lock.get("character_id") or ""),
        "character_name": str(lock.get("character_name") or ""),
        "provider": synthesized.provider,
        "voice_id": voice_id,
        "speed": synthesized.speed,
        "emotion": synthesized.emotion or "",
        "text": str(line.get("text") or ""),
        "start_seconds": float(line.get("start_seconds") or 0.0),
        "end_seconds": float(line.get("end_seconds") or 0.0),
        "source_path": source.relative_to(project).as_posix(),
        "audio_path": aligned.relative_to(project).as_posix(),
        **timing,
        "status": "READY",
        "billable_generation": True,
    }
    previous[unit_id] = item
    ordered = [previous[str(source_line["unit_id"])] for source_line in episode["lines"] if str(source_line["unit_id"]) in previous]
    complete = len(ordered) == len(episode["lines"]) and all(entry.get("status") == "READY" for entry in ordered)
    manifest = {
        "schema_version": 1,
        "episode_id": str(episode["episode_id"]),
        "provider": "fish_audio",
        "timing_policy": "CONFORM_TO_P33_VOICE_TIMELINE",
        "line_count": len(episode["lines"]),
        "ready_line_count": len(ordered),
        "status": "READY" if complete else "PARTIAL",
        "lines": ordered,
    }
    _atomic_json(_manifest_path(project, str(episode["episode_id"])), manifest)
    return item


def generate_final_voice_episode(
    project: Path,
    episode_id: str,
    *,
    api_key: str,
    confirm_billable: bool,
    text_upload_authorized: bool,
) -> dict[str, Any]:
    project = Path(project).resolve()
    _, episode = _episode(project, episode_id)
    locks = load_voice_locks(project)
    missing = []
    for line in episode.get("lines", []):
        lock = _line_lock(locks, line)
        if not str(lock.get("voice_id") or "").strip():
            missing.append(str(lock.get("character_name") or lock.get("character_id") or "UNKNOWN"))
    if missing:
        raise FinalAudioError("以下声线尚未锁定：" + "、".join(sorted(set(missing))))
    for line in episode.get("lines", []):
        generate_final_voice_line(
            project,
            str(episode["episode_id"]),
            str(line["unit_id"]),
            api_key=api_key,
            confirm_billable=confirm_billable,
            text_upload_authorized=text_upload_authorized,
        )
    return _load_manifest(project, str(episode["episode_id"]))


def _audio_candidates(project: Path) -> dict[str, list[str]]:
    roots = {
        "bgm": ("audio/bgm", "brand/audio/bgm"),
        "ambience": ("audio/ambience", "brand/audio/ambience"),
        "sfx": ("audio/sfx", "brand/audio/sfx"),
    }
    result: dict[str, list[str]] = {}
    for kind, directories in roots.items():
        values = []
        for relative in directories:
            root = project / relative
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                    values.append(path.relative_to(project).as_posix())
        result[kind] = values
    return result


def _resolve_audio(project: Path, relative: str) -> Path | None:
    relative = str(relative or "").strip()
    if not relative:
        return None
    candidate = (project / relative).resolve()
    if project not in candidate.parents or not candidate.is_file() or candidate.suffix.lower() not in AUDIO_EXTENSIONS:
        raise FinalAudioError("选择的音频素材无效或不在当前项目内")
    return candidate


def _voice_mix_graph(lines: list[dict[str, Any]], bed_roles: list[str], duration: float) -> tuple[str, str]:
    parts = []
    delayed = []
    for index, line in enumerate(lines):
        delay = max(0, round(float(line.get("start_seconds") or 0.0) * 1000))
        label = f"v{index}"
        parts.append(f"[{index}:a]adelay={delay}|{delay},volume=1.0[{label}]")
        delayed.append(f"[{label}]")
    if len(delayed) == 1:
        parts.append(f"{delayed[0]}anull[voice]")
    else:
        parts.append(f"{''.join(delayed)}amix=inputs={len(delayed)}:duration=longest:normalize=0[voice]")

    next_input = len(lines)
    mix_inputs = ["[voice_main]"]
    parts.append("[voice]asplit=2[voice_main][voice_side]")

    if "bgm" in bed_roles:
        parts.append(
            f"[{next_input}:a]volume=0.35,atrim=duration={duration:.3f},asetpts=N/SR/TB[bgm];"
            f"[bgm][voice_side]sidechaincompress=threshold=0.035:ratio=10:attack=18:release=350:makeup=1[bgmduck]"
        )
        mix_inputs.append("[bgmduck]")
        next_input += 1
    else:
        parts.append("[voice_side]anullsink")

    if "ambience" in bed_roles:
        parts.append(f"[{next_input}:a]volume=0.18,atrim=duration={duration:.3f},asetpts=N/SR/TB[amb]")
        mix_inputs.append("[amb]")
        next_input += 1
    if "sfx" in bed_roles:
        parts.append(f"[{next_input}:a]volume=0.45,atrim=duration={duration:.3f},asetpts=N/SR/TB[sfx]")
        mix_inputs.append("[sfx]")

    parts.append(
        f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=longest:normalize=0,"
        f"loudnorm=I=-16:TP=-1:LRA=11,atrim=duration={duration:.3f}[mix]"
    )
    return ";".join(parts), "[mix]"


def mix_episode(
    project: Path,
    episode_id: str,
    *,
    bgm_path: str = "",
    ambience_path: str = "",
    sfx_path: str = "",
) -> dict[str, Any]:
    project = Path(project).resolve()
    if shutil.which("ffmpeg") is None:
        raise FinalAudioError("Final Mix 需要 FFmpeg")
    _, episode = _episode(project, episode_id)
    manifest = _load_manifest(project, str(episode["episode_id"]))
    if manifest.get("status") != "READY":
        raise FinalAudioError("必须先完成本集全部正式角色配音，才能 Final Mix")
    lines = manifest.get("lines", [])
    if not lines:
        raise FinalAudioError("Final Voice manifest 没有可混音的台词")

    voice_paths = []
    for line in lines:
        path = project / str(line.get("audio_path") or "")
        if not path.is_file():
            raise FinalAudioError(f"正式配音文件缺失：{line.get('unit_id')}")
        voice_paths.append(path)

    selected = {
        "bgm": _resolve_audio(project, bgm_path),
        "ambience": _resolve_audio(project, ambience_path),
        "sfx": _resolve_audio(project, sfx_path),
    }
    duration = max(float(episode.get("duration_seconds") or 0.0), max(float(item.get("end_seconds") or 0.0) for item in lines))
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for path in voice_paths:
        command += ["-i", str(path)]

    roles = []
    for role in ("bgm", "ambience", "sfx"):
        path = selected[role]
        if path is not None:
            command += ["-stream_loop", "-1", "-i", str(path)]
            roles.append(role)

    graph, mix_label = _voice_mix_graph(lines, roles, duration)
    output_dir = project / FINAL_MIX_ROOT
    output_dir.mkdir(parents=True, exist_ok=True)
    wav = output_dir / f"{str(episode['episode_id']).lower()}-final-mix.wav"
    m4a = output_dir / f"{str(episode['episode_id']).lower()}-final-mix.m4a"
    command += [
        "-filter_complex", graph,
        "-map", mix_label,
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(wav),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not wav.is_file():
        raise FinalAudioError((completed.stderr or "Final Mix failed")[-1600:])

    encoded = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(wav), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(m4a),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if encoded.returncode != 0 or not m4a.is_file():
        raise FinalAudioError((encoded.stderr or "AAC encode failed")[-1200:])

    result = {
        "schema_version": 1,
        "episode_id": str(episode["episode_id"]),
        "status": "READY",
        "voice_manifest": _manifest_path(project, str(episode["episode_id"])).relative_to(project).as_posix(),
        "wav_path": wav.relative_to(project).as_posix(),
        "m4a_path": m4a.relative_to(project).as_posix(),
        "duration_seconds": _media_duration(wav),
        "target_lufs": -16.0,
        "true_peak_db": -1.0,
        "dialogue_ducking": bool(selected["bgm"]),
        "ducking_profile": {
            "threshold": 0.035,
            "ratio": 10,
            "attack_ms": 18,
            "release_ms": 350,
            "bgm_volume": 0.35,
        },
        "inputs": {key: (value.relative_to(project).as_posix() if value else "") for key, value in selected.items()},
        "finalizer": "ffmpeg",
    }
    _atomic_json(output_dir / f"{str(episode['episode_id']).lower()}-final-mix.json", result)
    return result


def _audio_magic_valid(path: Path) -> bool:
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return False
    if head.startswith(b"RIFF") and len(head) >= 12 and head[8:12] == b"WAVE":
        return True
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return True
    if head.startswith(b"fLaC"):
        return True
    if head.startswith(b"FORM") and len(head) >= 12 and head[8:12] in {b"AIFF", b"AIFC"}:
        return True
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return True
    return False


def upload_audio_asset(project: Path, *, kind: str, filename: str, content: bytes) -> dict[str, Any]:
    project = Path(project).resolve()
    kind = str(kind or "").strip().lower()
    if kind not in {"bgm", "ambience", "sfx"}:
        raise FinalAudioError("audio kind 必须是 bgm / ambience / sfx")
    if not isinstance(content, (bytes, bytearray)) or not content or len(content) > 30 * 1024 * 1024:
        raise FinalAudioError("音频文件必须在 1 byte 到 30 MB 之间")
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        raise FinalAudioError("只支持 WAV / MP3 / M4A / AAC / AIFF / FLAC")
    safe_stem = _safe_id(Path(str(filename or "audio")).stem)[:80]
    directory = project / "audio" / kind
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{safe_stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{safe_stem}-{counter}{suffix}"
        counter += 1
    candidate.write_bytes(bytes(content))
    if not _audio_magic_valid(candidate):
        candidate.unlink(missing_ok=True)
        raise FinalAudioError("上传文件头不是受支持的音频格式")
    return {
        "status": "READY",
        "kind": kind,
        "path": candidate.relative_to(project).as_posix(),
        "bytes": candidate.stat().st_size,
    }


def inventory(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    locks = load_voice_locks(project)
    timeline = None
    try:
        timeline = _load_timeline(project)
    except FinalAudioError:
        timeline = {"episodes": []}

    episodes = []
    for episode in timeline.get("episodes", []):
        if not isinstance(episode, dict):
            continue
        episode_id = str(episode.get("episode_id") or "")
        manifest = _load_manifest(project, episode_id)
        final_by_id = {
            str(item.get("unit_id")): item
            for item in manifest.get("lines", [])
            if isinstance(item, dict)
        }
        lines = []
        for line in episode.get("lines", []):
            if not isinstance(line, dict):
                continue
            final = final_by_id.get(str(line.get("unit_id") or ""), {})
            lines.append({
                "unit_id": str(line.get("unit_id") or ""),
                "kind": str(line.get("kind") or ""),
                "speaker_character_id": line.get("speaker_character_id"),
                "text": str(line.get("text") or ""),
                "emotion": str(line.get("emotion") or ""),
                "start_seconds": float(line.get("start_seconds") or 0.0),
                "end_seconds": float(line.get("end_seconds") or 0.0),
                "duration_seconds": float(line.get("duration_seconds") or 0.0),
                "final_status": str(final.get("status") or "NOT_RUN"),
                "final_audio_path": str(final.get("audio_path") or ""),
                "final_provider": str(final.get("provider") or ""),
                "final_voice_id": str(final.get("voice_id") or ""),
                "source_duration_seconds": float(final.get("source_duration_seconds") or 0.0),
                "aligned_duration_seconds": float(final.get("output_duration_seconds") or 0.0),
            })
        mix_path = project / FINAL_MIX_ROOT / f"{episode_id.lower()}-final-mix.json"
        mix = {}
        if mix_path.is_file():
            try:
                value = json.loads(mix_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    mix = value
            except (OSError, json.JSONDecodeError):
                mix = {}
        episodes.append({
            "episode_id": episode_id,
            "timing_status": str(episode.get("status") or "PLANNED"),
            "duration_seconds": float(episode.get("duration_seconds") or 0.0),
            "final_voice_status": str(manifest.get("status") or "NOT_RUN"),
            "ready_line_count": int(manifest.get("ready_line_count") or 0),
            "line_count": len(lines),
            "lines": lines,
            "final_mix": mix,
        })

    return {
        "schema_version": 1,
        "project_id": project.name,
        "provider": {
            "id": "fish_audio",
            "label": "Fish Audio S2-Pro",
            "remote": True,
            "billable": True,
            "key_env": "FISH_AUDIO_API_KEY",
            "key_persistence": "PROCESS_ONLY",
        },
        "locks": locks,
        "audio_candidates": _audio_candidates(project),
        "mix_profile": {
            "target_lufs": -16.0,
            "true_peak_db": -1.0,
            "dialogue_ducking_db": -6.0,
            "ducking": "FFMPEG_SIDECHAINCOMPRESS",
        },
        "episodes": episodes,
    }


__all__ = [
    "FinalAudioError",
    "generate_final_voice_episode",
    "generate_final_voice_line",
    "inventory",
    "load_voice_locks",
    "mix_episode",
    "save_voice_lock",
    "upload_audio_asset",
]
