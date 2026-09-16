#!/usr/bin/env python3
"""Create and validate the P18 novel-anime project aggregate."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "novel-anime-project.schema.json"
MANIFEST_NAME = "novel-anime-project.json"
SCHEMA_VERSION = 1

ID_PATTERNS = {
    "ip": re.compile(r"IP-[A-Z0-9]{2,12}\Z"),
    "source_edition": re.compile(r"SRC-[A-Z0-9]{2,12}-\d{3}\Z"),
    "series": re.compile(r"SER-[A-Z0-9]{2,12}-\d{2}\Z"),
    "season": re.compile(r"S\d{2}\Z"),
    "arc": re.compile(r"S\d{2}-ARC\d{2}\Z"),
    "episode": re.compile(r"S\d{2}E\d{3}\Z"),
    "scene": re.compile(r"S\d{2}E\d{3}-SC\d{3}\Z"),
    "shot": re.compile(r"S\d{2}E\d{3}-SC\d{3}-SH\d{3}\Z"),
    "asset": re.compile(r"AST-[A-Z0-9][A-Z0-9-]{2,80}\Z"),
    "render": re.compile(r"RND-[A-Z0-9][A-Z0-9-]{2,80}\Z"),
}
PROJECT_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{2,63}\Z")
ENTITY_LISTS = {
    "source_editions": "source_edition",
    "seasons": "season",
    "arcs": "arc",
    "episodes": "episode",
    "scenes": "scene",
    "shots": "shot",
    "assets": "asset",
    "renders": "render",
}
STATUSES = {
    "DRAFT", "SOURCE_READY", "BIBLE_READY", "WRITING_READY", "STORYBOARD_READY",
    "ASSETS_READY", "AUDIO_READY", "ANIMATIC_READY", "MOTION_READY", "EDIT_READY",
    "QC_READY", "HUMAN_APPROVED", "PACKAGED",
}


class NovelAnimeProjectError(ValueError):
    """Raised when a novel-anime aggregate violates the P18 contract."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_ip_code(value: str) -> str:
    code = re.sub(r"[^A-Z0-9]", "", value.strip().upper())
    if not 2 <= len(code) <= 12:
        raise NovelAnimeProjectError("ip_code must contain 2 to 12 ASCII letters or numbers")
    return code


def _review() -> dict[str, Any]:
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None}


def _entity(entity_id: str, title: str) -> dict[str, Any]:
    return {
        "id": entity_id,
        "title": title,
        "revision": 1,
        "status": "DRAFT",
        "input_refs": [],
        "source_refs": [],
        "provider": None,
        "human_review": _review(),
    }


def build_project(project_id: str, ip_code: str, title: str, *, episode_count: int = 5) -> dict[str, Any]:
    project_id = project_id.strip()
    title = title.strip()
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise NovelAnimeProjectError("project_id must use lowercase letters, numbers, and hyphens")
    if not title:
        raise NovelAnimeProjectError("title must not be empty")
    if isinstance(episode_count, bool) or not isinstance(episode_count, int) or not 1 <= episode_count <= 999:
        raise NovelAnimeProjectError("episode_count must be an integer from 1 to 999")
    code = normalize_ip_code(ip_code)
    now = utc_timestamp()
    ip_id = f"IP-{code}"
    series_id = f"SER-{code}-01"
    season_id = "S01"
    episode_ids = [f"S01E{index:03d}" for index in range(1, episode_count + 1)]

    ip = _entity(ip_id, title)
    ip.update({"source_edition_ids": [], "series_ids": [series_id], "publication_allowed": False})
    series = _entity(series_id, f"{title}·剧集")
    series.update({"ip_id": ip_id, "season_ids": [season_id]})
    season = _entity(season_id, "第一季")
    season.update({"series_id": series_id, "arc_ids": [], "episode_ids": episode_ids, "season_number": 1})
    episodes = []
    for index, episode_id in enumerate(episode_ids, start=1):
        episode = _entity(episode_id, f"第{index}集（待定）")
        episode.update({
            "season_id": season_id,
            "arc_id": None,
            "episode_number": index,
            "target_duration_seconds": 60,
            "scene_ids": [],
            "continuity_in_ref": None,
            "continuity_delta_ref": None,
        })
        episodes.append(episode)

    project = {
        "schema_version": SCHEMA_VERSION,
        "project_type": "NOVEL_ANIME_SERIES",
        "project_id": project_id,
        "title": title,
        "revision": 1,
        "status": "DRAFT",
        "created_at": now,
        "updated_at": now,
        "ip": ip,
        "source_editions": [],
        "series": series,
        "seasons": [season],
        "arcs": [],
        "episodes": episodes,
        "scenes": [],
        "shots": [],
        "assets": [],
        "renders": [],
        "human_review": _review(),
    }
    validate_project(project)
    return project


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NovelAnimeProjectError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise NovelAnimeProjectError(f"{label} must be a list")
    return value


