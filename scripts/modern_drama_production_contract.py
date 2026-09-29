#!/usr/bin/env python3
"""Build and review a provider-neutral production contract for modern low-cost drama."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from scripts.cost_first_hybrid_router import load_plan, load_render_profile
from scripts.novel_episode_script import load_script_package
from scripts.novel_shot_breakdown import load_shot_breakdown

OUTPUT = Path("production/modern-drama-contract.json")
SCHEMA_VERSION = 1
REVIEW_STAGES = ("storyboard", "keyframe", "video")
REVIEW_RESULTS = ("APPROVED", "REJECTED")
KEYFRAME_STRATEGIES = {"STATIC", "LOCAL_MOTION", "LAYERED_2_5D", "AI_VIDEO"}


class ModernDramaContractError(ValueError):
    pass


def _load_timeline(project: Path) -> dict[str, Any]:
    # Lazy import keeps contract primitives testable without loading rendering backends.
    from scripts.modern_editable_timeline import load_timeline

    return load_timeline(project)


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


def _approval(required: bool = True) -> dict[str, Any]:
    return {"required": bool(required), "status": "PENDING" if required else "NOT_REQUIRED", "note": ""}


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
    if str(shot.get("motion_strategy")) == "SCREEN_MG":
        return "INFORMATION_BEAT"
    if "DIALOGUE" in kinds:
        return "DIALOGUE_BEAT"
    if "ACTION" in kinds:
        return "ACTION_BEAT"
    return "VISUAL_BEAT"


def _source_state(project: Path) -> dict[str, Any]:
    scripts = load_script_package(project)
    breakdown = load_shot_breakdown(project)
    timeline = _load_timeline(project)
    plan = load_plan(project)
    return {
        "script_revision": int(scripts.get("revision") or 0),
        "shot_breakdown_revision": int(breakdown.get("revision") or 0),
        "timeline_revision": int(timeline.get("revision") or 0),
        "route_updated_at": str(plan.get("updated_at") or ""),
    }


def _source_fingerprint(project: Path) -> str:
    timeline = _load_timeline(project)
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


def _shot_fingerprint(shot: dict[str, Any]) -> str:
    technical = dict(shot["technical_execution"])
    technical.pop("actual_cost", None)
    return _sha256({
        "asset_refs": shot["asset_refs"],
        "narrative": shot["narrative"],
        "director_intent": shot["director_intent"],
        "technical_execution": technical,
    })


def _existing_shots(project: Path) -> dict[str, dict[str, Any]]:
    path = project / OUTPUT
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        str(item.get("shot_id")): item
        for item in payload.get("shots", [])
        if isinstance(item, dict) and item.get("shot_id")
    }


def _preserved_approvals(
    existing: dict[str, Any] | None,
    shot_fingerprint: str,
    *,
    keyframe_required: bool,
) -> dict[str, Any]:
    fresh = {
        "storyboard": _approval(True),
        "keyframe": _approval(keyframe_required),
        "video": _approval(True),
    }
    if not existing or str(existing.get("shot_fingerprint") or "") != shot_fingerprint:
        return fresh
    old = existing.get("approvals")
    if not isinstance(old, dict):
        return fresh
    for stage in REVIEW_STAGES:
        candidate = old.get(stage)
        if not isinstance(candidate, dict):
            continue
        required = fresh[stage]["required"]
        if not required:
            fresh[stage] = _approval(False)
            continue
        status = str(candidate.get("status") or "")
        if status in REVIEW_RESULTS:
            fresh[stage] = {
                "required": True,
                "status": status,
                "note": str(candidate.get("note") or ""),
            }
    return fresh


def _review_gate(shot: dict[str, Any], stage: str) -> None:
    stage = str(stage or "").strip()
    if stage not in REVIEW_STAGES:
        raise ModernDramaContractError("review stage must be storyboard, keyframe or video")
    approvals = shot.get("approvals") or {}
    target = approvals.get(stage) or {}
    if target.get("required") is not True:
        raise ModernDramaContractError(f"{stage} review is not required for this Shot")
    if stage in {"keyframe", "video"} and (approvals.get("storyboard") or {}).get("status") != "APPROVED":
        raise ModernDramaContractError("storyboard must be APPROVED first")
    if stage == "video":
        keyframe = approvals.get("keyframe") or {}
        if keyframe.get("required") is True and keyframe.get("status") != "APPROVED":
            raise ModernDramaContractError("required keyframe must be APPROVED before video review")


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    shots = payload.get("shots", [])
    stages: dict[str, dict[str, int]] = {}
    for stage in REVIEW_STAGES:
        stage_items = [(shot.get("approvals") or {}).get(stage) or {} for shot in shots]
        required = [item for item in stage_items if item.get("required") is True]
        stages[stage] = {
            "required": len(required),
            "approved": sum(1 for item in required if item.get("status") == "APPROVED"),
            "rejected": sum(1 for item in required if item.get("status") == "REJECTED"),
            "pending": sum(1 for item in required if item.get("status") == "PENDING"),
        }
    return {"shot_count": len(shots), "stages": stages}


def build_contract(project: Path) -> dict[str, Any]:
    project = Path(project).expanduser().resolve()
    if load_render_profile(project) != "modern_low_cost":
        raise ModernDramaContractError("production contract requires render_profile=modern_low_cost")

    scripts = load_script_package(project)
    breakdown = load_shot_breakdown(project)
    timeline = _load_timeline(project)
    scenes = _scene_index(scripts)
    raw_shots = _shot_index(breakdown)
    existing = _existing_shots(project)

    previous_by_episode: dict[str, str] = {}
    output_shots: list[dict[str, Any]] = []

    for timeline_shot in timeline.get("shots", []):
        shot_id = str(timeline_shot["shot_id"])
        episode_id = str(timeline_shot["episode_id"])
        scene_id = str(timeline_shot["scene_id"])
        scene = scenes.get(scene_id) or {}
        raw = raw_shots.get(shot_id) or {}

        asset_refs: list[str] = []
        for character_id in timeline_shot.get("character_ids") or []:
            asset_refs.append(canonical_asset_ref("character", str(character_id)))
        location_id = str(timeline_shot.get("location_id") or "").strip()
        if location_id:
            asset_refs.append(canonical_asset_ref("scene", location_id))
        for path in timeline_shot.get("asset_paths") or []:
            asset_refs.append(canonical_asset_ref("prop", str(path)))
        asset_refs = list(dict.fromkeys(asset_refs))

        action = _unit_text(scene, "ACTION")
        dialogue = _unit_text(scene, "DIALOGUE")
        source_text = str(timeline_shot.get("script") or dialogue or action).strip()
        story_purpose = str(scene.get("story_purpose") or scene.get("purpose") or "").strip() or source_text[:120]

        start_state = raw.get("start_state")
        blocking = ""
        if isinstance(start_state, dict):
            blocking = str(start_state.get("blocking") or start_state.get("position") or "")

        must_keep = [f"identity {ref}" for ref in asset_refs if ref.startswith("C:")]
        if location_id:
            must_keep.append(f"scene layout S:{location_id}")

        technical = {
            "duration_seconds": float(timeline_shot["duration_seconds"]),
            "motion_strategy": str(timeline_shot["motion_strategy"]),
            "renderer": str(timeline_shot["renderer"]),
            "asset_paths": list(timeline_shot.get("asset_paths") or []),
            "tracks": _tracks_for_shot(timeline, shot_id),
            "estimated_cost": timeline_shot.get("estimated_cost"),
            "actual_cost": timeline_shot.get("actual_cost"),
            "timing_source": str(timeline_shot.get("timing_source") or ""),
        }
        shot = {
            "shot_id": shot_id,
            "episode_id": episode_id,
            "scene_id": scene_id,
            "asset_refs": asset_refs,
            "narrative": {
                "source_text": source_text,
                "story_purpose": story_purpose,
                "beat": _story_beat(scene, timeline_shot),
            },
            "director_intent": {
                "shot_size": str(raw.get("framing") or raw.get("shot_type") or ""),
                "camera_angle": str(raw.get("angle") or ""),
                "camera_movement": str(raw.get("movement") or timeline_shot.get("camera") or ""),
                "blocking": blocking,
                "action": action,
                "expression": str(scene.get("emotion") or scene.get("expression") or ""),
                "continuity_from": previous_by_episode.get(episode_id),
                "must_keep": must_keep,
                "must_not": [
                    "do not add unplanned characters",
                    "do not change locked identity or wardrobe without an explicit asset revision",
                    "do not relocate camera or actor blocking outside Director Intent",
                ],
            },
            "technical_execution": technical,
        }
        shot["shot_fingerprint"] = _shot_fingerprint(shot)
        keyframe_required = technical["motion_strategy"] in KEYFRAME_STRATEGIES
        shot["approvals"] = _preserved_approvals(
            existing.get(shot_id),
            shot["shot_fingerprint"],
            keyframe_required=keyframe_required,
        )
        output_shots.append(shot)
        previous_by_episode[episode_id] = shot_id

    payload = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project.name,
        "render_profile": "modern_low_cost",
        "source_state": _source_state(project),
        "source_fingerprint": _source_fingerprint(project),
        "shots": output_shots,
    }
    payload["summary"] = _summary(payload)
    return payload


def write_contract(project: Path) -> dict[str, Any]:
    project = Path(project).expanduser().resolve()
    payload = build_contract(project)
    _atomic_json(project / OUTPUT, payload)
    payload["freshness"] = "FRESH"
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
    payload["summary"] = _summary(payload)
    return payload


def review_shot(
    project: Path,
    *,
    shot_id: str,
    stage: str,
    status: str,
    note: str = "",
) -> dict[str, Any]:
    project = Path(project).expanduser().resolve()
    payload = load_contract(project)
    if payload.get("freshness") != "FRESH":
        raise ModernDramaContractError("production contract is STALE; rebuild it before reviewing")

    shot = next((item for item in payload.get("shots", []) if item.get("shot_id") == shot_id), None)
    if shot is None:
        raise ModernDramaContractError("unknown shot_id")
    stage = str(stage or "").strip()
    status = str(status or "").strip().upper()
    if status not in REVIEW_RESULTS:
        raise ModernDramaContractError("review status must be APPROVED or REJECTED")
    _review_gate(shot, stage)
    shot["approvals"][stage] = {"required": True, "status": status, "note": str(note or "").strip()}

    # A rejected upstream stage invalidates downstream approvals for this Shot only.
    if status == "REJECTED":
        if stage == "storyboard":
            keyframe_required = bool((shot["approvals"].get("keyframe") or {}).get("required"))
            shot["approvals"]["keyframe"] = _approval(keyframe_required)
            shot["approvals"]["video"] = _approval(True)
        elif stage == "keyframe":
            shot["approvals"]["video"] = _approval(True)

    payload.pop("freshness", None)
    payload["summary"] = _summary(payload)
    _atomic_json(project / OUTPUT, payload)
    payload["freshness"] = "FRESH"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("action", choices=("build", "status", "review"))
    parser.add_argument("--shot-id")
    parser.add_argument("--stage", choices=REVIEW_STAGES)
    parser.add_argument("--status", choices=REVIEW_RESULTS)
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    if args.action == "build":
        payload = write_contract(args.project_dir)
    elif args.action == "status":
        payload = load_contract(args.project_dir)
    else:
        if not args.shot_id or not args.stage or not args.status:
            parser.error("review requires --shot-id, --stage and --status")
        payload = review_shot(
            args.project_dir,
            shot_id=args.shot_id,
            stage=args.stage,
            status=args.status,
            note=args.note,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
