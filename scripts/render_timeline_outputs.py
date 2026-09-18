#!/usr/bin/env python3
"""Render per-shot dialogue mixes and SRT subtitles from the unified cue timeline."""

from __future__ import annotations

import argparse
import json
import wave
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.novel_anime_repository import NovelAnimeRepository


def _srt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def render(project: Path, limit: int | None = None) -> dict[str, object]:
    project = project.expanduser().resolve()
    timeline_path = project / "dynamic" / "mouth-cues.json"
    payload = json.loads(timeline_path.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in payload.get("timeline", []):
        if item.get("audio", {}).get("asset_id"):
            grouped.setdefault(str(item["shot_id"]), []).append(item)
    if limit:
        grouped = dict(list(grouped.items())[:limit])
    output_dir = project / "audio" / "timeline-mix"
    subtitle_dir = project / "subtitles" / "timeline"
    output_dir.mkdir(parents=True, exist_ok=True); subtitle_dir.mkdir(parents=True, exist_ok=True)
    repository = NovelAnimeRepository(project)
    generated = []
    for shot_id, cues in grouped.items():
        total = max(float(item["end_seconds"]) for item in cues)
        rate, channels, width = 48000, 1, 2
        buffer = bytearray(round(total * rate) * width * channels)
        srt_lines = []
        source_ids = []
        for index, item in enumerate(cues, 1):
            audio_path = project / str(item["audio"]["path"])
            with wave.open(str(audio_path), "rb") as stream:
                raw = stream.readframes(stream.getnframes())
                rate, channels, width = stream.getframerate(), stream.getnchannels(), stream.getsampwidth()
            start_frame = round(float(item["start_seconds"]) * rate)
            destination = start_frame * channels * width
            available = max(0, len(buffer) - destination)
            buffer[destination:destination + min(len(raw), available)] = raw[:available]
            srt_lines.extend([str(index), f"{_srt_time(float(item['start_seconds']))} --> {_srt_time(float(item['end_seconds']))}", str(item["text"]), ""])
            source_ids.append(str(item["audio"]["asset_id"]))
        stem = shot_id.lower()
        wav_path = output_dir / f"{stem}.wav"; srt_path = subtitle_dir / f"{stem}.srt"
        with wave.open(str(wav_path), "wb") as stream:
            stream.setnchannels(channels); stream.setsampwidth(width); stream.setframerate(rate); stream.writeframes(bytes(buffer))
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        scene_id = shot_id.removeprefix("SHOT-").rsplit("-", 1)[0]
        mix_asset = repository.register_asset(f"AST-AUDIO-MIX-JHY-{stem.upper()}", "audio", wav_path, metadata={"title": f"对白混音 · {shot_id}", "provider": "local_timeline_mix", "duration_seconds": total}, source_entity_ids=source_ids + [scene_id])
        subtitle_asset = repository.register_asset(f"AST-SUBTITLE-JHY-{stem.upper()}", "subtitle", srt_path, metadata={"title": f"字幕 · {shot_id}", "provider": "local_timeline_srt"}, source_entity_ids=source_ids + [scene_id])
        for item in cues:
            item["audio"]["mix_asset_id"] = mix_asset["asset_id"]; item["subtitle_asset_id"] = subtitle_asset["asset_id"]
        generated.append({"shot_id": shot_id, "mix_asset_id": mix_asset["asset_id"], "subtitle_asset_id": subtitle_asset["asset_id"], "duration_seconds": total})
    timeline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"count": len(generated), "generated": generated}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("project_dir", type=Path); parser.add_argument("--limit", type=int); args = parser.parse_args()
    print(json.dumps(render(args.project_dir, args.limit), ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
