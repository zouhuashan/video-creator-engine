"""Validate a timed storyboard against a completed VideoCreator script."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .project_state import StateError, load_run_state, transition_project
except ImportError:
    from project_state import StateError, load_run_state, transition_project


SCHEMA_VERSION = 1
OUTPUT_NAMES = ("storyboard.json", "storyboard.md")
SCENE_ID_PATTERN = re.compile(r"SC\d{3,}\Z")
SCENE_FIELDS = {
    "scene_id",
    "start",
    "end",
    "spoken_text",
    "caption",
    "visual_description",
    "visual_type",
    "asset_query",
    "motion",
    "transition",
    "source",
}


class StoryboardInputError(ValueError):
    """Raised when a storyboard cannot safely represent the completed script."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise StoryboardInputError(f"{label} not found: {path}") from error
    except json.JSONDecodeError as error:
        raise StoryboardInputError(f"invalid {label}: {error}") from error


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StoryboardInputError(f"{label} must be a non-empty string")
    return value.strip()


def _seconds(value: Any, label: str) -> float:
    if type(value) not in (int, float) or value < 0:
        raise StoryboardInputError(f"{label} must be a non-negative number")
    return float(value)


def _canonical_spoken_text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _format_seconds(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.1f}".rstrip("0").rstrip(".")


def _load_script(directory: Path, project_id: str) -> dict[str, Any]:
    script = _read_json(directory / "script.json", "script.json")
    if not isinstance(script, dict) or script.get("schema_version") != 1:
        raise StoryboardInputError("script.json must use schema_version 1")
    if script.get("project_id") != project_id:
        raise StoryboardInputError("script.json project_id does not match this project")
    topic = script.get("topic")
    if not isinstance(topic, str) or not topic.strip():
        raise StoryboardInputError("script.json has no topic")
    target = script.get("target_duration_seconds")
    if type(target) is not int or target < 1:
        raise StoryboardInputError("script.json has no valid target_duration_seconds")
    sections = script.get("sections")
    if not isinstance(sections, list) or not sections:
        raise StoryboardInputError("script.json has no sections")
    if any(not isinstance(section, dict) or not isinstance(section.get("narration"), str) for section in sections):
        raise StoryboardInputError("script.json has invalid section narration")
    sources = script.get("sources")
    if not isinstance(sources, list):
        raise StoryboardInputError("script.json has no source list")
    source_ids = {
        source.get("source_id")
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("source_id"), str)
    }
    if len(source_ids) != len(sources):
        raise StoryboardInputError("script.json has invalid source IDs")
    return script


