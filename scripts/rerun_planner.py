"""Build safe, non-mutating plans for rerunning part of a video project."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from .project_state import ROOT, STAGES, StateError, load_run_state
except ImportError:
    from project_state import ROOT, STAGES, StateError, load_run_state


SCENE_ID_PATTERN = re.compile(r"SC\d{3}\Z")
SCENE_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9])SC\d{3}(?![A-Za-z0-9])")

RERUN_TARGETS: dict[str, dict[str, Any]] = {
    "scene": {
        "minimum_status": "EDITED",
        "checkpoint": "VOICE_READY",
        "preserve": ["research", "topic", "script", "storyboard", "assets", "voice", "subtitles", "all_other_scenes"],
        "rebuild": ["target_scene", "final.mp4", "qc.json", "qc-report.md", "package.json"],
    },
    "voice": {
        "minimum_status": "VOICE_READY",
        "checkpoint": "ASSETS_READY",
        "preserve": ["research", "topic", "script", "storyboard", "assets", "cover.png", "all_scene_visuals"],
        "rebuild": ["voice.json", "subtitles", "final.mp4", "qc.json", "qc-report.md", "package.json"],
        "cache_policy": "reuse_voice_cache_on_exact_text_voice_speed_provider_match",
    },
    "cover": {
        "minimum_status": "PACKAGED",
        "checkpoint": "QC_PASS",
        "preserve": ["research", "topic", "script", "storyboard", "assets", "voice", "final.mp4", "qc.json"],
        "rebuild": ["cover.png", "package.json"],
    },
    "qc": {
        "minimum_status": "EDITED",
        "checkpoint": "EDITED",
        "preserve": ["research", "topic", "script", "storyboard", "assets", "voice", "scene_visuals", "final.mp4", "cover.png"],
        "rebuild": ["qc.json", "qc-report.md", "package.json"],
    },
}


def _scene_ids_from_json(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        scene_id = value.get("scene_id")
        if isinstance(scene_id, str) and SCENE_ID_PATTERN.fullmatch(scene_id):
            found.add(scene_id)
        for child in value.values():
            found.update(_scene_ids_from_json(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_scene_ids_from_json(child))
    return found


def _available_scene_ids(directory: Path) -> set[str]:
    storyboard_json = directory / "storyboard.json"
    storyboard_markdown = directory / "storyboard.md"
    found: set[str] = set()
    if storyboard_json.is_file():
        try:
            found.update(_scene_ids_from_json(json.loads(storyboard_json.read_text(encoding="utf-8"))))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StateError(f"cannot validate scene IDs from storyboard.json: {error}") from error
    if storyboard_markdown.is_file():
        try:
            found.update(SCENE_TOKEN_PATTERN.findall(storyboard_markdown.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError) as error:
            raise StateError(f"cannot validate scene IDs from storyboard.md: {error}") from error
    if not storyboard_json.is_file() and not storyboard_markdown.is_file():
        raise StateError("cannot rerun a scene: storyboard.json or storyboard.md is required to validate the scene ID")
    return found


def rerun_plan(directory: Path, project_id: str, target: str, scene_id: str | None = None) -> dict[str, Any]:
    """Return a scoped rerun plan without changing run.json or project artifacts."""
    if target not in RERUN_TARGETS:
        raise StateError(f"unknown rerun target: {target}; expected scene, voice, cover, or qc")
    if target == "scene":
        if scene_id is None or not SCENE_ID_PATTERN.fullmatch(scene_id):
            raise StateError("scene rerun requires a scene ID in the form SC001")
        available = _available_scene_ids(directory)
        if scene_id not in available:
            choices = ", ".join(sorted(available)) if available else "none found"
            raise StateError(f"scene {scene_id} not found in the storyboard (available: {choices})")
    elif scene_id is not None:
        raise StateError(f"scene ID is only valid for the scene target, not {target}")

    state = load_run_state(directory, project_id)
    current_index = STAGES.index(state["status"])
    minimum_status = RERUN_TARGETS[target]["minimum_status"]
    minimum_index = STAGES.index(minimum_status)
    if state["status"] == "PUBLISHED_MANUALLY":
        raise StateError("cannot rerun a project after manual publication has been recorded")
    if current_index < minimum_index:
        raise StateError(f"{target} rerun requires status {minimum_status} or later; current status is {state['status']}")

    spec = RERUN_TARGETS[target]
    checkpoint = spec["checkpoint"]
    checkpoint_index = STAGES.index(checkpoint)
    invalidated = [
        stage for stage in STAGES[checkpoint_index + 1 :]
        if stage != "PUBLISHED_MANUALLY"
    ]
    try:
        run_file = (directory / "run.json").relative_to(ROOT).as_posix()
    except ValueError:
        run_file = (directory / "run.json").as_posix()

    plan: dict[str, Any] = {
        "project_id": project_id,
        "status": state["status"],
        "target": {"type": target},
        "action": "plan_only",
        "execution_status": "not_executed",
        "execution_ready": False,
        "reason": "The CLI currently plans rerun scope; production stage executors are not wired yet.",
        "checkpoint": checkpoint,
        "resume_stage": STAGES[checkpoint_index + 1],
        "preserve": list(spec["preserve"]),
        "rebuild": [scene_id if item == "target_scene" else item for item in spec["rebuild"]],
        "invalidated_stages_after_success": invalidated,
        "state_changed": False,
        "run_file": run_file,
    }
    if target == "scene":
        plan["target"]["scene_id"] = scene_id
    if "cache_policy" in spec:
        plan["cache_policy"] = spec["cache_policy"]
    return plan
