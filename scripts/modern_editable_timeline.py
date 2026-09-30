#!/usr/bin/env python3
"""Shot-level editable project layered over existing script, voice timing and router."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from adapters.video_generation import LocalMicroMotionVideo, LocalScenePlateVideo, VideoGenerationRequest
from scripts.cost_first_hybrid_router import MOTION_STRATEGIES, load_plan
from scripts.modern_drama_production_contract import require_ai_video_gate, require_render_gate
from scripts.modern_asset_library import load_library
from scripts.novel_episode_script import load_script_package
from scripts.render_screen_mg import render_screen_mg
from scripts.render_stock_broll import render_stock_broll
from scripts.render_layered_25d import render_layered_25d

OUTPUT = Path("rendering/modern-timeline-edits.json")
RENDERER = {"STATIC": "local_scene_plate", "LOCAL_MOTION": "local_micro_motion", "SCREEN_MG": "local_screen_mg", "STOCK_BROLL": "stock_broll_library", "LAYERED_2_5D": "local_layered_25d", "AI_VIDEO": "hailuo_h3_manual_web"}
TRACKS = ("VIDEO", "CHARACTER", "BACKGROUND", "MG", "FX", "SUBTITLE", "VOICE", "BGM", "SFX", "TRANSITION")


class ModernTimelineError(ValueError):
    pass


def _read(project: Path) -> dict[str, Any]:
    path = Path(project).resolve() / OUTPUT
    if not path.is_file():
        return {"schema_version": 1, "revision": 0, "shots": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModernTimelineError(f"cannot read editable timeline: {error}") from error
    if payload.get("schema_version") != 1 or not isinstance(payload.get("shots"), dict):
        raise ModernTimelineError("editable timeline format is invalid")
    return payload


def _write(project: Path, payload: dict[str, Any]) -> None:
    path = Path(project).resolve() / OUTPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".timeline-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _script_index(project: Path) -> dict[str, dict[str, Any]]:
    package = load_script_package(project)
    return {scene["id"]: scene for episode in package["episode_scripts"] for scene in episode["scenes"]}


def load_timeline(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    plan = load_plan(project)
    edits = _read(project)
    scripts = _script_index(project)
    map_path = project / "storyboard/modern-shot-units.json"
    try:
        shot_unit_map = json.loads(map_path.read_text(encoding="utf-8")).get("shots", {}) if map_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        shot_unit_map = {}
    tracks = {name: [] for name in TRACKS}
    shots: list[dict[str, Any]] = []
    positions: dict[str, float] = {}
    for route in plan.get("routes") or []:
        shot_id = route["shot_id"]
        scene = scripts.get(route["scene_id"], {})
        edit = edits["shots"].get(shot_id) or {}
        strategy = edit.get("motion_strategy") or route.get("motion_strategy") or "STATIC"
        if strategy not in MOTION_STRATEGIES:
            raise ModernTimelineError(f"invalid strategy saved for {shot_id}")
        duration = float(edit.get("duration_seconds") or route["duration_seconds"])
        start = positions.get(route["episode_id"], 0.0)
        end = round(start + duration, 3)
        positions[route["episode_id"]] = end
        scoped_ids = set((shot_unit_map.get(shot_id) or {}).get("unit_ids") or [])
        units = [unit for unit in scene.get("units") or [] if unit["id"] in scoped_ids] if scoped_ids else scene.get("units") or []
        estimated_cost = route.get("estimated_cost") if strategy == route.get("motion_strategy") else ({"amount": route.get("h3_full_cost_shells"), "unit": "H3_SHELL_ESTIMATE"} if strategy == "AI_VIDEO" else {"amount": None, "unit": "LICENSE_DEPENDENT"} if strategy == "STOCK_BROLL" else {"amount": 0.0, "unit": "INCREMENTAL_PROVIDER_CHARGE"})
        shot = {
            "shot_id": shot_id, "episode_id": route["episode_id"], "scene_id": route["scene_id"],
            "script": str((shot_unit_map.get(shot_id) or {}).get("text_excerpt") or " ".join(str(unit.get("text") or "") for unit in units)[:800]),
            "character_ids": scene.get("character_ids") or [], "location_id": scene.get("location_id"),
            "camera": route.get("camera_movement"), "timing_source": route.get("timing_source"),
            "start_seconds": round(start, 3), "end_seconds": end, "duration_seconds": duration,
            "motion_strategy": strategy, "renderer": RENDERER[strategy],
            "asset_paths": edit.get("asset_paths") or [], "screen_mg": edit.get("screen_mg") or {},
            "preview": edit.get("preview") or {}, "status": edit.get("status") or "PLANNED",
            "estimated_cost": estimated_cost, "actual_cost": edit.get("actual_cost"),
            "reason": edit.get("reason") or ("人工调整镜头策略" if strategy != route.get("motion_strategy") else route.get("reason") or ""),
        }
        shots.append(shot)
        for name in TRACKS:
            if name == "VIDEO" or (name == "CHARACTER" and shot["character_ids"]) or (name == "BACKGROUND" and shot["location_id"]) or (name == "MG" and strategy == "SCREEN_MG") or (name == "VOICE" and any(unit.get("kind") == "DIALOGUE" for unit in units)):
                tracks[name].append({"shot_id": shot_id, "episode_id": route["episode_id"], "start_seconds": shot["start_seconds"], "end_seconds": end, "status": shot["status"] if name == "VIDEO" else "SOURCE_LINKED"})
    return {"schema_version": 1, "project_id": project.name, "render_profile": plan.get("render_profile"), "revision": edits["revision"], "shot_count": len(shots), "tracks": [{"name": name, "clips": clips} for name, clips in tracks.items()], "shots": shots, "episode_durations": positions}


def update_shot(project: Path, shot_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    project = Path(project).resolve()
    current = next((item for item in load_timeline(project)["shots"] if item["shot_id"] == shot_id), None)
    if current is None:
        raise ModernTimelineError("unknown shot_id")
    allowed = {"motion_strategy", "duration_seconds", "asset_paths", "screen_mg", "reason"}
    if not isinstance(changes, dict) or set(changes) - allowed:
        raise ModernTimelineError("unsupported shot edit field")
    if "motion_strategy" in changes and changes["motion_strategy"] not in MOTION_STRATEGIES:
        raise ModernTimelineError("invalid motion_strategy")
    if "duration_seconds" in changes:
        try:
            duration = float(changes["duration_seconds"])
        except (TypeError, ValueError) as error:
            raise ModernTimelineError("invalid duration") from error
        if not math.isfinite(duration) or not 1 <= duration <= 30:
            raise ModernTimelineError("duration must be 1-30 seconds")
        if current["timing_source"] == "ACTUAL_TTS" and abs(duration - current["duration_seconds"]) > 0.01:
            raise ModernTimelineError("voice-locked Shot duration cannot change until voice timing is revised")
        changes["duration_seconds"] = round(duration, 3)
    if "asset_paths" in changes:
        registered = {item["path"] for item in load_library(project)["assets"]}
        paths = changes["asset_paths"]
        if not isinstance(paths, list) or len(paths) > 2 or any(path not in registered for path in paths):
            raise ModernTimelineError("select at most two registered project assets")
    if "screen_mg" in changes:
        spec = changes["screen_mg"]
        if not isinstance(spec, dict) or set(spec) - {"template", "title", "lines"}:
            raise ModernTimelineError("invalid screen MG specification")
    edits = _read(project)
    previous = edits["shots"].get(shot_id) or {}
    edits["shots"][shot_id] = {**previous, **changes, "status": "DIRTY", "preview": {}}
    edits["revision"] += 1
    _write(project, edits)
    return next(item for item in load_timeline(project)["shots"] if item["shot_id"] == shot_id)


def rerender_shot(project: Path, shot_id: str) -> dict[str, Any]:
    project = Path(project).resolve()
    require_render_gate(project, shot_id)
    shot = next((item for item in load_timeline(project)["shots"] if item["shot_id"] == shot_id), None)
    if shot is None:
        raise ModernTimelineError("unknown shot_id")
    strategy = shot["motion_strategy"]
    assets = {item["path"]: item for item in load_library(project)["assets"]}
    selected = shot["asset_paths"]
    if strategy == "AI_VIDEO":
        try:
            require_ai_video_gate(project, shot_id)
        except ValueError as error:
            raise ModernTimelineError(f"AI Video production gate blocked: {error}") from error
        raise ModernTimelineError("AI Video gate passed, but paid generation remains manual; no paid call was made")
    if strategy == "SCREEN_MG":
        spec = shot["screen_mg"]
        result = render_screen_mg(project, shot_id=shot_id, kind=str(spec.get("template") or "chat"), title=str(spec.get("title") or ""), lines=spec.get("lines"), duration_seconds=shot["duration_seconds"])
    elif strategy == "STOCK_BROLL":
        if len(selected) != 1 or assets.get(selected[0], {}).get("kind") != "stock":
            raise ModernTimelineError("select one rights-declared B-roll asset")
        result = render_stock_broll(project, shot_id=shot_id, asset_path=selected[0], duration_seconds=shot["duration_seconds"])
    elif strategy in {"STATIC", "LOCAL_MOTION"}:
        if len(selected) != 1 or assets.get(selected[0], {}).get("kind") not in {"scene", "character"}:
            raise ModernTimelineError("select one registered image asset")
        output = project / "rendering/modern-shot-previews" / f"{shot_id}.mp4"
        request = VideoGenerationRequest(image_paths=((project / selected[0]).resolve(),), output_path=output, shot_duration_seconds=shot["duration_seconds"], fps=24, width=540, height=960)
        generated = (LocalScenePlateVideo() if strategy == "STATIC" else LocalMicroMotionVideo()).generate(request)
        result = {"status": "READY", "renderer": generated.provider, "shot_id": shot_id, "output": output.relative_to(project).as_posix(), "duration_seconds": shot["duration_seconds"]}
    elif strategy == "LAYERED_2_5D":
        if len(selected) != 2 or assets.get(selected[0], {}).get("kind") != "scene" or assets.get(selected[1], {}).get("kind") != "character":
            raise ModernTimelineError("select two assets in order: scene background, then transparent character")
        result = render_layered_25d(project, shot_id=shot_id, background=project / selected[0], character=project / selected[1], duration_seconds=shot["duration_seconds"])
    else:
        raise ModernTimelineError("unsupported motion strategy")
    edits = _read(project)
    previous = edits["shots"].get(shot_id) or {}
    edits["shots"][shot_id] = {**previous, "status": "PREVIEW_READY", "preview": result, "actual_cost": {"amount": 0, "unit": "REMOTE_PROVIDER_CHARGE"}}
    edits["revision"] += 1
    _write(project, edits)
    return next(item for item in load_timeline(project)["shots"] if item["shot_id"] == shot_id)
