#!/usr/bin/env python3
"""Build a provider-neutral production contract for modern low-cost drama Shots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from scripts.cost_first_hybrid_router import load_plan, load_render_profile
from scripts.modern_editable_timeline import load_timeline
from scripts.novel_episode_script import load_script_package
from scripts.novel_shot_breakdown import load_shot_breakdown

OUTPUT = Path("production/modern-drama-contract.json")
SCHEMA_VERSION = 1


class ModernDramaContractError(ValueError):
    pass


def canonical_asset_ref(kind: str, value: str) -> str:
    prefix = {"character": "C", "scene": "S", "prop": "P"}.get(str(kind))
    clean = str(value or "").strip()
    if prefix is None:
        raise ModernDramaContractError(f"unsupported asset reference kind: {kind}")
    if not clean:
        raise ModernDramaContractError("asset reference value is required")
    return f"{prefix}:{clean}"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _approval() -> dict[str, Any]:
    return {"required": True, "status": "PENDING", "note": ""}


def _scene_index(package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(scene["id"]): scene
        for episode in package.get("episode_scripts", [])
        for scene in episode.get("scenes", [])
    }


def _shot_index(package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(shot["id"]): shot
        for scene in package.get("scene_breakdowns", [])
        for shot in scene.get("shots", [])
    }


def _tracks_for_shot(timeline: dict[str, Any], shot_id: str) -> list[str]:
    active = []
    for track in timeline.get("tracks", []):
        if any(str(clip.get("shot_id")) == shot_id for clip in track.get("clips", [])):
            active.append(str(track.get("name")))
    return active


def _unit_text(scene: dict[str, Any], kind: str) -> str:
    values = [
        str(unit.get("text") or "").strip()
        for unit in scene.get("units", [])
        if str(unit.get("kind") or "") == kind and str(unit.get("text") or "").strip()
    ]
    return " ".join(values)[:800]


def _story_beat(scene: dict[str, Any], shot: dict[str, Any]) -> str:
    kinds = {str(unit.get("kind") or "") for unit in scene.get("units", [])}
    if "DIALOGUE" in kinds:
        return "DIALOGUE_BEAT"
    if "ACTION" in kinds:
        return "ACTION_BEAT"
    if str(shot.get("motion_strategy")) == "SCREEN_MG":
        return "INFORMATION_BEAT"
    return "VISUAL_BEAT"


def _source_state(project: Path) -> dict[str, Any]:
    scripts = load_script_package(project)
    breakdown = load_shot_breakdown(project)
    timeline = load_timeline(project)
    plan = load_plan(project)
    return {
        "script_revision": int(scripts.get("revision") or 0),
        "shot_breakdown_revision": int(breakdown.get("revision") or 0),
        "timeline_revision": int(timeline.get("revision") or 0),
        "route_updated_at": str(plan.get("updated_at") or ""),
    }


def _source_fingerprint(project: Path) -> str:
    timeline = load_timeline(project)
    route_projection = [
        {
            "shot_id": shot.get("shot_id"),
            "duration_seconds": shot.get("duration_seconds"),
            "motion_strategy": shot.get("motion_strategy"),
            "renderer": shot.get("renderer"),
            "asset_paths": shot.get("asset_paths"),
            "timing_source": shot.get("timing_source"),
        }
        for shot in timeline.get("shots", [])
    ]
    return _sha256({"state": _source_state(project), "routes": route_projection})


def build_contract(project: Path) -> dict[str, Any]:
    project = Path(project).expanduser().resolve()
    if load_render_profile(project) != "modern_low_cost":
        raise ModernDramaContractError("production contract requires render_profile=modern_low_cost")

    scripts = load_script_package(project)
    breakdown = load_shot_breakdown(project)
    timeline = load_timeline(project)
    scenes = _scene_index(scripts)
    raw_shots = _shot_index(breakdown)

    previous_by_episode: dict[str, str] = {}
    output_shots: list[dict[str, Any]] = []

    for shot in timeline.get("shots", []):
        shot_id = str(shot["shot_id"])
        episode_id = str(shot["episode_id"])
        scene_id = str(shot["scene_id"])
        scene = scenes.get(scene_id) or {}
        raw = raw_shots.get(shot_id) or {}

        asset_refs: list[str] = []
        for character_id in shot.get("character_ids") or []:
            asset_refs.append(canonical_asset_ref("character", str(character_id)))
        location_id = str(shot.get("location_id") or "").strip()
        if location_id:
            asset_refs.append(canonical_asset_ref("scene", location_id))
        for path in shot.get("asset_paths") or []:
            asset_refs.append(canonical_asset_ref("prop", str(path)))
        asset_refs = list(dict.fromkeys(asset_refs))

        action = _unit_text(scene, "ACTION")
        dialogue = _unit_text(scene, "DIALOGUE")
        source_text = str(shot.get("script") or dialogue or action).strip()
        story_purpose = str(scene.get("story_purpose") or scene.get("purpose") or "").strip()
        if not story_purpose:
            story_purpose = source_text[:120]

        start_state = raw.get("start_state")
        blocking = ""
        if isinstance(start_state, dict):
            blocking = str(start_state.get("blocking") or start_state.get("position") or "")
        expression = str(scene.get("emotion") or scene.get("expression") or "")

        must_keep = [
            f"identity {ref}" for ref in asset_refs if ref.startswith("C:")
        ]
        if location_id:
            must_keep.append(f"scene layout S:{location_id}")
        must_not = [
            "do not add unplanned characters",
            "do not change locked identity or wardrobe without an explicit asset revision",
            "do not relocate the camera or actor blocking outside Director Intent",
        ]

        output_shots.append({
            "shot_id": shot_id,
            "episode_id": episode_id,
            "scene_id": scene_id,
            "asset_refs": asset_refs,
            "narrative": {
                "source_text": source_text,
                "story_purpose": story_purpose,
                "beat": _story_beat(scene, shot),
            },
            "director_intent": {
                "shot_size": str(raw.get("framing") or raw.get("shot_type") or ""),
                "camera_angle": str(raw.get("angle") or ""),
                "camera_movement": str(raw.get("movement") or shot.get("camera") or ""),
                "blocking": blocking,
                "action": action,
                "expression": expression,
                "continuity_from": previous_by_episode.get(episode_id),
                "must_keep": must_keep,
                "must_not": must_not,
            },
            "technical_execution": {
                "duration_seconds": float(shot["duration_seconds"]),
                "motion_strategy": str(shot["motion_strategy"]),
                "renderer": str(shot["renderer"]),
                "asset_paths": list(shot.get("asset_paths") or []),
                "tracks": _tracks_for_shot(timeline, shot_id),
                "estimated_cost": shot.get("estimated_cost"),
                "actual_cost": shot.get("actual_cost"),
                "timing_source": str(shot.get("timing_source") or ""),
            },
            "approvals": {
                "storyboard": _approval(),
                "keyframe": _approval(),
                "video": _approval(),
            },
        })
        previous_by_episode[episode_id] = shot_id

    state = _source_state(project)
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project.name,
        "render_profile": "modern_low_cost",
        "source_state": state,
        "source_fingerprint": _source_fingerprint(project),
        "shots": output_shots,
    }


def write_contract(project: Path) -> dict[str, Any]:
    project = Path(project).expanduser().resolve()
    payload = build_contract(project)
    _atomic_json(project / OUTPUT, payload)
    return payload


def load_contract(project: Path) -> dict[str, Any]:
    project = Path(project).expanduser().resolve()
    path = project / OUTPUT
    if not path.is_file():
        raise ModernDramaContractError("production contract has not been built")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModernDramaContractError(f"cannot read production contract: {error}") from error
    saved = str(payload.get("source_fingerprint") or "")
    current = _source_fingerprint(project)
    payload["freshness"] = "FRESH" if saved == current else "STALE"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("action", choices=("build", "status"))
    args = parser.parse_args()
    payload = write_contract(args.project_dir) if args.action == "build" else load_contract(args.project_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
