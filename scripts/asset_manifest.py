"""Validate resolved asset files and write a traceable manifest."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

try:
    from .project_state import StateError, load_run_state
except ImportError:
    from project_state import StateError, load_run_state


ASSET_ID = re.compile(r"A\d{3,}\Z")
FIELDS = {"asset_id", "scene_id", "type", "path", "source", "license", "generated", "provider"}


class AssetManifestError(ValueError):
    pass


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssetManifestError(f"{label} must be a non-empty string")
    return value.strip()


def write_asset_manifest(directory: Path, project_id: str, payload: Any) -> dict[str, Any]:
    state = load_run_state(directory, project_id)
    if state["status"] != "STORYBOARDED":
        raise StateError(f"asset manifest requires status STORYBOARDED; current status is {state['status']}")
    output = directory / "asset-manifest.json"
    if output.exists():
        raise StateError(f"refusing to overwrite existing asset manifest: {output}")
    try:
        storyboard = json.loads((directory / "storyboard.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AssetManifestError(f"invalid storyboard.json: {error}") from error
    scene_ids = {scene.get("scene_id") for scene in storyboard.get("scenes", []) if isinstance(scene, dict)}
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or set(payload) != {"schema_version", "assets"}:
        raise AssetManifestError("asset input must contain schema_version 1 and assets")
    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, list) or not raw_assets:
        raise AssetManifestError("assets must be a non-empty list")
    assets = []
    seen = set()
    root = directory.resolve()
    for index, raw in enumerate(raw_assets):
        if not isinstance(raw, dict) or set(raw) != FIELDS:
            raise AssetManifestError(f"assets[{index}] has invalid fields")
        asset_id = _text(raw.get("asset_id"), f"assets[{index}].asset_id")
        if not ASSET_ID.fullmatch(asset_id) or asset_id in seen:
            raise AssetManifestError(f"assets[{index}].asset_id must be unique and match A001")
        scene_id = _text(raw.get("scene_id"), f"assets[{index}].scene_id")
        if scene_id not in scene_ids:
            raise AssetManifestError(f"assets[{index}] references unknown scene {scene_id}")
        relative_path = Path(_text(raw.get("path"), f"assets[{index}].path"))
        resolved = (directory / relative_path).resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise AssetManifestError(f"assets[{index}].path must identify an existing file inside the project")
        generated = raw.get("generated")
        if type(generated) is not bool:
            raise AssetManifestError(f"assets[{index}].generated must be boolean")
        provider = raw.get("provider")
        if provider is not None and (not isinstance(provider, str) or not provider.strip()):
            raise AssetManifestError(f"assets[{index}].provider must be null or non-empty")
        if generated and provider is None:
            raise AssetManifestError(f"assets[{index}] generated assets require provider")
        assets.append({
            "asset_id": asset_id, "scene_id": scene_id, "type": _text(raw.get("type"), f"assets[{index}].type"),
            "path": relative_path.as_posix(), "source": _text(raw.get("source"), f"assets[{index}].source"),
            "license": _text(raw.get("license"), f"assets[{index}].license"), "generated": generated,
            "provider": provider.strip() if isinstance(provider, str) else None,
            "checksum": "sha256:" + hashlib.sha256(resolved.read_bytes()).hexdigest(),
        })
        seen.add(asset_id)
    descriptor, temp_name = tempfile.mkstemp(prefix=".asset-manifest.", suffix=".tmp", dir=directory)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump({"schema_version": 1, "project_id": project_id, "assets": assets}, file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(temp_name, output)
    return {"project_id": project_id, "asset_count": len(assets), "outputs": ["asset-manifest.json"], "state": state["status"]}