def _validate_common(entity: dict[str, Any], kind: str, label: str) -> str:
    entity_id = entity.get("id")
    if not isinstance(entity_id, str) or not ID_PATTERNS[kind].fullmatch(entity_id):
        raise NovelAnimeProjectError(f"{label}.id is not a valid {kind} ID")
    if not isinstance(entity.get("title"), str) or not entity["title"].strip():
        raise NovelAnimeProjectError(f"{label}.title must not be empty")
    if type(entity.get("revision")) is not int or entity["revision"] < 1:
        raise NovelAnimeProjectError(f"{label}.revision must be a positive integer")
    if entity.get("status") not in STATUSES:
        raise NovelAnimeProjectError(f"{label}.status is invalid")
    _require_list(entity.get("input_refs"), f"{label}.input_refs")
    _require_list(entity.get("source_refs"), f"{label}.source_refs")
    review = _require_object(entity.get("human_review"), f"{label}.human_review")
    if review.get("required") is not True or review.get("status") not in {"PENDING", "APPROVED", "CHANGES_REQUESTED"}:
        raise NovelAnimeProjectError(f"{label}.human_review is invalid")
    return entity_id


def _unique_ids(entities: Iterable[tuple[str, dict[str, Any]]]) -> dict[str, str]:
    seen: dict[str, str] = {}
    for label, entity in entities:
        entity_id = str(entity["id"])
        if entity_id in seen:
            raise NovelAnimeProjectError(f"duplicate entity ID {entity_id}: {seen[entity_id]} and {label}")
        seen[entity_id] = label
    return seen


def _ids(items: list[dict[str, Any]]) -> set[str]:
    return {str(item["id"]) for item in items}


def _check_refs(refs: Any, known: set[str], label: str, *, optional: bool = False) -> None:
    if optional and refs is None:
        return
    values = refs if isinstance(refs, list) else [refs]
    if any(not isinstance(ref, str) or ref not in known for ref in values):
        raise NovelAnimeProjectError(f"{label} contains an unknown reference")


