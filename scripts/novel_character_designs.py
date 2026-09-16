#!/usr/bin/env python3
"""Manage character identity contracts, turnarounds, expressions, and costumes."""

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
from scripts.novel_story_bible import load_bible  # noqa: E402
from scripts.novel_visual_bible import load_visual_bible, readiness as visual_readiness  # noqa: E402

SCHEMA_PATH = ROOT / "schemas" / "novel-character-designs.schema.json"
OUTPUT = Path("visual-bible/character-designs.json")
REQUIRED_VIEWS = {"FRONT", "SIDE", "BACK", "CLOSEUP"}
REQUIRED_EXPRESSIONS = {"NEUTRAL", "HAPPY", "ANGRY", "SAD", "SURPRISED"}


class NovelCharacterDesignError(ValueError):
    """Raised when character identity or selected assets are inconsistent."""


def _review() -> dict[str, Any]: return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def identity_signature(identity: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _empty_identity() -> dict[str, Any]:
    return {"height_heads": None, "body_type": "", "face_shape": "", "skin_tone": "", "hair_shape": "", "hair_color": "", "eye_shape": "", "eye_color": "", "distinguishing_marks": [], "immutable_features": [], "negative_constraints": []}


def build_character_designs(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); bible = load_bible(project_dir); visual = load_visual_bible(project_dir); now = utc_timestamp(); designs = []
    for character in bible["characters"]:
        identity = _empty_identity(); signature = identity_signature(identity); character_code = character["id"]
        designs.append({"id": f"CDES-{character_code}", "character_id": character_code, "status": "DRAFT", "identity": identity, "identity_signature": signature, "palette_swatch_ids": [], "turnarounds": [{"view": view, "status": "PLANNED", "asset_id": None, "identity_signature": signature, "prompt_note": ""} for view in ("FRONT", "THREE_QUARTER", "SIDE", "BACK", "CLOSEUP")], "expressions": [{"id": f"EXPR-{character_code.removeprefix('CHR-')}-{emotion}", "emotion": emotion, "intensity": 0.5 if emotion != "NEUTRAL" else 0.0, "status": "PLANNED", "asset_id": None, "identity_signature": signature, "performance_note": ""} for emotion in ("NEUTRAL", "HAPPY", "ANGRY", "SAD", "SURPRISED")], "costumes": [], "default_costume_id": None, "voice_profile_id": None, "prompt_template": {"positive": "", "negative": ""}, "human_review": _review()})
    return validate_character_designs(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "visual_bible_revision": visual["revision"], "revision": 1, "created_at": now, "updated_at": now, "character_designs": designs})


def _schema(payload: dict[str, Any]) -> None:
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path) or "character_designs"; raise NovelCharacterDesignError(f"character design schema violation at {path}: {errors[0].message}")


def _unique(items: list[dict[str, Any]], field: str, label: str) -> set[str]:
    values: set[str] = set()
    for index, item in enumerate(items):
        value = str(item[field])
        if value in values: raise NovelCharacterDesignError(f"duplicate {label} {value} at index {index}")
        values.add(value)
    return values


def _registered_assets(project_dir: Path, project: dict[str, Any]) -> set[str]:
    result = {item["id"] for item in project["assets"]}; repository = NovelAnimeRepository(project_dir)
    if repository.db_path.is_file(): result |= repository.current_asset_ids()
    return result


