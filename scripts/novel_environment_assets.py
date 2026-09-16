#!/usr/bin/env python3
"""Manage reusable location, weather/light variants, props, and scene assignments."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp  # noqa: E402
from scripts.novel_anime_repository import NovelAnimeRepository  # noqa: E402
from scripts.novel_episode_script import load_script_package  # noqa: E402
from scripts.novel_story_bible import load_bible  # noqa: E402
from scripts.novel_visual_bible import load_visual_bible, readiness as visual_readiness  # noqa: E402

SCHEMA_PATH = ROOT / "schemas" / "novel-environment-assets.schema.json"
OUTPUT = Path("visual-bible/environment-assets.json")


class NovelEnvironmentAssetError(ValueError):
    """Raised when environment or prop assets break spatial continuity."""


def _review() -> dict[str, Any]: return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def continuity_signature(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_environment_assets(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); bible = load_bible(project_dir); visual = load_visual_bible(project_dir); scripts = load_script_package(project_dir); now = utc_timestamp(); locations = []; props = []
    for location in bible["locations"]:
        layout = {"orientation": "", "scale": "", "zones": [], "entrances": [], "fixed_landmarks": []}; signature = continuity_signature(layout)
        locations.append({"id": f"LDES-{location['id']}", "location_id": location["id"], "status": "DRAFT", "layout": layout, "visual_language": "", "base_palette_swatch_ids": [], "continuity_signature": signature, "camera_views": [], "variants": [], "prompt_template": {"positive": "", "negative": ""}, "human_review": _review()})
    for prop in bible["props"]:
        identity = {"dimensions": "", "materials": [], "distinctive_marks": [], "interaction_rules": []}; signature = continuity_signature(identity)
        props.append({"id": f"PDES-{prop['id']}", "prop_id": prop["id"], "status": "DRAFT", **identity, "palette_swatch_ids": [], "continuity_signature": signature, "states": [], "default_state_id": None, "prompt_template": {"positive": "", "negative": ""}, "human_review": _review()})
    assignments = []
    for script in scripts["episode_scripts"]:
        for scene in script["scenes"]:
            if scene["location_id"]:
                assignments.append({"scene_id": scene["id"], "episode_id": script["episode_id"], "location_id": scene["location_id"], "location_variant_id": None, "weather": "", "time_of_day": scene["time_of_day"], "lighting": "", "prop_state_ids": []})
    return validate_environment_assets(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "story_bible_revision": bible["revision"], "visual_bible_revision": visual["revision"], "revision": 1, "created_at": now, "updated_at": now, "location_designs": locations, "prop_designs": props, "scene_environment_assignments": assignments})


def _schema(payload: dict[str, Any]) -> None:
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path) or "environment_assets"; raise NovelEnvironmentAssetError(f"environment asset schema violation at {path}: {errors[0].message}")


def _unique(items: list[dict[str, Any]], field: str, label: str) -> set[str]:
    values: set[str] = set()
    for index, item in enumerate(items):
        value = str(item[field])
        if value in values: raise NovelEnvironmentAssetError(f"duplicate {label} {value} at index {index}")
        values.add(value)
    return values


def _assets(project_dir: Path, project: dict[str, Any]) -> set[str]:
    result = {item["id"] for item in project["assets"]}; repository = NovelAnimeRepository(project_dir)
    if repository.db_path.is_file(): result |= repository.current_asset_ids()
    return result


def validate_environment_assets(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelEnvironmentAssetError("environment assets must be an object")
    package = deepcopy(payload); _schema(package); project = load_project(Path(project_dir) / MANIFEST_NAME); bible = load_bible(project_dir); visual = load_visual_bible(project_dir); scripts = load_script_package(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]: raise NovelEnvironmentAssetError("environment assets do not match the project")
    if package["story_bible_revision"] != bible["revision"] or package["visual_bible_revision"] != visual["revision"]: raise NovelEnvironmentAssetError("environment asset upstream revisions are stale")
    location_ids = {item["id"] for item in bible["locations"]}; prop_ids = {item["id"] for item in bible["props"]}; character_ids = {item["id"] for item in bible["characters"]}; swatch_ids = {item["id"] for item in visual["color_script"]["swatches"]}; assets = _assets(project_dir, project)
    locations = package["location_designs"]; props = package["prop_designs"]
    if {item["location_id"] for item in locations} != location_ids or len(locations) != len(location_ids): raise NovelEnvironmentAssetError("location designs must cover every story location")
    if {item["prop_id"] for item in props} != prop_ids or len(props) != len(prop_ids): raise NovelEnvironmentAssetError("prop designs must cover every story prop")
    variant_ids: set[str] = set(); state_ids: set[str] = set()
    for design in locations:
        if design["id"] != f"LDES-{design['location_id']}" or design["continuity_signature"] != continuity_signature(design["layout"]): raise NovelEnvironmentAssetError(f"location signature drift for {design['location_id']}")
        if set(design["base_palette_swatch_ids"]) - swatch_ids: raise NovelEnvironmentAssetError(f"{design['id']} references unknown palette swatches")
        _unique(design["camera_views"], "id", f"{design['id']} camera view"); local_variants = _unique(design["variants"], "id", f"{design['id']} variant")
        if variant_ids & local_variants: raise NovelEnvironmentAssetError("location variant IDs must be globally unique")
        variant_ids |= local_variants
        for item in [*design["camera_views"], *design["variants"]]:
            if item["continuity_signature"] != design["continuity_signature"]: raise NovelEnvironmentAssetError(f"{design['id']} child continuity signature drift")
            if item["status"] == "SELECTED" and (not item["asset_id"] or item["asset_id"] not in assets): raise NovelEnvironmentAssetError(f"{design['id']} selected item requires a registered asset")
        if any(set(item["palette_swatch_ids"]) - swatch_ids for item in design["variants"]): raise NovelEnvironmentAssetError(f"{design['id']} variant uses unknown palette swatches")
        if design["status"] == "READY" and (not design["layout"]["orientation"] or not design["layout"]["scale"] or not design["layout"]["zones"] or not design["layout"]["fixed_landmarks"] or not design["visual_language"] or not design["base_palette_swatch_ids"] or not any(item["status"] == "SELECTED" for item in design["camera_views"]) or not any(item["status"] == "SELECTED" for item in design["variants"]) or not design["prompt_template"]["positive"] or not design["prompt_template"]["negative"]): raise NovelEnvironmentAssetError(f"READY {design['id']} is incomplete")
    for design in props:
        identity = {key: design[key] for key in ("dimensions", "materials", "distinctive_marks", "interaction_rules")}
        if design["id"] != f"PDES-{design['prop_id']}" or design["continuity_signature"] != continuity_signature(identity): raise NovelEnvironmentAssetError(f"prop signature drift for {design['prop_id']}")
        if set(design["palette_swatch_ids"]) - swatch_ids: raise NovelEnvironmentAssetError(f"{design['id']} references unknown palette swatches")
        local_states = _unique(design["states"], "id", f"{design['id']} state")
        if state_ids & local_states: raise NovelEnvironmentAssetError("prop state IDs must be globally unique")
        state_ids |= local_states
        for state in design["states"]:
            if state["continuity_signature"] != design["continuity_signature"] or (state["holder_character_id"] and state["holder_character_id"] not in character_ids) or (state["location_id"] and state["location_id"] not in location_ids): raise NovelEnvironmentAssetError(f"{design['id']} state has continuity drift or unknown holder/location")
            if state["status"] == "SELECTED" and (not state["asset_id"] or state["asset_id"] not in assets): raise NovelEnvironmentAssetError(f"{design['id']} selected state requires a registered asset")
        if design["default_state_id"] is not None and design["default_state_id"] not in local_states: raise NovelEnvironmentAssetError(f"{design['id']} has unknown default state")
        if design["status"] == "READY" and (not design["dimensions"] or not design["materials"] or not design["distinctive_marks"] or not design["interaction_rules"] or not design["palette_swatch_ids"] or design["default_state_id"] is None or not next(item for item in design["states"] if item["id"] == design["default_state_id"])["status"] == "SELECTED" or not design["prompt_template"]["positive"] or not design["prompt_template"]["negative"]): raise NovelEnvironmentAssetError(f"READY {design['id']} is incomplete")
    expected_scenes = {scene["id"]: (script["episode_id"], scene["location_id"], scene["time_of_day"]) for script in scripts["episode_scripts"] for scene in script["scenes"] if scene["location_id"]}
    assignments = package["scene_environment_assignments"]
    if {item["scene_id"] for item in assignments} != set(expected_scenes) or len(assignments) != len(expected_scenes): raise NovelEnvironmentAssetError("environment assignments must cover every located script scene")
    variant_map = {item["id"]: item for design in locations for item in design["variants"]}
    for assignment in assignments:
        episode_id, location_id, time_of_day = expected_scenes[assignment["scene_id"]]
        if assignment["episode_id"] != episode_id or assignment["location_id"] != location_id or set(assignment["prop_state_ids"]) - state_ids: raise NovelEnvironmentAssetError(f"assignment {assignment['scene_id']} has invalid references")
        if assignment["location_variant_id"]:
            variant = variant_map.get(assignment["location_variant_id"])
            if not variant or assignment["location_variant_id"] not in variant_ids or assignment["time_of_day"] != variant["time_of_day"] or assignment["weather"] != variant["weather"] or assignment["lighting"] != variant["lighting"]: raise NovelEnvironmentAssetError(f"assignment {assignment['scene_id']} does not match its location variant")
    return package


def _atomic(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite: raise NovelEnvironmentAssetError(f"refusing to overwrite environment assets: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=".environment-assets.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file: json.dump(payload, file, ensure_ascii=False, indent=2); file.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


def write_environment_assets(project_dir: Path, package: dict[str, Any], overwrite: bool = False) -> Path:
    project_dir = Path(project_dir).expanduser().resolve(); package = validate_environment_assets(project_dir, package); output = project_dir / OUTPUT; _atomic(output, package, overwrite); return output


def load_environment_assets(project_dir: Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve() / OUTPUT
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: raise NovelEnvironmentAssetError(f"cannot read environment assets: {error}") from error
    return validate_environment_assets(project_dir, payload)


def readiness(project_dir: Path) -> dict[str, Any]:
    package = load_environment_assets(project_dir); blockers = list(visual_readiness(project_dir)["blockers"])
    for design in [*package["location_designs"], *package["prop_designs"]]:
        if design["status"] != "READY" or design["human_review"]["status"] != "APPROVED": blockers.append(f"{design['id']} is not ready and approved")
    if any(item["location_variant_id"] is None for item in package["scene_environment_assignments"]): blockers.append("one or more scenes lack an environment variant")
    return {"ready": not blockers, "blockers": blockers}


def summary(project_dir: Path) -> dict[str, Any] | None:
    try: package = load_environment_assets(project_dir); state = readiness(project_dir)
    except (NovelEnvironmentAssetError, ValueError): return None
    return {"revision": package["revision"], "location_count": len(package["location_designs"]), "ready_location_count": sum(1 for item in package["location_designs"] if item["status"] == "READY"), "location_variant_count": sum(len(item["variants"]) for item in package["location_designs"]), "prop_count": len(package["prop_designs"]), "ready_prop_count": sum(1 for item in package["prop_designs"] if item["status"] == "READY"), "prop_state_count": sum(len(item["states"]) for item in package["prop_designs"]), "scene_assignment_count": len(package["scene_environment_assignments"]), "ready": state["ready"], "blocker_count": len(state["blockers"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try:
        if args.command == "create": result: Any = {"output": write_environment_assets(args.project_dir, build_environment_assets(args.project_dir)).relative_to(Path(args.project_dir).resolve()).as_posix()}
        else: result = summary(args.project_dir)
    except (NovelEnvironmentAssetError, OSError, ValueError) as error: print(f"novel_environment_assets: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
