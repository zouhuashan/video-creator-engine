#!/usr/bin/env python3
"""Create and validate art direction, color, composition, and negative constraints."""

from __future__ import annotations

import argparse
import json
import math
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

from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp  # noqa: E402
from scripts.novel_anime_repository import NovelAnimeRepository  # noqa: E402
from scripts.novel_episode_script import load_script_package  # noqa: E402
from scripts.novel_story_bible import load_bible  # noqa: E402
from scripts.novel_story_review import load_report as load_story_review  # noqa: E402
from scripts.novel_source_catalog import CATALOG_RELATIVE_PATH, load_catalog  # noqa: E402

SCHEMA_PATH = ROOT / "schemas" / "novel-visual-bible.schema.json"
VISUAL_ROOT = Path("visual-bible")
FILES = {"style.json": "style", "color-script.json": "color_script", "composition-rules.json": "composition", "negative-constraints.json": "negative_constraints"}


class NovelVisualBibleError(ValueError):
    """Raised when visual direction is incomplete or internally inconsistent."""


def _review() -> dict[str, Any]:
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def build_visual_bible(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    bible = load_bible(project_dir)
    scripts = load_script_package(project_dir)
    code = project["ip"]["id"].removeprefix("IP-")
    now = utc_timestamp()
    return validate_visual_bible(project_dir, {
        "schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "story_bible_revision": bible["revision"], "script_package_revision": scripts["revision"], "revision": 1, "created_at": now, "updated_at": now,
        "style": {"id": f"VSTYLE-{code}-01", "status": "DRAFT", "title": "国风动漫视觉方向（待审核）", "art_direction": "", "cultural_basis": [], "linework": "", "rendering": "", "texture": "", "character_language": "", "environment_language": "", "motion_language": "", "prompt_prefix": "", "reference_asset_ids": [], "provenance": {"kind": "UNSET", "source_refs": [], "story_refs": [], "note": ""}, "human_review": _review()},
        "color_script": {"status": "DRAFT", "swatches": [], "episode_palettes": [{"episode_id": item["id"], "mood": "", "time_of_day": "", "lighting": "", "swatch_ids": [], "transition_note": ""} for item in project["episodes"]], "human_review": _review()},
        "composition": {"status": "DRAFT", "canvas": {"width": 1080, "height": 1920, "aspect_ratio": "9:16", "fps": 30}, "safe_zone": {"top": 0.06, "right": 0.06, "bottom": 0.14, "left": 0.06}, "subtitle_zone": {"top": 0.68, "right": 0.08, "bottom": 0.08, "left": 0.08}, "rules": [], "human_review": _review()},
        "negative_constraints": {"status": "DRAFT", "global": ["无水印", "无乱码文字", "无多余肢体"], "character_identity": ["不得无依据改变角色脸型、发型、年龄和身体比例"], "environment": ["不得在连续场景中无依据改变天气、时间和空间结构"], "prompt_tokens": ["watermark", "garbled text", "extra limbs", "identity drift"], "forbidden_reference_types": ["MODERN_ANNOTATION", "MODERN_ILLUSTRATION", "EXISTING_SCREEN_DESIGN", "UNLICENSED_REFERENCE", "EMBEDDED_CREDENTIAL"], "human_review": _review()},
    })


def _schema(payload: dict[str, Any]) -> None:
    try: import jsonschema
    except ImportError: return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path) or "visual_bible"
        raise NovelVisualBibleError(f"visual bible schema violation at {path}: {errors[0].message}")


def _unique(items: list[dict[str, Any]], label: str) -> set[str]:
    result: set[str] = set()
    for index, item in enumerate(items):
        value = item["id"]
        if value in result: raise NovelVisualBibleError(f"duplicate {label} ID at index {index}: {value}")
        result.add(value)
    return result


