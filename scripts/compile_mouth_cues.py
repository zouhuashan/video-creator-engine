#!/usr/bin/env python3
"""Compile deterministic mouth cues from the local voice assignment ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _shape(index: int, total: int) -> str:
    if index == 0 or index == total - 1:
        return "rest"
    return ("wide", "smile", "o")[index % 3]


def compile_cues(project: Path) -> dict[str, Any]:
    voice_path = project / "audio" / "voice-profiles.json"
    payload = json.loads(voice_path.read_text(encoding="utf-8"))
    shots: dict[str, list[dict[str, Any]]] = {}
    for line in payload.get("line_assignments", []):
        unit_id = str(line.get("unit_id") or "")
        speaker = line.get("speaker_character_id")
        text = str(line.get("text") or "").strip()
        kind = str(line.get("kind") or "")
        if not unit_id or not text or kind not in {"DIALOGUE", "NARRATION"}:
            continue
        parts = unit_id.split("-")
        if len(parts) < 4:
            continue
        shot_id = "SHOT-" + "-".join(parts[1:])
        duration = max(1.2, min(8.0, 0.32 * len(text)))
        total = max(3, min(10, round(duration / 0.55))) if speaker else 0
        cues = []
        for index in range(total):
            start = round(index * duration / total, 3)
            end = round((index + 1) * duration / total, 3)
            cues.append({"start": start, "end": end, "mouth": _shape(index, total)})
        shots.setdefault(shot_id, []).append({"dialogue_line_id": unit_id, "kind": kind, "speaker_character_id": speaker, "text": text, "emotion": line.get("emotion") or "", "duration_seconds": duration, "mouth_cues": cues})
    timeline: list[dict[str, Any]] = []
    for shot_id, lines in shots.items():
        cursor = 0.0
        for index, line in enumerate(lines, 1):
            start = round(cursor, 3); end = round(cursor + float(line["duration_seconds"]), 3); cursor = end
            line.update({"start_seconds": start, "end_seconds": end, "subtitle": {"text": line["text"], "start_seconds": start, "end_seconds": end, "status": "PLANNED"}, "audio": {"asset_id": None, "start_seconds": start, "end_seconds": end, "status": "PLANNED"}, "cue_id": f"CUE-{shot_id}-{index:02d}"})
            timeline.append({"shot_id": shot_id, "cue_id": line["cue_id"], "dialogue_line_id": line["dialogue_line_id"], "kind": line["kind"], "start_seconds": start, "end_seconds": end, "text": line["text"], "speaker_character_id": line["speaker_character_id"], "subtitle": line["subtitle"], "audio": line["audio"], "mouth_cues": line["mouth_cues"]})
    return {"schema_version": 1, "project_id": project.name, "source": "audio/voice-profiles.json", "shots": shots, "timeline": timeline, "human_review": {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("dynamic/mouth-cues.json"))
    args = parser.parse_args()
    project = args.project_dir.expanduser().resolve()
    result = compile_cues(project)
    output = args.output if args.output.is_absolute() else project / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": output.relative_to(project).as_posix(), "shot_count": len(result["shots"]), "line_count": sum(len(v) for v in result["shots"].values())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
