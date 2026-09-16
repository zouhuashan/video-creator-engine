#!/usr/bin/env python3
"""Create and validate scene scripts, performance units, and continuity deltas."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.novel_anime_project import MANIFEST_NAME, load_project, replace_project, utc_timestamp, validate_project  # noqa: E402
from scripts.novel_anime_repository import NovelAnimeRepository  # noqa: E402
from scripts.novel_episode_planning import load_episode_planning, readiness as episode_planning_readiness  # noqa: E402
from scripts.novel_source_catalog import CATALOG_RELATIVE_PATH, load_catalog  # noqa: E402
from scripts.novel_story_bible import load_bible, validate_bible  # noqa: E402

SCHEMA_PATH = ROOT / "schemas" / "novel-script-package.schema.json"
SCRIPT_ROOT = Path("writing-room/episodes")


class NovelEpisodeScriptError(ValueError):
    """Raised when a script or continuity delta violates the writing contract."""


def _review() -> dict[str, Any]:
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def _expected_input_snapshot(project: dict[str, Any], episode_id: str) -> str:
    episodes = sorted(project["episodes"], key=lambda item: (item["season_id"], item["episode_number"]))
    index = next((index for index, item in enumerate(episodes) if item["id"] == episode_id), None)
    if index is None:
        raise NovelEpisodeScriptError(f"unknown episode: {episode_id}")
    return "CNT-S01E000-END" if index == 0 else f"CNT-{episodes[index - 1]['id']}-END"


def build_script_package(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    planning = load_episode_planning(project_dir)
    now = utc_timestamp()
    scripts, deltas = [], []
    cards = {item["episode_id"]: item for item in planning["episode_cards"]}
    for episode in sorted(project["episodes"], key=lambda item: (item["season_id"], item["episode_number"])):
        episode_id = episode["id"]
        snapshot_id = _expected_input_snapshot(project, episode_id)
        scripts.append({"id": f"SCRIPT-{episode_id}", "episode_id": episode_id, "card_id": cards[episode_id]["id"], "status": "DRAFT", "input_snapshot_id": snapshot_id, "target_duration_seconds": episode["target_duration_seconds"], "scenes": [], "human_review": _review()})
        deltas.append({"id": f"DELTA-{episode_id}", "episode_id": episode_id, "status": "DRAFT", "input_snapshot_id": snapshot_id, "character_changes": [], "relationship_changes": [], "prop_changes": [], "open_foreshadowing_ids": [], "close_foreshadowing_ids": [], "timeline_position_id": None, "human_review": _review()})
    return validate_script_package(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "episode_planning_revision": planning["revision"], "revision": 1, "created_at": now, "updated_at": now, "episode_scripts": scripts, "continuity_deltas": deltas})


def _schema_validate(payload: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError:
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path) or "script_package"
        raise NovelEpisodeScriptError(f"script schema violation at {path}: {errors[0].message}")


def _unique(items: list[dict[str, Any]], field: str, pattern: str, label: str) -> set[str]:
    values: set[str] = set()
    for index, item in enumerate(items):
        value = str(item.get(field, ""))
        if not re.fullmatch(pattern, value) or value in values:
            raise NovelEpisodeScriptError(f"{label}[{index}].{field} is invalid or duplicated")
        values.add(value)
    return values


def _reference_sets(project_dir: Path, bible: dict[str, Any]) -> tuple[set[str], dict[str, set[str]]]:
    source_ids: set[str] = set()
    path = Path(project_dir) / CATALOG_RELATIVE_PATH
    if path.is_file():
        catalog = load_catalog(path)
        source_ids = {item["id"] for item in catalog["chapters"]} | {item["id"] for item in catalog["locators"]}
    story = {field: {item["id"] for item in bible[field]} for field in ("characters", "relationships", "locations", "props", "timeline", "foreshadowing")}
    story["all"] = {bible["world"]["id"]} | set().union(*(story[field] for field in story if field != "all"), {item["id"] for item in bible["rules"]})
    return source_ids, story


def _check_provenance(item: dict[str, Any], label: str, source_ids: set[str], story_ids: set[str]) -> None:
    value = item["provenance"]
    if set(value["source_refs"]) - source_ids or set(value["story_refs"]) - story_ids:
        raise NovelEpisodeScriptError(f"{label} has unknown provenance references")
    if value["kind"] == "SOURCE" and not (value["source_refs"] or value["story_refs"]):
        raise NovelEpisodeScriptError(f"{label} requires traceable provenance")
    if value["kind"] == "ORIGINAL" and not value["note"].strip():
        raise NovelEpisodeScriptError(f"{label} original content requires a note")
    if value["kind"] == "UNSET":
        raise NovelEpisodeScriptError(f"{label} lacks provenance")


def _available_snapshot_ids(bible: dict[str, Any]) -> set[str]:
    return {item["id"] for item in bible["continuity_ledger"]["snapshots"]}


def validate_script_package(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NovelEpisodeScriptError("script package must be an object")
    package = deepcopy(payload)
    _schema_validate(package)
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    planning = load_episode_planning(project_dir)
    bible = load_bible(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]:
        raise NovelEpisodeScriptError("script package does not match the project")
    if package["episode_planning_revision"] != planning["revision"]:
        raise NovelEpisodeScriptError("script package episode_planning_revision is stale")
    episode_ids = {item["id"] for item in project["episodes"]}
    script_episodes = {item["episode_id"] for item in package["episode_scripts"]}
    delta_episodes = {item["episode_id"] for item in package["continuity_deltas"]}
    if script_episodes != episode_ids or delta_episodes != episode_ids or len(package["episode_scripts"]) != len(episode_ids) or len(package["continuity_deltas"]) != len(episode_ids):
        raise NovelEpisodeScriptError("scripts and continuity deltas must cover every episode exactly once")
    _unique(package["episode_scripts"], "id", r"SCRIPT-S\d{2}E\d{3}", "episode_scripts")
    _unique(package["continuity_deltas"], "id", r"DELTA-S\d{2}E\d{3}", "continuity_deltas")
    cards = {item["episode_id"]: item for item in planning["episode_cards"]}
    episodes = {item["id"]: item for item in project["episodes"]}
    source_ids, story = _reference_sets(project_dir, bible)
    available_snapshots = _available_snapshot_ids(bible)
    for script in package["episode_scripts"]:
        episode_id = script["episode_id"]
        if script["id"] != f"SCRIPT-{episode_id}" or script["card_id"] != cards[episode_id]["id"] or script["input_snapshot_id"] != _expected_input_snapshot(project, episode_id):
            raise NovelEpisodeScriptError(f"script {script['id']} has invalid identity or upstream references")
        if script["target_duration_seconds"] != episodes[episode_id]["target_duration_seconds"]:
            raise NovelEpisodeScriptError(f"script {script['id']} duration differs from the episode")
        scene_ids = _unique(script["scenes"], "id", rf"{episode_id}-SC\d{{3}}", f"{script['id']}.scenes")
        if [item["sequence"] for item in sorted(script["scenes"], key=lambda item: item["sequence"])] != list(range(1, len(script["scenes"]) + 1)):
            raise NovelEpisodeScriptError(f"script {script['id']} scene sequence must be contiguous")
        beat_ids = {item["id"] for item in cards[episode_id]["beats"]}
        kinds: set[str] = set()
        estimated = 0.0
        for scene in script["scenes"]:
            if scene["location_id"] and scene["location_id"] not in story["locations"] or set(scene["character_ids"]) - story["characters"]:
                raise NovelEpisodeScriptError(f"scene {scene['id']} has unknown story references")
            _check_provenance(scene, scene["id"], source_ids, story["all"])
            units = sorted(scene["units"], key=lambda item: item["sequence"])
            _unique(units, "id", rf"UNIT-{scene['id']}-\d{{3}}", f"{scene['id']}.units")
            if [item["sequence"] for item in units] != list(range(1, len(units) + 1)):
                raise NovelEpisodeScriptError(f"scene {scene['id']} unit sequence must be contiguous")
            for unit in units:
                kinds.add(unit["kind"])
                estimated += unit["estimated_duration_seconds"]
                if unit["beat_ref"] and unit["beat_ref"] not in beat_ids:
                    raise NovelEpisodeScriptError(f"unit {unit['id']} references an unknown episode beat")
                if unit["kind"] == "DIALOGUE" and (unit["speaker_character_id"] not in scene["character_ids"] or unit["emotion"] is None):
                    raise NovelEpisodeScriptError(f"dialogue {unit['id']} requires an in-scene speaker and emotion")
                if unit["kind"] == "NARRATION" and (unit["speaker_character_id"] is not None or unit["emotion"] is None):
                    raise NovelEpisodeScriptError(f"narration {unit['id']} requires emotion and no character speaker")
                if unit["kind"] == "SFX" and unit["sound"] is None:
                    raise NovelEpisodeScriptError(f"sound effect {unit['id']} requires a sound cue")
                if unit["kind"] not in {"DIALOGUE"} and unit["speaker_character_id"] is not None:
                    raise NovelEpisodeScriptError(f"unit {unit['id']} cannot have a character speaker")
                _check_provenance(unit, unit["id"], source_ids, story["all"])
        if estimated > script["target_duration_seconds"] * 1.15:
            raise NovelEpisodeScriptError(f"script {script['id']} exceeds the duration budget")
        if script["status"] == "READY":
            if cards[episode_id]["status"] != "READY" or script["input_snapshot_id"] not in available_snapshots or not scene_ids or not ({"ACTION", "VISUAL"} & kinds) or not ({"DIALOGUE", "NARRATION"} & kinds):
                raise NovelEpisodeScriptError(f"READY script {script['id']} is incomplete or lacks its continuity input")
    for delta in package["continuity_deltas"]:
        episode_id = delta["episode_id"]
        if delta["id"] != f"DELTA-{episode_id}" or delta["input_snapshot_id"] != _expected_input_snapshot(project, episode_id):
            raise NovelEpisodeScriptError(f"delta {delta['id']} has invalid identity or input")
        _unique(delta["character_changes"], "character_id", r"CHR-[A-Z0-9-]+", f"{delta['id']}.character_changes")
        _unique(delta["relationship_changes"], "relationship_id", r"REL-[A-Z0-9-]+", f"{delta['id']}.relationship_changes")
        _unique(delta["prop_changes"], "prop_id", r"PROP-[A-Z0-9-]+", f"{delta['id']}.prop_changes")
        for change in delta["character_changes"]:
            if change["character_id"] not in story["characters"] or (change["set_location_id"] and change["set_location_id"] not in story["locations"]) or set(change["add_carried_prop_ids"] + change["remove_carried_prop_ids"]) - story["props"]:
                raise NovelEpisodeScriptError(f"delta {delta['id']} has invalid character references")
            for add, remove, label in ((change["add_carried_prop_ids"], change["remove_carried_prop_ids"], "props"), (change["add_injuries"], change["remove_injuries"], "injuries")):
                if set(add) & set(remove):
                    raise NovelEpisodeScriptError(f"delta {delta['id']} both adds and removes the same {label}")
        if any(item["relationship_id"] not in story["relationships"] for item in delta["relationship_changes"]):
            raise NovelEpisodeScriptError(f"delta {delta['id']} has unknown relationship changes")
        if any(item["prop_id"] not in story["props"] or (item["location_id"] and item["location_id"] not in story["locations"]) or (item["holder_character_id"] and item["holder_character_id"] not in story["characters"]) for item in delta["prop_changes"]):
            raise NovelEpisodeScriptError(f"delta {delta['id']} has unknown prop changes")
        if set(delta["open_foreshadowing_ids"] + delta["close_foreshadowing_ids"]) - story["foreshadowing"] or set(delta["open_foreshadowing_ids"]) & set(delta["close_foreshadowing_ids"]):
            raise NovelEpisodeScriptError(f"delta {delta['id']} has invalid foreshadowing changes")
        if delta["timeline_position_id"] and delta["timeline_position_id"] not in story["timeline"]:
            raise NovelEpisodeScriptError(f"delta {delta['id']} has an unknown timeline position")
        if delta["status"] == "READY" and delta["input_snapshot_id"] not in available_snapshots:
            raise NovelEpisodeScriptError(f"READY delta {delta['id']} lacks its continuity input")
    return package


def _atomic(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise NovelEpisodeScriptError(f"refusing to overwrite script file: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=".episode-script.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def write_script_package(project_dir: Path, package: dict[str, Any], *, overwrite: bool = False) -> list[Path]:
    project_dir = Path(project_dir).expanduser().resolve()
    package = validate_script_package(project_dir, package)
    common = {key: package[key] for key in ("schema_version", "project_id", "ip_id", "episode_planning_revision", "revision", "created_at", "updated_at")}
    deltas = {item["episode_id"]: item for item in package["continuity_deltas"]}
    paths: list[Path] = []
    for script in package["episode_scripts"]:
        directory = project_dir / SCRIPT_ROOT / script["episode_id"]
        script_path = directory / "script.json"
        delta_path = directory / "continuity-delta.json"
        _atomic(script_path, {**common, "episode_script": script}, overwrite=overwrite)
        _atomic(delta_path, {**common, "continuity_delta": deltas[script["episode_id"]]}, overwrite=overwrite)
        paths.extend((script_path, delta_path))
    return paths


def load_script_package(project_dir: Path) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    project = load_project(project_dir / MANIFEST_NAME)
    common_keys = ("schema_version", "project_id", "ip_id", "episode_planning_revision", "revision", "created_at", "updated_at")
    package: dict[str, Any] = {}
    scripts, deltas = [], []
    for episode in sorted(project["episodes"], key=lambda item: (item["season_id"], item["episode_number"])):
        directory = project_dir / SCRIPT_ROOT / episode["id"]
        try:
            script_part = json.loads((directory / "script.json").read_text(encoding="utf-8"))
            delta_part = json.loads((directory / "continuity-delta.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise NovelEpisodeScriptError(f"cannot read episode script files for {episode['id']}: {error}") from error
        if not package:
            package.update({key: script_part.get(key) for key in common_keys})
        if any(script_part.get(key) != package[key] or delta_part.get(key) != package[key] for key in common_keys):
            raise NovelEpisodeScriptError("episode script files have inconsistent metadata")
        scripts.append(script_part.get("episode_script"))
        deltas.append(delta_part.get("continuity_delta"))
    package["episode_scripts"], package["continuity_deltas"] = scripts, deltas
    return validate_script_package(project_dir, package)


def _apply_list(current: list[str], additions: list[str], removals: list[str], label: str) -> list[str]:
    missing = set(removals) - set(current)
    if missing:
        raise NovelEpisodeScriptError(f"cannot remove absent {label}: {sorted(missing)}")
    return sorted((set(current) - set(removals)) | set(additions))


def preview_continuity_snapshot(project_dir: Path, episode_id: str) -> dict[str, Any]:
    package = load_script_package(project_dir)
    bible = load_bible(project_dir)
    delta = next((item for item in package["continuity_deltas"] if item["episode_id"] == episode_id), None)
    if delta is None:
        raise NovelEpisodeScriptError(f"unknown episode delta: {episode_id}")
    prior = next((item for item in bible["continuity_ledger"]["snapshots"] if item["id"] == delta["input_snapshot_id"]), None)
    if prior is None:
        raise NovelEpisodeScriptError(f"continuity input is missing: {delta['input_snapshot_id']}")
    result = deepcopy(prior)
    result.update({"id": f"CNT-{episode_id}-END", "episode_id": episode_id, "sequence": prior["sequence"] + 1, "prior_snapshot_id": prior["id"], "continuity_delta_ref": f"writing-room/episodes/{episode_id}/continuity-delta.json", "human_review": _review()})
    character_states = {item["character_id"]: item for item in result["character_states"]}
    for change in delta["character_changes"]:
        if change["character_id"] not in character_states:
            raise NovelEpisodeScriptError(f"continuity input lacks character state: {change['character_id']}")
        state = character_states[change["character_id"]]
        if change["set_location_id"] is not None: state["location_id"] = change["set_location_id"]
        if change["set_costume_id"] is not None: state["costume_id"] = change["set_costume_id"]
        state["carried_prop_ids"] = _apply_list(state["carried_prop_ids"], change["add_carried_prop_ids"], change["remove_carried_prop_ids"], "carried props")
        state["injuries"] = _apply_list(state["injuries"], change["add_injuries"], change["remove_injuries"], "injuries")
        state["knowledge"] = sorted(set(state["knowledge"]) | set(change["add_knowledge"]))
        if change["set_emotional_state"] is not None: state["emotional_state"] = change["set_emotional_state"]
    relationship_states = {item["relationship_id"]: item for item in result["relationship_states"]}
    for change in delta["relationship_changes"]: relationship_states[change["relationship_id"]] = deepcopy(change)
    prop_states = {item["prop_id"]: item for item in result["prop_states"]}
    for change in delta["prop_changes"]: prop_states[change["prop_id"]] = deepcopy(change)
    result["relationship_states"] = list(relationship_states.values())
    result["prop_states"] = list(prop_states.values())
    result["open_foreshadowing_ids"] = _apply_list(result["open_foreshadowing_ids"], delta["open_foreshadowing_ids"], delta["close_foreshadowing_ids"], "foreshadowing")
    if delta["timeline_position_id"] is not None: result["timeline_position_id"] = delta["timeline_position_id"]
    test_bible = deepcopy(bible)
    test_bible["continuity_ledger"]["snapshots"].append(result)
    validate_bible(project_dir, test_bible)
    return result


def sync_manifest_scenes(project_dir: Path, package: dict[str, Any]) -> dict[str, int]:
    project_dir = Path(project_dir).expanduser().resolve()
    package = validate_script_package(project_dir, package)
    project = load_project(project_dir / MANIFEST_NAME)
    scenes = []
    by_episode: dict[str, list[str]] = {item["id"]: [] for item in project["episodes"]}
    for script in package["episode_scripts"]:
        for scene in script["scenes"]:
            scenes.append({"id": scene["id"], "title": scene["title"], "revision": package["revision"], "status": "DRAFT", "input_refs": [], "source_refs": list(scene["provenance"]["source_refs"]), "provider": None, "human_review": {key: scene["human_review"][key] for key in ("required", "status", "reviewed_at", "reviewed_by")}, "episode_id": script["episode_id"], "scene_number": scene["sequence"], "location_ref": scene["location_id"], "character_refs": list(scene["character_ids"]), "shot_ids": []})
            by_episode[script["episode_id"]].append(scene["id"])
    project["scenes"] = scenes
    for episode in project["episodes"]: episode["scene_ids"] = by_episode[episode["id"]]
    project["revision"] += 1
    project["updated_at"] = utc_timestamp()
    replace_project(project_dir, validate_project(project))
    repository = NovelAnimeRepository(project_dir)
    if repository.db_path.is_file(): repository.sync_manifest()
    return {"scenes": len(scenes), "scripted_episodes": sum(1 for ids in by_episode.values() if ids)}


def summary(project_dir: Path) -> dict[str, Any] | None:
    try:
        package = load_script_package(project_dir)
        bible = load_bible(project_dir)
    except (NovelEpisodeScriptError, ValueError):
        return None
    available = _available_snapshot_ids(bible)
    return {"revision": package["revision"], "script_count": len(package["episode_scripts"]), "ready_script_count": sum(1 for item in package["episode_scripts"] if item["status"] == "READY"), "scene_count": sum(len(item["scenes"]) for item in package["episode_scripts"]), "unit_count": sum(len(scene["units"]) for item in package["episode_scripts"] for scene in item["scenes"]), "ready_delta_count": sum(1 for item in package["continuity_deltas"] if item["status"] == "READY"), "available_input_count": sum(1 for item in package["episode_scripts"] if item["input_snapshot_id"] in available), "upstream_ready": episode_planning_readiness(project_dir)["ready"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "validate", "preview-delta"))
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--episode-id")
    args = parser.parse_args()
    try:
        if args.command == "create":
            package = build_script_package(args.project_dir)
            files = write_script_package(args.project_dir, package)
            result: Any = {"files": [path.relative_to(Path(args.project_dir).resolve()).as_posix() for path in files], "manifest": sync_manifest_scenes(args.project_dir, package)}
        elif args.command == "validate": result = summary(args.project_dir)
        else:
            if not args.episode_id: raise NovelEpisodeScriptError("preview-delta requires --episode-id")
            result = preview_continuity_snapshot(args.project_dir, args.episode_id)
    except (NovelEpisodeScriptError, OSError, ValueError) as error:
        print(f"novel_episode_script: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