def validate_project(payload: Any) -> dict[str, Any]:
    project = _require_object(payload, "project")
    if project.get("schema_version") != SCHEMA_VERSION or project.get("project_type") != "NOVEL_ANIME_SERIES":
        raise NovelAnimeProjectError("unsupported novel-anime project schema")
    project_id = project.get("project_id")
    if not isinstance(project_id, str) or not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise NovelAnimeProjectError("project.project_id is invalid")
    if project.get("status") not in STATUSES or type(project.get("revision")) is not int or project["revision"] < 1:
        raise NovelAnimeProjectError("project revision or status is invalid")
    for field in ("created_at", "updated_at", "title"):
        if not isinstance(project.get(field), str) or not project[field].strip():
            raise NovelAnimeProjectError(f"project.{field} must not be empty")
    review = _require_object(project.get("human_review"), "project.human_review")
    if review.get("required") is not True:
        raise NovelAnimeProjectError("project human review must remain required")

    ip = _require_object(project.get("ip"), "project.ip")
    series = _require_object(project.get("series"), "project.series")
    collections: dict[str, list[dict[str, Any]]] = {}
    typed_entities: list[tuple[str, dict[str, Any]]] = []
    _validate_common(ip, "ip", "ip")
    _validate_common(series, "series", "series")
    typed_entities.extend((("ip", ip), ("series", series)))
    for field, kind in ENTITY_LISTS.items():
        raw = _require_list(project.get(field), field)
        values: list[dict[str, Any]] = []
        for index, item in enumerate(raw):
            entity = _require_object(item, f"{field}[{index}]")
            _validate_common(entity, kind, f"{field}[{index}]")
            values.append(entity)
            typed_entities.append((f"{field}[{index}]", entity))
        collections[field] = values
    _unique_ids(typed_entities)

    ip_ids = {ip["id"]}
    series_ids = {series["id"]}
    source_ids = _ids(collections["source_editions"])
    season_ids = _ids(collections["seasons"])
    arc_ids = _ids(collections["arcs"])
    episode_ids = _ids(collections["episodes"])
    scene_ids = _ids(collections["scenes"])
    shot_ids = _ids(collections["shots"])
    asset_ids = _ids(collections["assets"])

    _check_refs(ip.get("source_edition_ids"), source_ids, "ip.source_edition_ids")
    _check_refs(ip.get("series_ids"), series_ids, "ip.series_ids")
    if ip.get("publication_allowed") is not False:
        raise NovelAnimeProjectError("new projects must start with publication_allowed=false")
    _check_refs(series.get("ip_id"), ip_ids, "series.ip_id")
    _check_refs(series.get("season_ids"), season_ids, "series.season_ids")

    for season in collections["seasons"]:
        _check_refs(season.get("series_id"), series_ids, f"{season['id']}.series_id")
        _check_refs(season.get("arc_ids"), arc_ids, f"{season['id']}.arc_ids")
        _check_refs(season.get("episode_ids"), episode_ids, f"{season['id']}.episode_ids")
    for arc in collections["arcs"]:
        _check_refs(arc.get("season_id"), season_ids, f"{arc['id']}.season_id")
        _check_refs(arc.get("episode_ids"), episode_ids, f"{arc['id']}.episode_ids")
        if not arc["id"].startswith(f"{arc['season_id']}-"):
            raise NovelAnimeProjectError(f"{arc['id']} must be scoped to its season")
    for episode in collections["episodes"]:
        _check_refs(episode.get("season_id"), season_ids, f"{episode['id']}.season_id")
        _check_refs(episode.get("arc_id"), arc_ids, f"{episode['id']}.arc_id", optional=True)
        _check_refs(episode.get("scene_ids"), scene_ids, f"{episode['id']}.scene_ids")
        if not episode["id"].startswith(episode["season_id"]):
            raise NovelAnimeProjectError(f"{episode['id']} must be scoped to its season")
    for scene in collections["scenes"]:
        _check_refs(scene.get("episode_id"), episode_ids, f"{scene['id']}.episode_id")
        _check_refs(scene.get("shot_ids"), shot_ids, f"{scene['id']}.shot_ids")
        if not scene["id"].startswith(f"{scene['episode_id']}-SC"):
            raise NovelAnimeProjectError(f"{scene['id']} must be scoped to its episode")
    for shot in collections["shots"]:
        _check_refs(shot.get("scene_id"), scene_ids, f"{shot['id']}.scene_id")
        _check_refs(shot.get("asset_refs"), asset_ids, f"{shot['id']}.asset_refs")
        if not shot["id"].startswith(f"{shot['scene_id']}-SH"):
            raise NovelAnimeProjectError(f"{shot['id']} must be scoped to its scene")
    all_targets = ip_ids | series_ids | season_ids | arc_ids | episode_ids | scene_ids | shot_ids | asset_ids
    for render in collections["renders"]:
        _check_refs(render.get("target_id"), all_targets, f"{render['id']}.target_id")
        _check_refs(render.get("asset_refs"), asset_ids, f"{render['id']}.asset_refs")
    return deepcopy(project)


def load_project(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelAnimeProjectError(f"cannot read project manifest: {error}") from error
    return validate_project(payload)


def _save_project(project_dir: Path, payload: dict[str, Any], *, overwrite: bool) -> Path:
    project = validate_project(payload)
    project_dir = Path(project_dir).expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    output = project_dir / MANIFEST_NAME
    if output.exists() and not overwrite:
        raise NovelAnimeProjectError(f"refusing to overwrite existing manifest: {output}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{MANIFEST_NAME}.", suffix=".tmp", dir=project_dir)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(project, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temp_name, output)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return output


def write_project(project_dir: Path, payload: dict[str, Any]) -> Path:
    return _save_project(project_dir, payload, overwrite=False)


def replace_project(project_dir: Path, payload: dict[str, Any]) -> Path:
    output = Path(project_dir).expanduser().resolve() / MANIFEST_NAME
    if not output.is_file():
        raise NovelAnimeProjectError("cannot replace a project manifest that does not exist")
    return _save_project(project_dir, payload, overwrite=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="create a one-season novel-anime project")
    create.add_argument("project_dir", type=Path)
    create.add_argument("--project-id", required=True)
    create.add_argument("--ip-code", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--episodes", type=int, default=5)
    validate = subparsers.add_parser("validate", help="validate an existing manifest")
    validate.add_argument("manifest", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "create":
            output = write_project(args.project_dir, build_project(args.project_id, args.ip_code, args.title, episode_count=args.episodes))
            result = {"status": "PASS", "manifest": str(output), "schema": str(SCHEMA_PATH), "episodes": args.episodes}
        else:
            project = load_project(args.manifest)
            result = {"status": "PASS", "project_id": project["project_id"], "episodes": len(project["episodes"])}
    except (NovelAnimeProjectError, OSError) as error:
        print(f"novel_anime_project: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