def validate_character_designs(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelCharacterDesignError("character designs must be an object")
    package = deepcopy(payload); _schema(package); project = load_project(Path(project_dir) / MANIFEST_NAME); bible = load_bible(project_dir); visual = load_visual_bible(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]: raise NovelCharacterDesignError("character designs do not match the project")
    if package["visual_bible_revision"] != visual["revision"]: raise NovelCharacterDesignError("character designs visual_bible_revision is stale")
    character_ids = {item["id"] for item in bible["characters"]}; designs = package["character_designs"]
    if {item["character_id"] for item in designs} != character_ids or len(designs) != len(character_ids): raise NovelCharacterDesignError("character designs must cover every story character exactly once")
    _unique(designs, "id", "character design ID"); swatch_ids = {item["id"] for item in visual["color_script"]["swatches"]}; assets = _registered_assets(project_dir, project)
    for design in designs:
        if design["id"] != f"CDES-{design['character_id']}": raise NovelCharacterDesignError(f"invalid design ID for {design['character_id']}")
        signature = identity_signature(design["identity"])
        if design["identity_signature"] != signature: raise NovelCharacterDesignError(f"identity signature drift for {design['character_id']}")
        if set(design["palette_swatch_ids"]) - swatch_ids: raise NovelCharacterDesignError(f"{design['id']} references unknown palette swatches")
        views = _unique(design["turnarounds"], "view", f"{design['id']} turnaround view"); expression_ids = _unique(design["expressions"], "id", f"{design['id']} expression ID"); costume_ids = _unique(design["costumes"], "id", f"{design['id']} costume ID")
        for item in [*design["turnarounds"], *design["expressions"], *design["costumes"]]:
            if item["identity_signature"] != signature: raise NovelCharacterDesignError(f"{design['id']} child asset identity signature drift")
            if item["status"] == "SELECTED" and (not item["asset_id"] or item["asset_id"] not in assets): raise NovelCharacterDesignError(f"{design['id']} selected item requires a registered asset")
        if any(set(item["palette_swatch_ids"]) - swatch_ids for item in design["costumes"]): raise NovelCharacterDesignError(f"{design['id']} costume references unknown palette swatches")
        defaults = [item for item in design["costumes"] if item["is_default"]]
        if design["default_costume_id"] is not None and (design["default_costume_id"] not in costume_ids or len(defaults) != 1 or defaults[0]["id"] != design["default_costume_id"]): raise NovelCharacterDesignError(f"{design['id']} has an inconsistent default costume")
        if design["status"] == "READY":
            required_identity = ("body_type", "face_shape", "skin_tone", "hair_shape", "hair_color", "eye_shape", "eye_color")
            if design["identity"]["height_heads"] is None or any(not design["identity"][field].strip() for field in required_identity) or not design["identity"]["immutable_features"] or not design["identity"]["negative_constraints"]: raise NovelCharacterDesignError(f"READY {design['id']} has an incomplete identity contract")
            selected_views = {item["view"] for item in design["turnarounds"] if item["status"] == "SELECTED"}
            selected_expressions = {item["emotion"] for item in design["expressions"] if item["status"] == "SELECTED"}
            if not REQUIRED_VIEWS <= selected_views or not REQUIRED_EXPRESSIONS <= selected_expressions: raise NovelCharacterDesignError(f"READY {design['id']} lacks required selected views or expressions")
            if design["default_costume_id"] is None or defaults[0]["status"] != "SELECTED" or not design["palette_swatch_ids"] or not design["prompt_template"]["positive"].strip() or not design["prompt_template"]["negative"].strip(): raise NovelCharacterDesignError(f"READY {design['id']} lacks costume, palette, or prompt contracts")
    return package


def check_identity_observation(design: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    identity = design["identity"]; issues = []
    for field in ("body_type", "face_shape", "skin_tone", "hair_shape", "hair_color", "eye_shape", "eye_color"):
        if observation.get(field) != identity.get(field): issues.append({"field": field, "expected": identity.get(field), "observed": observation.get(field)})
    expected_marks = set(identity["distinguishing_marks"]); observed_marks = set(observation.get("distinguishing_marks", []))
    if expected_marks != observed_marks: issues.append({"field": "distinguishing_marks", "expected": sorted(expected_marks), "observed": sorted(observed_marks)})
    height = observation.get("height_heads")
    if height is None or identity["height_heads"] is None or abs(float(height) - float(identity["height_heads"])) > 0.25: issues.append({"field": "height_heads", "expected": identity["height_heads"], "observed": height})
    return {"character_id": design["character_id"], "identity_signature": design["identity_signature"], "pass": not issues, "issues": issues}


def _atomic(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite: raise NovelCharacterDesignError(f"refusing to overwrite character designs: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=".character-designs.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file: json.dump(payload, file, ensure_ascii=False, indent=2); file.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


def write_character_designs(project_dir: Path, package: dict[str, Any], overwrite: bool = False) -> Path:
    project_dir = Path(project_dir).expanduser().resolve(); package = validate_character_designs(project_dir, package); output = project_dir / OUTPUT; _atomic(output, package, overwrite); return output


def load_character_designs(project_dir: Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve() / OUTPUT
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: raise NovelCharacterDesignError(f"cannot read character designs: {error}") from error
    return validate_character_designs(project_dir, payload)


def readiness(project_dir: Path) -> dict[str, Any]:
    package = load_character_designs(project_dir); blockers = list(visual_readiness(project_dir)["blockers"])
    if not package["character_designs"]: blockers.append("no story characters are available for design")
    for design in package["character_designs"]:
        if design["status"] != "READY" or design["human_review"]["status"] != "APPROVED": blockers.append(f"{design['id']} is not ready and approved")
    return {"ready": not blockers, "blockers": blockers}


def summary(project_dir: Path) -> dict[str, Any] | None:
    try: package = load_character_designs(project_dir); state = readiness(project_dir)
    except (NovelCharacterDesignError, ValueError): return None
    designs = package["character_designs"]
    return {"revision": package["revision"], "character_count": len(designs), "ready_character_count": sum(1 for item in designs if item["status"] == "READY"), "selected_turnaround_count": sum(1 for design in designs for item in design["turnarounds"] if item["status"] == "SELECTED"), "selected_expression_count": sum(1 for design in designs for item in design["expressions"] if item["status"] == "SELECTED"), "costume_count": sum(len(item["costumes"]) for item in designs), "ready": state["ready"], "blocker_count": len(state["blockers"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try:
        if args.command == "create": result: Any = {"output": write_character_designs(args.project_dir, build_character_designs(args.project_dir)).relative_to(Path(args.project_dir).resolve()).as_posix()}
        else: result = summary(args.project_dir)
    except (NovelCharacterDesignError, OSError, ValueError) as error: print(f"novel_character_designs: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
