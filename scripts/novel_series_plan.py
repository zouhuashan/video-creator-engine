#!/usr/bin/env python3
"""Create and validate full-series, season, and character-arc planning files."""

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

from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp  # noqa: E402
from scripts.novel_source_catalog import CATALOG_RELATIVE_PATH, load_catalog  # noqa: E402
from scripts.novel_story_bible import load_bible, readiness as bible_readiness  # noqa: E402

SCHEMA_PATH = ROOT / "schemas" / "novel-series-plan.schema.json"
PLAN_ROOT = Path("writing-room")


class NovelSeriesPlanError(ValueError):
    """Raised when a long-form planning document has invalid references."""


def _review() -> dict[str, Any]:
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def _provenance() -> dict[str, Any]:
    return {"kind": "UNSET", "source_refs": [], "story_refs": [], "note": ""}


def build_plan(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    bible = load_bible(project_dir)
    code = project["ip"]["id"].removeprefix("IP-")
    now = utc_timestamp()
    season_plans = []
    for season in project["seasons"]:
        episodes = sorted((item for item in project["episodes"] if item["season_id"] == season["id"]), key=lambda item: item["episode_number"])
        season_plans.append({
            "id": f"SEASONPLAN-{season['id']}", "season_id": season["id"], "status": "DRAFT", "episode_ids": [item["id"] for item in episodes],
            "premise": "", "dramatic_question": "", "start_state": "", "end_state": "", "major_turns": [], "character_arc_ids": [],
            "provenance": _provenance(), "human_review": _review(),
        })
    return validate_plan(project_dir, {
        "schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "series_id": project["series"]["id"],
        "revision": 1, "story_bible_revision": bible["revision"], "created_at": now, "updated_at": now,
        "series_plan": {
            "id": f"SERPLAN-{code}-01", "status": "DRAFT", "title": project["title"], "logline": "", "themes": [], "audience": "", "format": "", "ending": "", "adaptation_strategy": "",
            "season_ids": [item["id"] for item in project["seasons"]], "character_arc_ids": [], "provenance": _provenance(), "human_review": _review(),
        },
        "season_plans": season_plans, "character_arcs": [],
    })


def _schema_validate(payload: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError:
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path) or "plan"
        raise NovelSeriesPlanError(f"series plan schema violation at {path}: {errors[0].message}")


def _ids(items: list[dict[str, Any]], pattern: str, label: str) -> set[str]:
    result: set[str] = set()
    for index, item in enumerate(items):
        value = str(item.get("id", ""))
        if not re.fullmatch(pattern, value) or value in result:
            raise NovelSeriesPlanError(f"{label}[{index}].id is invalid or duplicated")
        result.add(value)
    return result


def _references(project_dir: Path, bible: dict[str, Any]) -> tuple[set[str], set[str]]:
    catalog_path = Path(project_dir) / CATALOG_RELATIVE_PATH
    source_ids: set[str] = set()
    if catalog_path.is_file():
        catalog = load_catalog(catalog_path)
        source_ids = {item["id"] for item in catalog["chapters"]} | {item["id"] for item in catalog["locators"]}
    story_ids = {bible["world"]["id"]}
    for field in ("characters", "relationships", "locations", "props", "rules", "timeline", "foreshadowing"):
        story_ids.update(item["id"] for item in bible[field])
    return source_ids, story_ids


def _check_provenance(value: dict[str, Any], label: str, source_ids: set[str], story_ids: set[str], *, allow_unset: bool) -> None:
    provenance = value["provenance"]
    unknown_source = set(provenance["source_refs"]) - source_ids
    unknown_story = set(provenance["story_refs"]) - story_ids
    if unknown_source or unknown_story:
        raise NovelSeriesPlanError(f"{label} has unknown provenance references")
    if provenance["kind"] == "SOURCE" and not (provenance["source_refs"] or provenance["story_refs"]):
        raise NovelSeriesPlanError(f"{label} requires source or story references")
    if provenance["kind"] == "ORIGINAL" and not provenance["note"].strip():
        raise NovelSeriesPlanError(f"{label} original additions require a note")
    if not allow_unset and provenance["kind"] == "UNSET":
        raise NovelSeriesPlanError(f"{label} must be source-backed or marked original")


def validate_plan(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NovelSeriesPlanError("series plan must be an object")
    plan = deepcopy(payload)
    _schema_validate(plan)
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    bible = load_bible(project_dir)
    if (plan["project_id"], plan["ip_id"], plan["series_id"]) != (project["project_id"], project["ip"]["id"], project["series"]["id"]):
        raise NovelSeriesPlanError("series plan does not match the project")
    if plan["story_bible_revision"] != bible["revision"]:
        raise NovelSeriesPlanError("series plan story_bible_revision is stale")
    code = plan["ip_id"].removeprefix("IP-")
    if plan["series_plan"]["id"] != f"SERPLAN-{code}-01":
        raise NovelSeriesPlanError("series plan ID must use the project IP code")
    season_ids = {item["id"] for item in project["seasons"]}
    episode_ids = {item["id"] for item in project["episodes"]}
    character_ids = {item["id"] for item in bible["characters"]}
    if set(plan["series_plan"]["season_ids"]) != season_ids:
        raise NovelSeriesPlanError("series plan must cover every project season")
    if {item["season_id"] for item in plan["season_plans"]} != season_ids or len(plan["season_plans"]) != len(season_ids):
        raise NovelSeriesPlanError("season plans must cover every project season exactly once")
    arc_ids = _ids(plan["character_arcs"], rf"CARC-{re.escape(code)}-[A-Z0-9-]+", "character_arcs")
    source_ids, story_ids = _references(project_dir, bible)
    series = plan["series_plan"]
    _check_provenance(series, "series_plan", source_ids, story_ids, allow_unset=series["status"] == "DRAFT")
    if set(series["character_arc_ids"]) != arc_ids:
        raise NovelSeriesPlanError("series character_arc_ids do not match character arcs")
    for season in plan["season_plans"]:
        expected_episodes = {item["id"] for item in project["episodes"] if item["season_id"] == season["season_id"]}
        if season["id"] != f"SEASONPLAN-{season['season_id']}" or set(season["episode_ids"]) != expected_episodes:
            raise NovelSeriesPlanError(f"season plan {season['id']} has invalid episode coverage")
        if set(season["character_arc_ids"]) - arc_ids:
            raise NovelSeriesPlanError(f"season plan {season['id']} references unknown character arcs")
        _check_provenance(season, season["id"], source_ids, story_ids, allow_unset=season["status"] == "DRAFT")
        _ids(season["major_turns"], rf"TURN-{season['season_id']}-\d{{2}}", f"{season['id']}.major_turns")
        for turn in season["major_turns"]:
            if turn["episode_id"] not in expected_episodes:
                raise NovelSeriesPlanError(f"turn {turn['id']} is outside its season")
            _check_provenance(turn, turn["id"], source_ids, story_ids, allow_unset=False)
    for arc in plan["character_arcs"]:
        if arc["character_id"] not in character_ids or arc["season_id"] not in season_ids:
            raise NovelSeriesPlanError(f"character arc {arc['id']} has unknown character or season")
        expected_episodes = {item["id"] for item in project["episodes"] if item["season_id"] == arc["season_id"]}
        _check_provenance(arc, arc["id"], source_ids, story_ids, allow_unset=False)
        _ids(arc["milestones"], r"MILE-[A-Z0-9-]+", f"{arc['id']}.milestones")
        for milestone in arc["milestones"]:
            if milestone["episode_id"] not in expected_episodes:
                raise NovelSeriesPlanError(f"milestone {milestone['id']} is outside its season")
            _check_provenance(milestone, milestone["id"], source_ids, story_ids, allow_unset=False)
    return plan


def _atomic(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise NovelSeriesPlanError(f"refusing to overwrite plan file: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=".series-plan.", suffix=".tmp", dir=path.parent)
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


def write_plan(project_dir: Path, plan: dict[str, Any], *, overwrite: bool = False) -> list[Path]:
    project_dir = Path(project_dir).expanduser().resolve()
    plan = validate_plan(project_dir, plan)
    common = {key: plan[key] for key in ("schema_version", "project_id", "ip_id", "series_id", "revision", "story_bible_revision", "created_at", "updated_at")}
    files = [(PLAN_ROOT / "series-plan.json", {**common, "series_plan": plan["series_plan"]}), (PLAN_ROOT / "character-arcs.json", {**common, "character_arcs": plan["character_arcs"]})]
    files.extend((PLAN_ROOT / "seasons" / item["season_id"] / "season-plan.json", {**common, "season_plan": item}) for item in plan["season_plans"])
    for path, content in files:
        _atomic(project_dir / path, content, overwrite=overwrite)
    return [project_dir / path for path, _ in files]


def load_plan(project_dir: Path) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    series_path = project_dir / PLAN_ROOT / "series-plan.json"
    arcs_path = project_dir / PLAN_ROOT / "character-arcs.json"
    try:
        series_part = json.loads(series_path.read_text(encoding="utf-8"))
        arcs_part = json.loads(arcs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelSeriesPlanError(f"cannot read series planning files: {error}") from error
    metadata_keys = ("schema_version", "project_id", "ip_id", "series_id", "revision", "story_bible_revision", "created_at", "updated_at")
    plan = {key: series_part.get(key) for key in metadata_keys}
    if any(arcs_part.get(key) != plan[key] for key in metadata_keys):
        raise NovelSeriesPlanError("series planning files have inconsistent metadata")
    plan["series_plan"] = series_part.get("series_plan")
    plan["character_arcs"] = arcs_part.get("character_arcs")
    project = load_project(project_dir / MANIFEST_NAME)
    season_plans = []
    for season in project["seasons"]:
        path = project_dir / PLAN_ROOT / "seasons" / season["id"] / "season-plan.json"
        try:
            part = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise NovelSeriesPlanError(f"cannot read season plan {path}: {error}") from error
        if any(part.get(key) != plan[key] for key in metadata_keys):
            raise NovelSeriesPlanError("series planning files have inconsistent metadata")
        season_plans.append(part.get("season_plan"))
    plan["season_plans"] = season_plans
    return validate_plan(project_dir, plan)


def replace_plan(project_dir: Path, plan: dict[str, Any]) -> list[Path]:
    plan = deepcopy(plan)
    plan["revision"] += 1
    plan["updated_at"] = utc_timestamp()
    return write_plan(project_dir, plan, overwrite=True)


def readiness(project_dir: Path) -> dict[str, Any]:
    plan = load_plan(project_dir)
    blockers = list(bible_readiness(project_dir)["blockers"])
    series = plan["series_plan"]
    if series["status"] != "READY" or series["human_review"]["status"] != "APPROVED":
        blockers.append("series plan is not ready and approved")
    for season in plan["season_plans"]:
        if season["status"] != "READY" or season["human_review"]["status"] != "APPROVED":
            blockers.append(f"{season['id']} is not ready and approved")
    if not plan["character_arcs"]:
        blockers.append("no character arcs are defined")
    for arc in plan["character_arcs"]:
        if arc["status"] != "READY" or arc["human_review"]["status"] != "APPROVED":
            blockers.append(f"{arc['id']} is not ready and approved")
    return {"ready": not blockers, "blockers": blockers}


def summary(project_dir: Path) -> dict[str, Any] | None:
    try:
        plan = load_plan(project_dir)
        state = readiness(project_dir)
    except (NovelSeriesPlanError, ValueError):
        return None
    return {"revision": plan["revision"], "status": plan["series_plan"]["status"], "season_plan_count": len(plan["season_plans"]), "character_arc_count": len(plan["character_arcs"]), "major_turn_count": sum(len(item["major_turns"]) for item in plan["season_plans"]), "ready": state["ready"], "blocker_count": len(state["blockers"])}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "validate"):
        command = subparsers.add_parser(name)
        command.add_argument("project_dir", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "create":
            files = write_plan(args.project_dir, build_plan(args.project_dir))
            result: Any = {"files": [path.relative_to(Path(args.project_dir).resolve()).as_posix() for path in files]}
        else:
            result = summary(args.project_dir)
    except (NovelSeriesPlanError, OSError, ValueError) as error:
        print(f"novel_series_plan: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
