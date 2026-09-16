#!/usr/bin/env python3
"""Create and validate the story bible and episode-end continuity ledger."""

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
from scripts.novel_source_catalog import CATALOG_RELATIVE_PATH, load_catalog  # noqa: E402

SCHEMA_PATH = ROOT / "schemas" / "novel-story-bible.schema.json"
STORY_BIBLE_DIR = Path("story-bible")
FILE_FIELDS = {
    "world.json": "world",
    "characters/index.json": "characters",
    "relationships.json": "relationships",
    "locations.json": "locations",
    "props.json": "props",
    "rules.json": "rules",
    "timeline.json": "timeline",
    "foreshadowing.json": "foreshadowing",
    "continuity-ledger.json": "continuity_ledger",
}
LIST_FIELDS = set(FILE_FIELDS.values()) - {"world", "continuity_ledger"}
ID_FIELDS = {
    "characters": ("id", r"CHR-{code}-[A-Z0-9-]+"),
    "relationships": ("id", r"REL-{code}-[A-Z0-9-]+"),
    "locations": ("id", r"LOCN-{code}-[A-Z0-9-]+"),
    "props": ("id", r"PROP-{code}-[A-Z0-9-]+"),
    "rules": ("id", r"RULE-{code}-[A-Z0-9-]+"),
    "timeline": ("id", r"TL-{code}-[A-Z0-9-]+"),
    "foreshadowing": ("id", r"FSH-{code}-[A-Z0-9-]+"),
}


class NovelStoryBibleError(ValueError):
    """Raised when story knowledge or continuity references are inconsistent."""


def _review() -> dict[str, Any]:
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def _provenance() -> dict[str, Any]:
    return {"kind": "UNSET", "source_refs": [], "note": ""}


def build_bible(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    code = project["ip"]["id"].removeprefix("IP-")
    now = utc_timestamp()
    baseline_id = "CNT-S01E000-END"
    return validate_bible(project_dir, {
        "schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"],
        "revision": 1, "created_at": now, "updated_at": now,
        "world": {"id": f"WORLD-{code}", "status": "DRAFT", "title": project["title"], "premise": "", "era": "", "geography": [], "societies": [], "cosmology": [], "tone": "", "provenance": _provenance(), "human_review": _review()},
        "characters": [], "relationships": [], "locations": [], "props": [], "rules": [], "timeline": [], "foreshadowing": [],
        "continuity_ledger": {"baseline_snapshot_id": baseline_id, "snapshots": [{
            "id": baseline_id, "episode_id": None, "sequence": 0, "prior_snapshot_id": None,
            "timeline_position_id": None, "character_states": [], "relationship_states": [], "prop_states": [],
            "open_foreshadowing_ids": [], "continuity_delta_ref": None, "human_review": _review(),
        }]},
    })


def _json_schema_validate(payload: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError:
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path) or "bible"
        raise NovelStoryBibleError(f"story bible schema violation at {path}: {errors[0].message}")


def _unique_ids(items: list[dict[str, Any]], field: str, pattern: str, label: str) -> set[str]:
    ids: set[str] = set()
    for index, item in enumerate(items):
        value = str(item.get(field, ""))
        if not re.fullmatch(pattern, value) or value in ids:
            raise NovelStoryBibleError(f"{label}[{index}].{field} is invalid or duplicated")
        ids.add(value)
    return ids


def _source_reference_ids(project_dir: Path) -> set[str]:
    path = Path(project_dir) / CATALOG_RELATIVE_PATH
    if not path.is_file():
        return set()
    catalog = load_catalog(path)
    return {item["id"] for item in catalog["chapters"]} | {item["id"] for item in catalog["locators"]}


