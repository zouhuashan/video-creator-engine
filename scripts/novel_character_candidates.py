#!/usr/bin/env python3
"""Persist review-only local character candidates without storing novel text."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp

OUTPUT = Path("story-bible/image-studio-character-candidates.json")


class NovelCharacterCandidateError(ValueError):
    pass


def build_character_candidates(
    project_dir: Path,
    *,
    source_file_name: str,
    source_sha256: str,
    provider: str,
    characters: list[dict[str, Any]],
) -> dict[str, Any]:
    project_dir = Path(project_dir).resolve()
    project = load_project(project_dir / MANIFEST_NAME)
    cleaned = []
    for item in characters:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        character_id = str(item.get("id") or "").strip()
        if not name or not character_id:
            continue
        mentions = item.get("mentions") if isinstance(item.get("mentions"), list) else []
        cleaned.append({
            "id": character_id,
            "name": name,
            "aliases": [str(value) for value in item.get("aliases", []) if str(value).strip()],
            "mentions": mentions,
            "total_mentions": int(item.get("total_mentions") or 0),
            "needs_review": True,
        })
    cleaned.sort(key=lambda item: (-int(item["total_mentions"]), str(item["name"])))
    return {
        "schema_version": 1,
        "project_id": project["project_id"],
        "source_file_name": Path(source_file_name).name,
        "source_sha256": str(source_sha256),
        "provider": str(provider),
        "created_at": utc_timestamp(),
        "full_text_stored": False,
        "characters": cleaned,
        "human_review_required": True,
    }


def write_character_candidates(project_dir: Path, payload: dict[str, Any]) -> Path:
    project_dir = Path(project_dir).resolve()
    output = project_dir / OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".character-candidates.", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, output)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return output


def load_character_candidates(project_dir: Path) -> dict[str, Any] | None:
    path = Path(project_dir).resolve() / OUTPUT
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelCharacterCandidateError(f"cannot read character candidates: {error}") from error
    if not isinstance(payload, dict):
        raise NovelCharacterCandidateError("character candidates must be an object")
    return payload


def summary(project_dir: Path) -> dict[str, Any]:
    payload = load_character_candidates(project_dir)
    if not payload:
        return {"ready": False, "character_count": 0, "characters": [], "full_text_stored": False}
    characters = payload.get("characters") if isinstance(payload.get("characters"), list) else []
    return {
        "ready": bool(characters),
        "character_count": len(characters),
        "characters": [
            {"id": item.get("id"), "name": item.get("name"), "total_mentions": item.get("total_mentions", 0)}
            for item in characters[:12]
            if isinstance(item, dict)
        ],
        "provider": payload.get("provider"),
        "source_file_name": payload.get("source_file_name"),
        "full_text_stored": False,
    }


__all__ = [
    "OUTPUT",
    "NovelCharacterCandidateError",
    "build_character_candidates",
    "write_character_candidates",
    "load_character_candidates",
    "summary",
]
