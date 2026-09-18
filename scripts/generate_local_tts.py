#!/usr/bin/env python3
"""Generate local Chinese TTS files and register them in the unified cue timeline."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.novel_anime_repository import NovelAnimeRepository


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as stream:
        return round(stream.getnframes() / max(1, stream.getframerate()), 3)


def generate(project: Path, voice: str = "Tingting", limit: int | None = None) -> dict[str, object]:
    project = project.expanduser().resolve()
    timeline_path = project / "dynamic" / "mouth-cues.json"
    payload = json.loads(timeline_path.read_text(encoding="utf-8"))
    timeline = payload.get("timeline", [])
    if limit:
        timeline = timeline[:limit]
    if shutil.which("say") is None:
        raise RuntimeError("macOS say command is required for local TTS")
    audio_dir = project / "audio" / "tts-local"
    audio_dir.mkdir(parents=True, exist_ok=True)
    repository = NovelAnimeRepository(project)
    generated = []
    for index, cue in enumerate(timeline, 1):
        text = str(cue.get("text") or "").strip()
        if not text:
            continue
        safe_id = str(cue["cue_id"]).replace("-", "_").lower()
        wav_path = audio_dir / f"{safe_id}.wav"
        with tempfile.TemporaryDirectory(prefix="local-tts-") as temporary:
            aiff_path = Path(temporary) / "voice.aiff"
            subprocess.run(["say", "-v", voice, "-o", str(aiff_path), text], check=True, capture_output=True)
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(aiff_path), "-ar", "48000", "-ac", "1", str(wav_path)], check=True, capture_output=True)
        duration = _duration(wav_path)
        scene_id = str(cue["shot_id"]).removeprefix("SHOT-").rsplit("-", 1)[0]
        asset_id = f"AST-AUDIO-JHY-{str(cue['cue_id']).replace('SHOT-', '').replace('-', '-')[:55]}"
        asset_id = asset_id[:90].rstrip("-")
        asset = repository.register_asset(asset_id, "audio", wav_path, metadata={"title": f"本地 TTS · {cue['cue_id']}", "provider": "macos_say", "voice": voice, "text": text, "duration_seconds": duration, "cue_id": cue["cue_id"]}, source_entity_ids=[scene_id])
        cue["audio"] = {"asset_id": asset["asset_id"], "path": wav_path.relative_to(project).as_posix(), "start_seconds": cue["start_seconds"], "end_seconds": cue["end_seconds"], "duration_seconds": duration, "status": "READY", "provider": "macos_say"}
        generated.append({"cue_id": cue["cue_id"], "asset_id": asset["asset_id"], "duration_seconds": duration})
    payload["timeline"] = payload.get("timeline", [])
    by_id = {item["cue_id"]: item for item in timeline}
    for item in payload["timeline"]:
        if item["cue_id"] in by_id:
            item.update(by_id[item["cue_id"]])
    payload["tts"] = {"provider": "macos_say", "voice": voice, "status": "READY", "human_review": {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None}}
    timeline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"output": timeline_path.relative_to(project).as_posix(), "generated": generated, "count": len(generated)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--voice", default="Tingting")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    print(json.dumps(generate(args.project_dir, args.voice, args.limit), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