def _validate_provenance(entity: dict[str, Any], label: str, source_ids: set[str]) -> None:
    provenance = entity["provenance"]
    refs = set(provenance["source_refs"])
    if not refs <= source_ids:
        raise NovelStoryBibleError(f"{label} references unknown source locations: {sorted(refs - source_ids)}")
    if provenance["kind"] == "SOURCE" and not refs:
        raise NovelStoryBibleError(f"{label} requires at least one source reference")
    if provenance["kind"] == "ORIGINAL" and not provenance["note"].strip():
        raise NovelStoryBibleError(f"{label} original additions require a note")


def validate_bible(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NovelStoryBibleError("story bible must be an object")
    bible = deepcopy(payload)
    _json_schema_validate(bible)
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    if bible["project_id"] != project["project_id"] or bible["ip_id"] != project["ip"]["id"]:
        raise NovelStoryBibleError("story bible does not match the project")
    code = bible["ip_id"].removeprefix("IP-")
    if bible["world"]["id"] != f"WORLD-{code}":
        raise NovelStoryBibleError("world ID must use the project IP code")
    ids = {field: _unique_ids(bible[field], id_field, pattern.format(code=re.escape(code)), field) for field, (id_field, pattern) in ID_FIELDS.items()}
    if len(bible["timeline"]) != len({item["order"] for item in bible["timeline"]}):
        raise NovelStoryBibleError("timeline order values must be unique")
    source_ids = _source_reference_ids(project_dir)
    _validate_provenance(bible["world"], "world", source_ids)
    if bible["world"]["status"] == "READY" and (not bible["world"]["premise"].strip() or bible["world"]["provenance"]["kind"] == "UNSET"):
        raise NovelStoryBibleError("a READY world requires a premise and traceable provenance")
    for field in ID_FIELDS:
        for item in bible[field]:
            _validate_provenance(item, f"{field}.{item['id']}", source_ids)
            if item["provenance"]["kind"] == "UNSET":
                raise NovelStoryBibleError(f"{field}.{item['id']} must be source-backed or marked as an original addition")
    for item in bible["relationships"]:
        if item["from_character_id"] == item["to_character_id"] or {item["from_character_id"], item["to_character_id"]} - ids["characters"]:
            raise NovelStoryBibleError(f"relationship {item['id']} has invalid character references")
    for item in bible["props"]:
        if item["owner_character_id"] and item["owner_character_id"] not in ids["characters"]:
            raise NovelStoryBibleError(f"prop {item['id']} has an unknown owner")
        if item["home_location_id"] and item["home_location_id"] not in ids["locations"]:
            raise NovelStoryBibleError(f"prop {item['id']} has an unknown home location")
    episode_ids = {item["id"] for item in project["episodes"]}
    for item in bible["timeline"]:
        if set(item["character_ids"]) - ids["characters"] or (item["location_id"] and item["location_id"] not in ids["locations"]):
            raise NovelStoryBibleError(f"timeline event {item['id']} has unknown references")
    for item in bible["foreshadowing"]:
        if item["setup_timeline_id"] and item["setup_timeline_id"] not in ids["timeline"]:
            raise NovelStoryBibleError(f"foreshadowing {item['id']} has an unknown setup event")
        if any(value and value not in episode_ids for value in (item["target_episode_id"], item["payoff_episode_id"])):
            raise NovelStoryBibleError(f"foreshadowing {item['id']} references an unknown episode")
    _validate_ledger(bible, ids, episode_ids)
    return bible


def _validate_ledger(bible: dict[str, Any], ids: dict[str, set[str]], episode_ids: set[str]) -> None:
    ledger = bible["continuity_ledger"]
    snapshots = ledger["snapshots"]
    snapshot_ids = _unique_ids(snapshots, "id", r"CNT-S\d{2}E\d{3}-END", "continuity snapshots")
    baseline = next((item for item in snapshots if item["id"] == ledger["baseline_snapshot_id"]), None)
    if baseline is None or baseline["episode_id"] is not None or baseline["sequence"] != 0 or baseline["prior_snapshot_id"] is not None:
        raise NovelStoryBibleError("continuity ledger requires a valid sequence-zero baseline")
    sequence_values: set[int] = set()
    episode_values: set[str] = set()
    for snapshot in snapshots:
        if snapshot["sequence"] in sequence_values:
            raise NovelStoryBibleError("continuity snapshot sequence values must be unique")
        sequence_values.add(snapshot["sequence"])
        if snapshot is not baseline:
            episode_id = snapshot["episode_id"]
            if episode_id not in episode_ids or episode_id in episode_values:
                raise NovelStoryBibleError(f"snapshot {snapshot['id']} has an invalid or duplicate episode")
            episode_values.add(episode_id)
            if snapshot["id"] != f"CNT-{episode_id}-END" or snapshot["prior_snapshot_id"] not in snapshot_ids:
                raise NovelStoryBibleError(f"snapshot {snapshot['id']} has invalid identity or ancestry")
        if snapshot["timeline_position_id"] and snapshot["timeline_position_id"] not in ids["timeline"]:
            raise NovelStoryBibleError(f"snapshot {snapshot['id']} has unknown timeline position")
        if set(snapshot["open_foreshadowing_ids"]) - ids["foreshadowing"]:
            raise NovelStoryBibleError(f"snapshot {snapshot['id']} has unknown foreshadowing")
        _unique_ids(snapshot["character_states"], "character_id", r"CHR-[A-Z0-9-]+", f"{snapshot['id']}.character_states")
        _unique_ids(snapshot["relationship_states"], "relationship_id", r"REL-[A-Z0-9-]+", f"{snapshot['id']}.relationship_states")
        _unique_ids(snapshot["prop_states"], "prop_id", r"PROP-[A-Z0-9-]+", f"{snapshot['id']}.prop_states")
        for state in snapshot["character_states"]:
            if state["character_id"] not in ids["characters"] or (state["location_id"] and state["location_id"] not in ids["locations"]) or set(state["carried_prop_ids"]) - ids["props"]:
                raise NovelStoryBibleError(f"snapshot {snapshot['id']} has invalid character state references")
        for state in snapshot["relationship_states"]:
            if state["relationship_id"] not in ids["relationships"]:
                raise NovelStoryBibleError(f"snapshot {snapshot['id']} has invalid relationship state")
        for state in snapshot["prop_states"]:
            if state["prop_id"] not in ids["props"] or (state["location_id"] and state["location_id"] not in ids["locations"]) or (state["holder_character_id"] and state["holder_character_id"] not in ids["characters"]):
                raise NovelStoryBibleError(f"snapshot {snapshot['id']} has invalid prop state")
        carried_by: dict[str, str] = {}
        for state in snapshot["character_states"]:
            for prop_id in state["carried_prop_ids"]:
                if prop_id in carried_by:
                    raise NovelStoryBibleError(f"snapshot {snapshot['id']} assigns {prop_id} to multiple characters")
                carried_by[prop_id] = state["character_id"]
        prop_holders = {state["prop_id"]: state["holder_character_id"] for state in snapshot["prop_states"]}
        if any(prop_holders.get(prop_id) != character_id for prop_id, character_id in carried_by.items()):
            raise NovelStoryBibleError(f"snapshot {snapshot['id']} has inconsistent carried prop states")
        if any(holder and carried_by.get(prop_id) != holder for prop_id, holder in prop_holders.items()):
            raise NovelStoryBibleError(f"snapshot {snapshot['id']} has inconsistent prop holder states")
    ordered = sorted(snapshots, key=lambda item: item["sequence"])
    for prior, current in zip(ordered, ordered[1:]):
        if current["sequence"] != prior["sequence"] + 1 or current["prior_snapshot_id"] != prior["id"]:
            raise NovelStoryBibleError("continuity snapshots must form one uninterrupted chain")


def _atomic_json(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise NovelStoryBibleError(f"refusing to overwrite story bible file: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=".story-bible.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def write_bible(project_dir: Path, bible: dict[str, Any], *, overwrite: bool = False) -> list[Path]:
    project_dir = Path(project_dir).expanduser().resolve()
    bible = validate_bible(project_dir, bible)
    common = {key: bible[key] for key in ("schema_version", "project_id", "ip_id", "revision", "created_at", "updated_at")}
    paths = []
    for relative, field in FILE_FIELDS.items():
        path = project_dir / STORY_BIBLE_DIR / relative
        _atomic_json(path, {**common, field: bible[field]}, overwrite=overwrite)
        paths.append(path)
    return paths


def load_bible(project_dir: Path) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    payload: dict[str, Any] = {}
    for relative, field in FILE_FIELDS.items():
        path = project_dir / STORY_BIBLE_DIR / relative
        if not path.is_file():
            raise NovelStoryBibleError(f"story bible file is missing: {path}")
        try:
            part = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise NovelStoryBibleError(f"cannot read story bible file {path}: {error}") from error
        metadata = {key: part.get(key) for key in ("schema_version", "project_id", "ip_id", "revision", "created_at", "updated_at")}
        if payload and any(payload[key] != value for key, value in metadata.items()):
            raise NovelStoryBibleError("story bible files have inconsistent metadata")
        payload.update(metadata)
        if field not in part:
            raise NovelStoryBibleError(f"story bible file is missing field: {field}")
        payload[field] = part[field]
    return validate_bible(project_dir, payload)


def replace_bible(project_dir: Path, bible: dict[str, Any]) -> list[Path]:
    bible = deepcopy(bible)
    bible["revision"] += 1
    bible["updated_at"] = utc_timestamp()
    return write_bible(project_dir, bible, overwrite=True)


def bind_continuity_refs(project_dir: Path) -> dict[str, str]:
    """Bind each episode to its required prior snapshot and future delta file."""
    project_dir = Path(project_dir).expanduser().resolve()
    project = load_project(project_dir / MANIFEST_NAME)
    episodes = sorted(project["episodes"], key=lambda item: (item["season_id"], item["episode_number"]))
    refs: dict[str, str] = {}
    for index, episode in enumerate(episodes):
        prior_id = "CNT-S01E000-END" if index == 0 else f"CNT-{episodes[index - 1]['id']}-END"
        episode["continuity_in_ref"] = f"story-bible/continuity-ledger.json#{prior_id}"
        episode["continuity_delta_ref"] = f"episodes/{episode['id']}/continuity-delta.json"
        refs[episode["id"]] = prior_id
    project["revision"] += 1
    project["updated_at"] = utc_timestamp()
    replace_project(project_dir, validate_project(project))
    repository = NovelAnimeRepository(project_dir)
    if repository.db_path.is_file():
        repository.sync_manifest()
    return refs


def readiness(project_dir: Path) -> dict[str, Any]:
    """Report blockers that prevent the project from entering BIBLE_READY."""
    bible = load_bible(project_dir)
    blockers: list[str] = []
    if bible["world"]["status"] != "READY":
        blockers.append("world is not READY")
    if not bible["characters"]:
        blockers.append("no characters are defined")
    if not bible["timeline"]:
        blockers.append("timeline is empty")
    reviewables = [bible["world"], *bible["characters"], *bible["relationships"], *bible["locations"], *bible["props"], *bible["rules"], *bible["timeline"], *bible["foreshadowing"]]
    pending = [item["id"] for item in reviewables if item["human_review"]["status"] != "APPROVED"]
    if pending:
        blockers.append(f"story entities awaiting approval: {', '.join(pending)}")
    baseline = next(item for item in bible["continuity_ledger"]["snapshots"] if item["id"] == bible["continuity_ledger"]["baseline_snapshot_id"])
    if baseline["human_review"]["status"] != "APPROVED":
        blockers.append("continuity baseline is awaiting approval")
    character_ids = {item["id"] for item in bible["characters"]}
    state_ids = {item["character_id"] for item in baseline["character_states"]}
    if state_ids != character_ids:
        blockers.append("continuity baseline does not cover every character")
    return {"ready": not blockers, "blockers": blockers}


def continuity_input(project_dir: Path, episode_id: str) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME)
    episodes = [item["id"] for item in sorted(project["episodes"], key=lambda item: (item["season_id"], item["episode_number"]))]
    if episode_id not in episodes:
        raise NovelStoryBibleError(f"unknown episode: {episode_id}")
    bible = load_bible(project_dir)
    snapshots = bible["continuity_ledger"]["snapshots"]
    wanted_id = bible["continuity_ledger"]["baseline_snapshot_id"] if episodes.index(episode_id) == 0 else f"CNT-{episodes[episodes.index(episode_id) - 1]}-END"
    snapshot = next((item for item in snapshots if item["id"] == wanted_id), None)
    if snapshot is None:
        raise NovelStoryBibleError(f"previous episode continuity snapshot is missing: {wanted_id}")
    return {"episode_id": episode_id, "input_snapshot_id": wanted_id, "snapshot": deepcopy(snapshot)}


def record_snapshot(project_dir: Path, snapshot_file: Path) -> dict[str, Any]:
    bible = load_bible(project_dir)
    try:
        snapshot = json.loads(Path(snapshot_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelStoryBibleError(f"cannot read continuity snapshot: {error}") from error
    if not isinstance(snapshot, dict):
        raise NovelStoryBibleError("continuity snapshot must be an object")
    ledger = bible["continuity_ledger"]
    ledger["snapshots"] = [item for item in ledger["snapshots"] if item["id"] != snapshot.get("id")] + [snapshot]
    replace_bible(project_dir, validate_bible(project_dir, bible))
    return {"snapshot_id": snapshot["id"], "episode_id": snapshot["episode_id"], "sequence": snapshot["sequence"]}


def summary(project_dir: Path) -> dict[str, Any] | None:
    try:
        bible = load_bible(project_dir)
    except NovelStoryBibleError:
        return None
    ledger = bible["continuity_ledger"]
    state = readiness(project_dir)
    return {
        "revision": bible["revision"], "world_status": bible["world"]["status"],
        "character_count": len(bible["characters"]), "relationship_count": len(bible["relationships"]),
        "location_count": len(bible["locations"]), "prop_count": len(bible["props"]), "rule_count": len(bible["rules"]),
        "timeline_event_count": len(bible["timeline"]), "foreshadowing_count": len(bible["foreshadowing"]),
        "continuity_snapshot_count": len(ledger["snapshots"]),
        "reviewed_snapshot_count": sum(1 for item in ledger["snapshots"] if item["human_review"]["status"] == "APPROVED"),
        "ready": state["ready"], "blocker_count": len(state["blockers"]),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("project_dir", type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("project_dir", type=Path)
    continuity = subparsers.add_parser("continuity-input")
    continuity.add_argument("project_dir", type=Path)
    continuity.add_argument("--episode-id", required=True)
    record = subparsers.add_parser("record-snapshot")
    record.add_argument("project_dir", type=Path)
    record.add_argument("--snapshot-file", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "create":
            paths = write_bible(args.project_dir, build_bible(args.project_dir))
            result: Any = {"files": [path.relative_to(Path(args.project_dir).resolve()).as_posix() for path in paths], "continuity_refs": bind_continuity_refs(args.project_dir)}
        elif args.command == "validate":
            result = summary(args.project_dir)
        elif args.command == "continuity-input":
            result = continuity_input(args.project_dir, args.episode_id)
        else:
            result = record_snapshot(args.project_dir, args.snapshot_file)
    except (NovelStoryBibleError, OSError, ValueError) as error:
        print(f"novel_story_bible: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
