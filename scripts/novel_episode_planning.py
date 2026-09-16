#!/usr/bin/env python3
"""Create story arcs and one traceable planning card for every episode."""

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
from scripts.novel_series_plan import load_plan, readiness as series_readiness  # noqa: E402
from scripts.novel_source_catalog import CATALOG_RELATIVE_PATH, load_catalog  # noqa: E402
from scripts.novel_story_bible import load_bible  # noqa: E402

SCHEMA_PATH = ROOT / "schemas" / "novel-episode-planning.schema.json"
OUTPUT = Path("writing-room/episode-planning.json")


class NovelEpisodePlanningError(ValueError):
    """Raised when story arc or episode-card planning is inconsistent."""


def _review() -> dict[str, Any]:
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def _provenance() -> dict[str, Any]:
    return {"kind": "UNSET", "source_refs": [], "story_refs": [], "note": ""}


def build_episode_planning(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    series_plan = load_plan(project_dir)
    now = utc_timestamp()
    cards = [{
        "id": f"CARD-{episode['id']}", "episode_id": episode["id"], "arc_id": None, "status": "DRAFT",
        "premise": "", "hook": "", "goal": "", "obstacle": "", "turn": "", "climax": "", "ending_hook": "", "beats": [],
        "character_ids": [], "location_ids": [], "prop_ids": [], "foreshadowing_setup_ids": [], "foreshadowing_payoff_ids": [],
        "provenance": _provenance(), "human_review": _review(),
    } for episode in sorted(project["episodes"], key=lambda item: (item["season_id"], item["episode_number"]))]
    return validate_episode_planning(project_dir, {
        "schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "series_plan_revision": series_plan["revision"],
        "revision": 1, "created_at": now, "updated_at": now, "story_arcs": [], "episode_cards": cards,
    })


def _schema(payload: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError:
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        path = ".".join(str(value) for value in errors[0].absolute_path) or "episode_planning"
        raise NovelEpisodePlanningError(f"episode planning schema violation at {path}: {errors[0].message}")


def _unique(items: list[dict[str, Any]], pattern: str, label: str) -> set[str]:
    ids: set[str] = set()
    for index, item in enumerate(items):
        value = str(item.get("id", ""))
        if not re.fullmatch(pattern, value) or value in ids:
            raise NovelEpisodePlanningError(f"{label}[{index}].id is invalid or duplicated")
        ids.add(value)
    return ids


def _reference_sets(project_dir: Path, bible: dict[str, Any]) -> tuple[set[str], dict[str, set[str]]]:
    path = Path(project_dir) / CATALOG_RELATIVE_PATH
    source_ids: set[str] = set()
    if path.is_file():
        catalog = load_catalog(path)
        source_ids = {item["id"] for item in catalog["chapters"]} | {item["id"] for item in catalog["locators"]}
    story = {field: {item["id"] for item in bible[field]} for field in ("characters", "locations", "props", "foreshadowing")}
    story["all"] = {bible["world"]["id"]} | set().union(*(set(item["id"] for item in bible[field]) for field in ("characters", "relationships", "locations", "props", "rules", "timeline", "foreshadowing")))
    return source_ids, story


def _provenance_valid(item: dict[str, Any], label: str, source_ids: set[str], story_ids: set[str], allow_unset: bool) -> None:
    value = item["provenance"]
    if set(value["source_refs"]) - source_ids or set(value["story_refs"]) - story_ids:
        raise NovelEpisodePlanningError(f"{label} has unknown provenance references")
    if value["kind"] == "SOURCE" and not (value["source_refs"] or value["story_refs"]):
        raise NovelEpisodePlanningError(f"{label} requires traceable source references")
    if value["kind"] == "ORIGINAL" and not value["note"].strip():
        raise NovelEpisodePlanningError(f"{label} original content requires a note")
    if value["kind"] == "UNSET" and not allow_unset:
        raise NovelEpisodePlanningError(f"{label} lacks provenance")


def validate_episode_planning(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NovelEpisodePlanningError("episode planning must be an object")
    planning = deepcopy(payload)
    _schema(planning)
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    series_plan = load_plan(project_dir)
    bible = load_bible(project_dir)
    if planning["project_id"] != project["project_id"] or planning["ip_id"] != project["ip"]["id"]:
        raise NovelEpisodePlanningError("episode planning does not match the project")
    if planning["series_plan_revision"] != series_plan["revision"]:
        raise NovelEpisodePlanningError("episode planning series_plan_revision is stale")
    episode_ids = {item["id"] for item in project["episodes"]}
    season_ids = {item["id"] for item in project["seasons"]}
    arc_ids = _unique(planning["story_arcs"], r"S\d{2}-ARC\d{2}", "story_arcs")
    card_ids = _unique(planning["episode_cards"], r"CARD-S\d{2}E\d{3}", "episode_cards")
    if {item["episode_id"] for item in planning["episode_cards"]} != episode_ids or len(card_ids) != len(episode_ids):
        raise NovelEpisodePlanningError("episode cards must cover every project episode exactly once")
    source_ids, story = _reference_sets(project_dir, bible)
    character_arc_ids = {item["id"] for item in series_plan["character_arcs"]}
    for arc in planning["story_arcs"]:
        if arc["season_id"] not in season_ids or arc["id"][:3] != arc["season_id"]:
            raise NovelEpisodePlanningError(f"arc {arc['id']} has an invalid season")
        expected = {item["id"] for item in project["episodes"] if item["season_id"] == arc["season_id"]}
        if not 3 <= len(arc["episode_ids"]) <= 8 or set(arc["episode_ids"]) - expected:
            raise NovelEpisodePlanningError(f"arc {arc['id']} must cover 3 to 8 episodes in its season")
        if set(arc["character_arc_ids"]) - character_arc_ids or set(arc["foreshadowing_ids"]) - story["foreshadowing"]:
            raise NovelEpisodePlanningError(f"arc {arc['id']} has unknown story references")
        _provenance_valid(arc, arc["id"], source_ids, story["all"], arc["status"] == "DRAFT")
    for card in planning["episode_cards"]:
        episode = next(item for item in project["episodes"] if item["id"] == card["episode_id"])
        if card["id"] != f"CARD-{card['episode_id']}" or (card["arc_id"] and card["arc_id"] not in arc_ids):
            raise NovelEpisodePlanningError(f"card {card['id']} has invalid identity or arc")
        if card["arc_id"] and card["episode_id"] not in next(item["episode_ids"] for item in planning["story_arcs"] if item["id"] == card["arc_id"]):
            raise NovelEpisodePlanningError(f"card {card['id']} is outside its arc")
        for field, allowed in (("character_ids", story["characters"]), ("location_ids", story["locations"]), ("prop_ids", story["props"]), ("foreshadowing_setup_ids", story["foreshadowing"]), ("foreshadowing_payoff_ids", story["foreshadowing"])):
            if set(card[field]) - allowed:
                raise NovelEpisodePlanningError(f"card {card['id']} has unknown {field}")
        _provenance_valid(card, card["id"], source_ids, story["all"], card["status"] == "DRAFT")
        beat_ids = _unique(card["beats"], rf"BEAT-{card['episode_id']}-\d{{2}}", f"{card['id']}.beats")
        for beat in card["beats"]:
            _provenance_valid(beat, beat["id"], source_ids, story["all"], False)
        if card["status"] == "READY":
            required_text = ("premise", "hook", "goal", "obstacle", "turn", "climax", "ending_hook")
            if not card["arc_id"] or any(not card[field].strip() for field in required_text) or {"HOOK", "ENDING_HOOK"} - {item["type"] for item in card["beats"]}:
                raise NovelEpisodePlanningError(f"READY card {card['id']} is incomplete")
    return planning


def write_episode_planning(project_dir: Path, planning: dict[str, Any], *, overwrite: bool = False) -> Path:
    project_dir = Path(project_dir).expanduser().resolve()
    planning = validate_episode_planning(project_dir, planning)
    output = project_dir / OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise NovelEpisodePlanningError(f"refusing to overwrite episode planning: {output}")
    descriptor, temporary = tempfile.mkstemp(prefix=".episode-planning.", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(planning, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, output)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return output


def sync_manifest_arcs(project_dir: Path, planning: dict[str, Any]) -> dict[str, int]:
    project_dir = Path(project_dir).expanduser().resolve()
    planning = validate_episode_planning(project_dir, planning)
    project = load_project(project_dir / MANIFEST_NAME)
    project["arcs"] = [{
        "id": arc["id"], "title": arc["title"], "revision": planning["revision"], "status": "DRAFT",
        "input_refs": list(arc["character_arc_ids"]), "source_refs": list(arc["provenance"]["source_refs"]), "provider": None,
        "human_review": {key: arc["human_review"][key] for key in ("required", "status", "reviewed_at", "reviewed_by")},
        "season_id": arc["season_id"], "episode_ids": list(arc["episode_ids"]),
    } for arc in planning["story_arcs"]]
    by_season = {season["id"]: [] for season in project["seasons"]}
    for arc in project["arcs"]:
        by_season[arc["season_id"]].append(arc["id"])
    for season in project["seasons"]:
        season["arc_ids"] = sorted(by_season[season["id"]])
    card_by_episode = {card["episode_id"]: card for card in planning["episode_cards"]}
    for episode in project["episodes"]:
        episode["arc_id"] = card_by_episode[episode["id"]]["arc_id"]
    project["revision"] += 1
    project["updated_at"] = utc_timestamp()
    replace_project(project_dir, validate_project(project))
    repository = NovelAnimeRepository(project_dir)
    if repository.db_path.is_file():
        repository.sync_manifest()
    return {"arcs": len(project["arcs"]), "assigned_episodes": sum(1 for item in project["episodes"] if item["arc_id"])}


def load_episode_planning(project_dir: Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve() / OUTPUT
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelEpisodePlanningError(f"cannot read episode planning: {error}") from error
    return validate_episode_planning(project_dir, payload)


def readiness(project_dir: Path) -> dict[str, Any]:
    planning = load_episode_planning(project_dir)
    blockers = list(series_readiness(project_dir)["blockers"])
    if not planning["story_arcs"]:
        blockers.append("no story arcs are defined")
    for item in [*planning["story_arcs"], *planning["episode_cards"]]:
        if item["status"] != "READY" or item["human_review"]["status"] != "APPROVED":
            blockers.append(f"{item['id']} is not ready and approved")
    return {"ready": not blockers, "blockers": blockers}


def summary(project_dir: Path) -> dict[str, Any] | None:
    try:
        planning = load_episode_planning(project_dir)
        state = readiness(project_dir)
    except (NovelEpisodePlanningError, ValueError):
        return None
    return {"revision": planning["revision"], "story_arc_count": len(planning["story_arcs"]), "episode_card_count": len(planning["episode_cards"]), "ready_card_count": sum(1 for item in planning["episode_cards"] if item["status"] == "READY"), "beat_count": sum(len(item["beats"]) for item in planning["episode_cards"]), "ready": state["ready"], "blocker_count": len(state["blockers"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "validate"))
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create":
            planning = build_episode_planning(args.project_dir)
            result: Any = {"output": write_episode_planning(args.project_dir, planning).relative_to(Path(args.project_dir).resolve()).as_posix(), "manifest": sync_manifest_arcs(args.project_dir, planning)}
        else:
            result = summary(args.project_dir)
    except (NovelEpisodePlanningError, OSError, ValueError) as error:
        print(f"novel_episode_planning: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