def _normalize_scenes(payload: Any, script: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION or set(payload) != {"schema_version", "scenes"}:
        raise StoryboardInputError("storyboard input must contain only schema_version 1 and scenes")
    raw_scenes = payload.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise StoryboardInputError("scenes must be a non-empty list")

    script_source_ids = {source["source_id"] for source in script["sources"]}
    expected_spoken = _canonical_spoken_text("".join(section["narration"] for section in script["sections"]))
    normalized: list[dict[str, Any]] = []
    previous_end = 0.0
    for index, raw_scene in enumerate(raw_scenes, start=1):
        if not isinstance(raw_scene, dict) or set(raw_scene) != SCENE_FIELDS:
            raise StoryboardInputError(f"scenes[{index - 1}] must contain exactly: {', '.join(sorted(SCENE_FIELDS))}")
        scene_id = _text(raw_scene.get("scene_id"), f"scenes[{index - 1}].scene_id")
        expected_scene_id = f"SC{index:03d}"
        if scene_id != expected_scene_id or not SCENE_ID_PATTERN.fullmatch(scene_id):
            raise StoryboardInputError(f"scenes[{index - 1}].scene_id must be sequential ({expected_scene_id})")
        start = _seconds(raw_scene.get("start"), f"scenes[{index - 1}].start")
        end = _seconds(raw_scene.get("end"), f"scenes[{index - 1}].end")
        if end <= start:
            raise StoryboardInputError(f"scenes[{index - 1}] end must be after start")
        if abs(start - previous_end) > 0.01:
            raise StoryboardInputError(f"scenes[{index - 1}] must start at {_format_seconds(previous_end)} seconds")
        source = raw_scene.get("source")
        if not isinstance(source, list) or any(not isinstance(item, str) or not item for item in source):
            raise StoryboardInputError(f"scenes[{index - 1}].source must be a list of source IDs")
        if len(source) != len(set(source)):
            raise StoryboardInputError(f"scenes[{index - 1}].source must not contain duplicates")
        unknown_sources = set(source) - script_source_ids
        if unknown_sources:
            raise StoryboardInputError(f"scenes[{index - 1}] references unknown script source: {', '.join(sorted(unknown_sources))}")
        normalized.append(
            {
                "scene_id": scene_id,
                "start": start,
                "end": end,
                "spoken_text": _text(raw_scene.get("spoken_text"), f"scenes[{index - 1}].spoken_text"),
                "caption": _text(raw_scene.get("caption"), f"scenes[{index - 1}].caption"),
                "visual_description": _text(raw_scene.get("visual_description"), f"scenes[{index - 1}].visual_description"),
                "visual_type": _text(raw_scene.get("visual_type"), f"scenes[{index - 1}].visual_type"),
                "asset_query": _text(raw_scene.get("asset_query"), f"scenes[{index - 1}].asset_query"),
                "motion": _text(raw_scene.get("motion"), f"scenes[{index - 1}].motion"),
                "transition": _text(raw_scene.get("transition"), f"scenes[{index - 1}].transition"),
                "source": list(source),
            }
        )
        previous_end = end

    if abs(previous_end - script["target_duration_seconds"]) > 0.01:
        raise StoryboardInputError(
            f"last scene must end at script target {script['target_duration_seconds']} seconds, got {_format_seconds(previous_end)}"
        )
    actual_spoken = _canonical_spoken_text("".join(scene["spoken_text"] for scene in normalized))
    if actual_spoken != expected_spoken:
        raise StoryboardInputError("scene spoken_text must cover the completed script narration exactly and in order")
    cited_sources = {
        source_id
        for section in script["sections"]
        for source_id in section.get("source_ids", [])
    }
    visual_sources = {source_id for scene in normalized for source_id in scene["source"]}
    missing_sources = cited_sources - visual_sources
    if missing_sources:
        raise StoryboardInputError(
            f"storyboard must provide an evidence visual for cited sources: {', '.join(sorted(missing_sources))}"
        )
    return normalized


def render_storyboard_markdown(storyboard: dict[str, Any]) -> str:
    lines = [
        f"# 分镜：{storyboard['topic']}",
        "",
        f"- 成片时长：{storyboard['duration_seconds']} 秒",
        f"- 镜头数量：{len(storyboard['scenes'])}",
        "",
    ]
    for scene in storyboard["scenes"]:
        lines.extend(
            [
                f"## {scene['scene_id']} · {_format_seconds(scene['start'])}–{_format_seconds(scene['end'])} 秒",
                "",
                f"- 口播：{scene['spoken_text']}",
                f"- 字幕：{scene['caption']}",
                f"- 画面：{scene['visual_description']}",
                f"- 画面类型：{scene['visual_type']}",
                f"- 素材查询：{scene['asset_query']}",
                f"- 运镜：{scene['motion']}",
                f"- 转场：{scene['transition']}",
                f"- 来源：{'、'.join(f'[{source_id}]' for source_id in scene['source']) if scene['source'] else '无'}",
                "",
            ]
        )
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(content)
            if not content.endswith("\n"):
                file.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def write_storyboard_artifacts(directory: Path, project_id: str, payload: Any) -> dict[str, Any]:
    """Write a complete, traceable storyboard and advance SCRIPTED to STORYBOARDED."""
    directory = Path(directory)
    state = load_run_state(directory, project_id)
    if state["status"] != "SCRIPTED":
        raise StateError(f"storyboard generation requires status SCRIPTED; current status is {state['status']}")
    paths = [directory / output for output in OUTPUT_NAMES]
    for path in paths:
        if path.exists():
            raise StateError(f"refusing to overwrite existing storyboard artifact: {path}")
    script = _load_script(directory, project_id)
    scenes = _normalize_scenes(payload, script)
    storyboard = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "topic": script["topic"],
        "platform": script["platform"],
        "duration_seconds": script["target_duration_seconds"],
        "created_at": utc_timestamp(),
        "scenes": scenes,
    }
    written: list[Path] = []
    try:
        _atomic_write(paths[0], json.dumps(storyboard, ensure_ascii=False, indent=2))
        written.append(paths[0])
        _atomic_write(paths[1], render_storyboard_markdown(storyboard))
        written.append(paths[1])
        transition_project(
            directory,
            project_id,
            "STORYBOARDED",
            note="Validated timed storyboard with full narration and source traceability",
        )
    except Exception:
        for path in written:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise
    return {
        "project_id": project_id,
        "topic": storyboard["topic"],
        "scene_count": len(scenes),
        "duration_seconds": storyboard["duration_seconds"],
        "outputs": list(OUTPUT_NAMES),
        "state": "STORYBOARDED",
    }
