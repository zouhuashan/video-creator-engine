#!/usr/bin/env python3
"""Project-local reusable modern drama assets; no provider or network calls."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from scripts.novel_anime_project import utc_timestamp

OUTPUT = Path("rendering/modern-assets.json")
FILES = Path("rendering/modern-assets/files")
KINDS = ("character", "scene", "stock")
CHARACTER_VIEWS = ("front", "left_45", "right_45", "left_profile", "right_profile", "half_body", "full_body", "seated", "standing")
EXPRESSIONS = ("neutral", "happy", "sad", "angry", "shocked", "nervous", "crying", "thinking")
SCENE_VARIANTS = ("day", "night", "warm", "cool", "wide", "medium", "close")
SCREEN_TEMPLATES = ("chat", "incoming_call", "news", "report", "transfer")


class ModernAssetLibraryError(ValueError):
    pass


def _empty() -> dict[str, Any]:
    return {"schema_version": 1, "revision": 1, "updated_at": utc_timestamp(), "assets": []}


def _atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".modern-assets-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def load_library(project: Path) -> dict[str, Any]:
    project = Path(project).resolve()
    path = project / OUTPUT
    if not path.is_file():
        return _empty()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModernAssetLibraryError(f"cannot read modern asset library: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("assets"), list):
        raise ModernAssetLibraryError("modern asset library format is invalid")
    seen = set()
    for asset in payload["assets"]:
        if not isinstance(asset, dict) or asset.get("kind") not in KINDS or not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", str(asset.get("entity_id") or "")):
            raise ModernAssetLibraryError("asset kind or entity_id is invalid")
        key = (asset["kind"], asset["entity_id"], asset.get("variant"), asset.get("expression"))
        if key in seen:
            raise ModernAssetLibraryError("duplicate asset variant")
        seen.add(key)
        relative = Path(str(asset.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts or not str(relative).startswith(str(FILES) + "/"):
            raise ModernAssetLibraryError("asset path must stay inside project library")
        review_status = str(asset.get("review_status") or "PENDING")
        if review_status not in {"PENDING", "APPROVED", "REJECTED"}:
            raise ModernAssetLibraryError("asset review_status is invalid")
        asset.setdefault("review_status", review_status)
        asset.setdefault("review_note", "")
        asset.setdefault("reviewed_at", None)
    return payload


def register_asset(project: Path, *, kind: str, entity_id: str, variant: str, content: bytes, extension: str, expression: str = "neutral", license_note: str = "") -> dict[str, Any]:
    project = Path(project).resolve()
    if kind not in KINDS or not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", entity_id):
        raise ModernAssetLibraryError("invalid asset kind or entity_id")
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", variant):
        raise ModernAssetLibraryError("invalid asset variant")
    if kind == "character" and expression not in EXPRESSIONS:
        raise ModernAssetLibraryError("unsupported expression")
    if kind != "character":
        expression = "neutral"
    if extension not in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}:
        raise ModernAssetLibraryError("unsupported image or video file")
    if not content or len(content) > 40 * 1024 * 1024:
        raise ModernAssetLibraryError("asset must be 1 byte to 40 MB")
    if kind == "stock" and extension not in {".mp4", ".mov", ".webm"}:
        raise ModernAssetLibraryError("stock footage must be video")
    if kind == "stock" and license_note not in {"owned", "CC0", "licensed"}:
        raise ModernAssetLibraryError("stock footage requires an owned, CC0, or licensed rights declaration")
    if kind != "stock" and extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ModernAssetLibraryError("character and scene assets must be images")
    digest = hashlib.sha256(content).hexdigest()
    relative = FILES / f"{digest}{extension}"
    target = project / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        handle, temporary = tempfile.mkstemp(prefix=".asset-", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(content)
            os.replace(temporary, target)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise
    library = load_library(project)
    key = (kind, entity_id, variant, expression)
    assets = [item for item in library["assets"] if (item["kind"], item["entity_id"], item["variant"], item["expression"]) != key]
    item = {"kind": kind, "entity_id": entity_id, "variant": variant, "expression": expression, "path": relative.as_posix(), "sha256": digest, "bytes": len(content), "license_note": license_note if kind == "stock" else "", "created_at": utc_timestamp(), "review_status": "PENDING", "review_note": "", "reviewed_at": None}
    assets.append(item)
    library.update({"assets": sorted(assets, key=lambda entry: (entry["kind"], entry["entity_id"], entry["variant"], entry["expression"])), "revision": int(library["revision"]) + 1, "updated_at": utc_timestamp()})
    _atomic(project / OUTPUT, library)
    return item


def review_asset(project: Path, asset_path: str, status: str, note: str = "") -> dict[str, Any]:
    """Persist a human review decision for one reusable asset."""
    project = Path(project).resolve()
    status = str(status or "").strip().upper()
    note = str(note or "").strip()
    if status not in {"PENDING", "APPROVED", "REJECTED"}:
        raise ModernAssetLibraryError("review status must be PENDING, APPROVED, or REJECTED")
    library = load_library(project)
    match = next((item for item in library["assets"] if item["path"] == asset_path), None)
    if match is None:
        raise ModernAssetLibraryError("unknown modern asset path")
    match["review_status"] = status
    match["review_note"] = note
    match["reviewed_at"] = utc_timestamp() if status != "PENDING" else None
    library["revision"] = int(library["revision"]) + 1
    library["updated_at"] = utc_timestamp()
    _atomic(project / OUTPUT, library)
    return match


def approved_entities(project: Path, kind: str) -> set[str]:
    """Return entity IDs that have at least one approved reusable asset."""
    if kind not in {"character", "scene"}:
        raise ModernAssetLibraryError("approved_entities only supports character or scene")
    return {
        str(item["entity_id"])
        for item in load_library(project)["assets"]
        if item.get("kind") == kind and item.get("review_status") == "APPROVED"
    }
