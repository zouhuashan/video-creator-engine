#!/usr/bin/env python3
"""Turn scene-length drafts into 2-5 second editorial Shots without AI Video."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from scripts.cost_first_hybrid_router import load_render_profile
from scripts.novel_episode_script import load_script_package
from scripts.novel_shot_breakdown import _state, build_shot_breakdown, load_shot_breakdown, signature, validate_shot_breakdown, write_shot_breakdown

MAP_OUTPUT = Path("storyboard/modern-shot-units.json")
BACKUP_OUTPUT = Path("storyboard/shot-breakdown.before-modern.json")
MAX_SHOT_SECONDS = 5.0


class ModernShotBreakdownError(ValueError):
    pass


def _segments(units: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_duration = 0.0
    for unit in units:
        duration = max(0.3, float(unit.get("estimated_duration_seconds") or 2.0))
        kind = str(unit.get("kind") or "")
        if duration > MAX_SHOT_SECONDS:
            if current:
                groups.append(current)
                current, current_duration = [], 0.0
            parts = math.ceil(duration / MAX_SHOT_SECONDS)
            for _ in range(parts):
                groups.append([{**unit, "_shot_duration": duration / parts}])
            continue
        if current and (current_duration + duration > 4.5 or kind != current[0].get("kind")):
            groups.append(current)
            current, current_duration = [], 0.0
        current.append({**unit, "_shot_duration": duration})
        current_duration += duration
    if current:
        groups.append(current)
    return groups


def build_modern_shots(project: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    project = Path(project).resolve()
    if load_render_profile(project) != "modern_low_cost":
        raise ModernShotBreakdownError("switch project to modern_low_cost before splitting Shots")
    scripts = load_script_package(project)
    package = build_shot_breakdown(project)
    current = load_shot_breakdown(project)
    package["revision"] = int(current["revision"]) + 1
    mapping: dict[str, dict[str, Any]] = {}
    scene_index = {scene["id"]: scene for episode in scripts["episode_scripts"] for scene in episode["scenes"]}
    total = 0
    for breakdown in package["scene_breakdowns"]:
        scene = scene_index[breakdown["scene_id"]]
        groups = _segments(scene["units"])
        if not groups:
            continue
        shots = []
        for index, group in enumerate(groups, start=1):
            shot_id = f"SHOT-{scene['id']}-{index:03d}"
            kinds = {unit.get("kind") for unit in group}
            text = " ".join(str(unit.get("text") or "") for unit in group)
            if any(term in text for term in ("短信", "聊天", "来电", "转账", "新闻", "手机屏幕", "合同", "报告")):
                shot_type, framing = "INSERT", "屏幕/资料特写"
            elif "DIALOGUE" in kinds:
                shot_type, framing = ("MEDIUM", "人物半身") if index % 2 else ("CLOSEUP", "人物反应特写")
            elif "ACTION" in kinds:
                shot_type, framing = "WIDE", "动作空间全景"
            else:
                shot_type, framing = ("ESTABLISHING", "环境建立镜头") if index == 1 else ("INSERT", "细节插入镜头")
            state = _state(scene)
            duration = round(sum(float(unit["_shot_duration"]) for unit in group), 3)
            payload = {"id": shot_id, "sequence": index, "shot_type": shot_type, "framing": framing, "angle": "平视", "movement": "轻缓推移", "lens": "35mm", "duration_seconds": duration, "start_state": state, "end_state": state, "reference_ids": [], "human_review": {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}}
            payload["continuity_signature"] = signature({key: payload[key] for key in ("id", "sequence", "shot_type", "framing", "angle", "movement", "lens", "duration_seconds", "start_state", "end_state", "reference_ids")})
            shots.append(payload)
            mapping[shot_id] = {"unit_ids": list(dict.fromkeys(str(unit["id"]) for unit in group)), "text_excerpt": text[:400], "duration_seconds": duration}
        breakdown["shots"] = shots
        breakdown["shot_ids"] = [shot["id"] for shot in shots]
        total += len(shots)
    package = validate_shot_breakdown(project, package)
    shot_map = {"schema_version": 1, "script_revision": scripts["revision"], "shot_breakdown_revision": package["revision"], "shot_count": total, "shots": mapping}
    return package, shot_map


def apply_modern_shot_breakdown(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    timing_path = project / "audio/shot-timing.json"
    if timing_path.is_file():
        try:
            timing = json.loads(timing_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ModernShotBreakdownError(f"cannot read existing voice timing: {error}") from error
        if any(item.get("timing_source") == "ACTUAL_TTS" for item in timing.get("shots", []) if isinstance(item, dict)):
            raise ModernShotBreakdownError("existing Shot IDs have locked TTS timing; migrate voice alignment before replacing the breakdown")
    package, shot_map = build_modern_shots(project)
    current_path = project / "storyboard/shot-breakdown.json"
    backup = project / BACKUP_OUTPUT
    if not backup.is_file():
        backup.write_bytes(current_path.read_bytes())
    write_shot_breakdown(project, package, overwrite=True)
    target = project / MAP_OUTPUT
    target.write_text(json.dumps(shot_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"shot_count": shot_map["shot_count"], "scene_count": len(package["scene_breakdowns"]), "shot_breakdown_revision": package["revision"], "backup": BACKUP_OUTPUT.as_posix(), "map": MAP_OUTPUT.as_posix()}
