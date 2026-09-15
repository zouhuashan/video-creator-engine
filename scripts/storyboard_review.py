"""Review a storyboard for visual pacing, evidence, hook, and conclusion emphasis."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .project_state import StateError, load_run_state
except ImportError:
    from project_state import StateError, load_run_state


OUTPUT_NAMES = ("storyboard-review.json", "storyboard-review.md")
MAX_STATIC_SECONDS = 8.0


class StoryboardReviewError(ValueError):
    """Raised when completed storyboard artifacts cannot be reviewed."""


def _read(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise StoryboardReviewError(f"{label} not found: {path}") from error
    except json.JSONDecodeError as error:
        raise StoryboardReviewError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise StoryboardReviewError(f"{label} must contain an object")
    return value


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _signature(scene: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(scene.get(field, "")).strip() for field in ("visual_type", "visual_description", "asset_query", "motion"))


def review_storyboard(storyboard: dict[str, Any], script: dict[str, Any]) -> dict[str, Any]:
    scenes = storyboard.get("scenes")
    script_sections = script.get("sections")
    if not isinstance(scenes, list) or not scenes or not isinstance(script_sections, list) or not script_sections:
        raise StoryboardReviewError("storyboard.json and script.json must contain scenes and sections")
    issues: list[dict[str, Any]] = []
    checks: dict[str, bool] = {}
    cited_sources = {source_id for section in script_sections if isinstance(section, dict) for source_id in section.get("source_ids", [])}

    static_start = float(scenes[0].get("start", 0))
    signature = _signature(scenes[0])
    for index, scene in enumerate(scenes[1:], start=1):
        if _signature(scene) != signature:
            duration = float(scenes[index - 1]["end"]) - static_start
            if duration > MAX_STATIC_SECONDS:
                issues.append({"check": "visual_change", "scene_ids": [item["scene_id"] for item in scenes[:index] if _signature(item) == signature], "message": f"同一视觉连续 {duration:g} 秒，超过 {MAX_STATIC_SECONDS:g} 秒"})
            static_start = float(scene["start"])
            signature = _signature(scene)
    duration = float(scenes[-1]["end"]) - static_start
    if duration > MAX_STATIC_SECONDS:
        issues.append({"check": "visual_change", "message": f"同一视觉连续 {duration:g} 秒，超过 {MAX_STATIC_SECONDS:g} 秒"})
    checks["visual_change_within_eight_seconds"] = not any(issue["check"] == "visual_change" for issue in issues)

    signatures: dict[tuple[str, str, str, str], list[str]] = {}
    for scene in scenes:
        signatures.setdefault(_signature(scene), []).append(scene["scene_id"])
    duplicates = [scene_ids for scene_ids in signatures.values() if len(scene_ids) > 1]
    if duplicates:
        issues.append({"check": "duplicate_visual", "scene_groups": duplicates, "message": "存在重复画面"})
    checks["no_duplicate_visuals"] = not duplicates

    text_runs: list[list[str]] = []
    run: list[str] = []
    for scene in scenes:
        if scene.get("visual_type") == "text_only":
            run.append(scene["scene_id"])
        else:
            if len(run) > 1:
                text_runs.append(run)
            run = []
    if len(run) > 1:
        text_runs.append(run)
    if text_runs:
        issues.append({"check": "text_stack", "scene_groups": text_runs, "message": "存在连续纯字幕堆叠"})
    checks["no_text_only_stack"] = not text_runs

    evidence_sources = {source_id for scene in scenes if scene.get("visual_type") != "text_only" for source_id in scene.get("source", [])}
    missing_evidence = sorted(cited_sources - evidence_sources)
    if missing_evidence:
        issues.append({"check": "evidence_visual", "source_ids": missing_evidence, "message": "缺少可视证据画面"})
    checks["sufficient_evidence_visuals"] = not missing_evidence

    hook_scenes = [scene for scene in scenes if float(scene["start"]) < 3]
    hook_ok = bool(hook_scenes) and any(scene.get("visual_type") != "text_only" and scene.get("visual_description") != scene.get("caption") for scene in hook_scenes)
    if not hook_ok:
        issues.append({"check": "hook_visual", "message": "开头 3 秒缺少与 Hook 匹配的非纯字幕画面"})
    checks["hook_visual_match"] = hook_ok

    conclusion = next((section.get("narration", "") for section in script_sections if section.get("section") == "conclusion"), "")
    conclusion_scenes = [scene for scene in scenes if scene.get("spoken_text") and scene["spoken_text"] in conclusion]
    conclusion_ok = any(scene.get("visual_type") in {"chart", "comparison", "text_only", "screenshot"} for scene in conclusion_scenes)
    if not conclusion_ok:
        issues.append({"check": "conclusion_visual", "message": "关键结论缺少视觉强化"})
    checks["conclusion_visual_emphasis"] = conclusion_ok
    return {"passed": not issues, "checks": checks, "issues": issues}


def _write(path: Path, content: str) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(content if content.endswith("\n") else content + "\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def write_storyboard_review(directory: Path, project_id: str) -> dict[str, Any]:
    directory = Path(directory)
    state = load_run_state(directory, project_id)
    if state["status"] != "STORYBOARDED":
        raise StateError(f"storyboard review requires status STORYBOARDED; current status is {state['status']}")
    paths = [directory / name for name in OUTPUT_NAMES]
    if any(path.exists() for path in paths):
        raise StateError("refusing to overwrite existing storyboard review artifact")
    storyboard = _read(directory / "storyboard.json", "storyboard.json")
    script = _read(directory / "script.json", "script.json")
    result = review_storyboard(storyboard, script)
    result.update({"schema_version": 1, "project_id": project_id, "created_at": _timestamp()})
    markdown = ["# 分镜审查", "", f"- 结果：{'PASS' if result['passed'] else 'NEEDS_REVISION'}", ""]
    markdown.extend(f"- {name}：{'通过' if passed else '未通过'}" for name, passed in result["checks"].items())
    if result["issues"]:
        markdown.extend(["", "## 问题", ""])
        markdown.extend(f"- {issue['message']}" for issue in result["issues"])
    _write(paths[0], json.dumps(result, ensure_ascii=False, indent=2))
    _write(paths[1], "\n".join(markdown))
    return {"project_id": project_id, "passed": result["passed"], "issues": result["issues"], "outputs": list(OUTPUT_NAMES), "state": state["status"]}
