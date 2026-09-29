#!/usr/bin/env python3
"""Prevent expensive video generation before identity and shot approval are ready."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.cost_first_hybrid_router import load_render_profile
from scripts.modern_asset_library import load_library
from scripts.novel_character_designs import load_character_designs
from scripts.novel_episode_script import load_script_package
from scripts.novel_shot_breakdown import load_shot_breakdown
from scripts.novel_storyboard import load_storyboard


class DramaProductionGateError(ValueError):
    pass


def _shot_context(project: Path, shot_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    shots = load_shot_breakdown(project)
    scripts = load_script_package(project)
    scene_index = {
        scene["id"]: scene
        for episode in scripts["episode_scripts"]
        for scene in episode["scenes"]
    }
    for breakdown in shots["scene_breakdowns"]:
        for shot in breakdown["shots"]:
            if shot["id"] == shot_id:
                scene = scene_index.get(breakdown["scene_id"])
                if scene is None:
                    raise DramaProductionGateError(f"scene missing for shot: {shot_id}")
                return shot, scene
    raise DramaProductionGateError(f"unknown shot_id: {shot_id}")


def _modern_character_blockers(project: Path, character_ids: list[str]) -> list[str]:
    if not character_ids:
        return []
    library = load_library(project)
    blockers: list[str] = []
    for character_id in character_ids:
        approved = [
            item
            for item in library["assets"]
            if item.get("kind") == "character"
            and item.get("entity_id") == character_id
            and item.get("review_status") == "APPROVED"
        ]
        if not approved:
            blockers.append(f"character asset not approved: {character_id}")
    return blockers


def _modern_storyboard_blockers(project: Path, shot_id: str) -> list[str]:
    path = project / "rendering/modern-timeline-edits.json"
    if not path.is_file():
        return [f"shot review not approved: {shot_id}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [f"shot review data unreadable: {shot_id}"]
    review = ((payload.get("shots") or {}).get(shot_id) or {}).get("human_review") or {}
    if review.get("status") != "APPROVED":
        return [f"shot review not approved: {shot_id}"]
    return []


def _character_design_blockers(project: Path, character_ids: list[str]) -> list[str]:
    if not character_ids:
        return []
    try:
        package = load_character_designs(project)
    except Exception as error:
        return [f"character design package is not ready: {error}"]
    designs = {item["character_id"]: item for item in package["character_designs"]}
    blockers: list[str] = []
    for character_id in character_ids:
        design = designs.get(character_id)
        if design is None:
            blockers.append(f"character design missing: {character_id}")
            continue
        if design.get("status") != "READY" or (design.get("human_review") or {}).get("status") != "APPROVED":
            blockers.append(f"character design not approved: {character_id}")
    return blockers


def _storyboard_blockers(project: Path, shot_id: str) -> list[str]:
    try:
        storyboard = load_storyboard(project)
    except Exception as error:
        return [f"storyboard is not ready: {error}"]
    frame = next((item for item in storyboard["frames"] if item["shot_id"] == shot_id), None)
    if frame is None:
        return [f"storyboard frame missing: {shot_id}"]
    blockers: list[str] = []
    if (frame.get("human_review") or {}).get("status") != "APPROVED":
        blockers.append(f"storyboard shot not approved: {shot_id}")
    start = frame.get("start") or {}
    if start.get("status") != "SELECTED" or not start.get("asset_id"):
        blockers.append(f"approved start keyframe missing: {shot_id}")
    return blockers


def check_shot_readiness(project: Path, shot_id: str) -> dict[str, Any]:
    project = Path(project).resolve()
    shot_id = str(shot_id or "").strip()
    if not shot_id:
        raise DramaProductionGateError("shot_id is required")
    shot, scene = _shot_context(project, shot_id)
    profile = load_render_profile(project)
    character_ids = list(scene.get("character_ids") or [])
    if profile == "modern_low_cost":
        blockers = _modern_character_blockers(project, character_ids)
        blockers += _modern_storyboard_blockers(project, shot_id)
        gate = "MODERN_CHARACTER_ASSET_AND_SHOT_REVIEW"
    else:
        blockers = _character_design_blockers(project, character_ids)
        blockers += _storyboard_blockers(project, shot_id)
        gate = "CHARACTER_DESIGN_AND_STORYBOARD"
    return {
        "ready": not blockers,
        "gate": gate,
        "render_profile": profile,
        "shot_id": shot_id,
        "scene_id": scene["id"],
        "character_ids": character_ids,
        "duration_seconds": float(shot.get("duration_seconds") or 0.0),
        "blockers": blockers,
    }


def require_shot_ready_for_video(project: Path, shot_id: str) -> dict[str, Any]:
    result = check_shot_readiness(project, shot_id)
    if not result["ready"]:
        raise DramaProductionGateError("; ".join(result["blockers"]))
    return result


__all__ = [
    "DramaProductionGateError",
    "check_shot_readiness",
    "require_shot_ready_for_video",
]