def validate_visual_bible(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelVisualBibleError("visual bible must be an object")
    visual = deepcopy(payload); _schema(visual)
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    bible = load_bible(project_dir); scripts = load_script_package(project_dir)
    if visual["project_id"] != project["project_id"] or visual["ip_id"] != project["ip"]["id"]: raise NovelVisualBibleError("visual bible does not match the project")
    if visual["story_bible_revision"] != bible["revision"] or visual["script_package_revision"] != scripts["revision"]: raise NovelVisualBibleError("visual bible upstream revisions are stale")
    code = visual["ip_id"].removeprefix("IP-")
    style = visual["style"]
    if style["id"] != f"VSTYLE-{code}-01": raise NovelVisualBibleError("visual style ID must use the project IP code")
    story_ids = {bible["world"]["id"]} | set().union(*({item["id"] for item in bible[field]} for field in ("characters", "relationships", "locations", "props", "rules", "timeline", "foreshadowing")))
    if set(style["provenance"]["story_refs"]) - story_ids: raise NovelVisualBibleError("visual style has unknown story references")
    source_ids: set[str] = set()
    catalog_path = Path(project_dir) / CATALOG_RELATIVE_PATH
    if catalog_path.is_file():
        catalog = load_catalog(catalog_path)
        source_ids = {item["id"] for item in catalog["chapters"]} | {item["id"] for item in catalog["locators"]}
    if set(style["provenance"]["source_refs"]) - source_ids: raise NovelVisualBibleError("visual style has unknown source references")
    asset_ids = {item["id"] for item in project["assets"]}
    repository = NovelAnimeRepository(project_dir)
    if repository.db_path.is_file(): asset_ids |= repository.current_asset_ids()
    if set(style["reference_asset_ids"]) - asset_ids: raise NovelVisualBibleError("visual style has unknown reference assets")
    if style["provenance"]["kind"] == "SOURCE" and not (style["provenance"]["source_refs"] or style["provenance"]["story_refs"]): raise NovelVisualBibleError("source-backed visual style requires references")
    if style["provenance"]["kind"] == "ORIGINAL" and not style["provenance"]["note"].strip(): raise NovelVisualBibleError("original visual style requires a note")
    swatch_ids = _unique(visual["color_script"]["swatches"], "swatch")
    episode_ids = {item["id"] for item in project["episodes"]}
    palettes = visual["color_script"]["episode_palettes"]
    if {item["episode_id"] for item in palettes} != episode_ids or len(palettes) != len(episode_ids): raise NovelVisualBibleError("color script must define exactly one palette for every episode")
    if any(set(item["swatch_ids"]) - swatch_ids for item in palettes): raise NovelVisualBibleError("episode palette references unknown swatches")
    rule_ids = _unique(visual["composition"]["rules"], "composition rule")
    canvas = visual["composition"]["canvas"]
    left, right = (int(value) for value in canvas["aspect_ratio"].split(":"))
    if not math.isclose(canvas["width"] / canvas["height"], left / right, rel_tol=0.01): raise NovelVisualBibleError("canvas dimensions do not match aspect_ratio")
    safe = visual["composition"]["safe_zone"]; subtitle = visual["composition"]["subtitle_zone"]
    if safe["left"] + safe["right"] >= 1 or safe["top"] + safe["bottom"] >= 1 or subtitle["top"] + subtitle["bottom"] >= 1: raise NovelVisualBibleError("safe zones leave no usable frame area")
    statuses = [style["status"], visual["color_script"]["status"], visual["composition"]["status"], visual["negative_constraints"]["status"]]
    if "READY" in statuses:
        if statuses != ["READY"] * 4: raise NovelVisualBibleError("visual bible sections must become READY together")
        required_style = ("art_direction", "linework", "rendering", "texture", "character_language", "environment_language", "motion_language", "prompt_prefix")
        if any(not style[field].strip() for field in required_style) or style["provenance"]["kind"] == "UNSET": raise NovelVisualBibleError("READY visual style is incomplete or lacks provenance")
        if not swatch_ids or any(not item["swatch_ids"] or not item["mood"].strip() or not item["lighting"].strip() for item in palettes): raise NovelVisualBibleError("READY color script is incomplete")
        if not rule_ids or not visual["negative_constraints"]["global"] or not visual["negative_constraints"]["prompt_tokens"]: raise NovelVisualBibleError("READY composition and negative constraints must not be empty")
    return visual


def _atomic(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite: raise NovelVisualBibleError(f"refusing to overwrite visual bible file: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=".visual-bible.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file: json.dump(payload, file, ensure_ascii=False, indent=2); file.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


def write_visual_bible(project_dir: Path, visual: dict[str, Any], overwrite: bool = False) -> list[Path]:
    project_dir = Path(project_dir).expanduser().resolve(); visual = validate_visual_bible(project_dir, visual)
    common = {key: visual[key] for key in ("schema_version", "project_id", "ip_id", "story_bible_revision", "script_package_revision", "revision", "created_at", "updated_at")}
    paths = []
    for relative, field in FILES.items():
        path = project_dir / VISUAL_ROOT / relative; _atomic(path, {**common, field: visual[field]}, overwrite); paths.append(path)
    return paths


def load_visual_bible(project_dir: Path) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve(); common_keys = ("schema_version", "project_id", "ip_id", "story_bible_revision", "script_package_revision", "revision", "created_at", "updated_at"); visual: dict[str, Any] = {}
    for relative, field in FILES.items():
        path = project_dir / VISUAL_ROOT / relative
        try: part = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error: raise NovelVisualBibleError(f"cannot read visual bible file {path}: {error}") from error
        if not visual: visual.update({key: part.get(key) for key in common_keys})
        if any(part.get(key) != visual[key] for key in common_keys): raise NovelVisualBibleError("visual bible files have inconsistent metadata")
        visual[field] = part.get(field)
    return validate_visual_bible(project_dir, visual)


def rebind_script_revision(project_dir: Path, script_revision: int | None = None) -> dict[str, Any]:
    """Preserve existing visual content while rebinding stale script metadata."""
    project_dir = Path(project_dir).expanduser().resolve()
    common_keys = ("schema_version", "project_id", "ip_id", "story_bible_revision", "script_package_revision", "revision", "created_at", "updated_at")
    visual: dict[str, Any] = {}
    for relative, field in FILES.items():
        path = project_dir / VISUAL_ROOT / relative
        try:
            part = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise NovelVisualBibleError(f"cannot read visual bible file {path}: {error}") from error
        if not visual:
            visual.update({key: part.get(key) for key in common_keys})
        else:
            for key in common_keys:
                if key in {"script_package_revision", "updated_at"}:
                    continue
                if part.get(key) != visual.get(key):
                    raise NovelVisualBibleError("visual bible files have inconsistent metadata")
        visual[field] = part.get(field)

    scripts = load_script_package(project_dir)
    visual["script_package_revision"] = int(script_revision or scripts["revision"])
    visual["updated_at"] = utc_timestamp()
    visual = validate_visual_bible(project_dir, visual)
    write_visual_bible(project_dir, visual, overwrite=True)
    return visual


def readiness(project_dir: Path) -> dict[str, Any]:
    visual = load_visual_bible(project_dir); blockers: list[str] = []
    try: review = load_story_review(project_dir)
    except ValueError: review = None
    if not review or review["overall_status"] != "PASS" or review["human_review"]["status"] != "APPROVED": blockers.append("story review is not PASS and approved")
    for field in ("style", "color_script", "composition", "negative_constraints"):
        section = visual[field]
        if section["status"] != "READY" or section["human_review"]["status"] != "APPROVED": blockers.append(f"{field} is not ready and approved")
    return {"ready": not blockers, "blockers": blockers}


def summary(project_dir: Path) -> dict[str, Any] | None:
    try: visual = load_visual_bible(project_dir); state = readiness(project_dir)
    except (NovelVisualBibleError, ValueError): return None
    return {"revision": visual["revision"], "status": visual["style"]["status"], "swatch_count": len(visual["color_script"]["swatches"]), "episode_palette_count": len(visual["color_script"]["episode_palettes"]), "composition_rule_count": len(visual["composition"]["rules"]), "negative_constraint_count": sum(len(visual["negative_constraints"][key]) for key in ("global", "character_identity", "environment", "prompt_tokens")), "ready": state["ready"], "blocker_count": len(state["blockers"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try:
        if args.command == "create": result: Any = {"files": [path.relative_to(Path(args.project_dir).resolve()).as_posix() for path in write_visual_bible(args.project_dir, build_visual_bible(args.project_dir))]}
        else: result = summary(args.project_dir)
    except (NovelVisualBibleError, OSError, ValueError) as error: print(f"novel_visual_bible: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
