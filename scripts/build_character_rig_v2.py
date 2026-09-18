#!/usr/bin/env python3
"""Build validated, aligned Rig V2 assets for Godot Skeleton2D/IK."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.godot_rig_readiness import PROFILE_REQUIREMENTS
from scripts.novel_anime_repository import NovelAnimeRepository

MANIFEST = Path("visual-bible/character-rigs-v2.json")
PARENTS = {
    "head": "torso",
    "torso": None,
    "pelvis": "torso",
    "upper_arm_l": "torso",
    "forearm_l": "upper_arm_l",
    "hand_l": "forearm_l",
    "upper_arm_r": "torso",
    "forearm_r": "upper_arm_r",
    "hand_r": "forearm_r",
    "thigh_l": "pelvis",
    "shin_l": "thigh_l",
    "foot_l": "shin_l",
    "thigh_r": "pelvis",
    "shin_r": "thigh_r",
    "foot_r": "shin_r",
}
JOINT_CHAINS = {
    "left_arm": ["upper_arm_l", "forearm_l", "hand_l"],
    "right_arm": ["upper_arm_r", "forearm_r", "hand_r"],
    "left_leg": ["thigh_l", "shin_l", "foot_l"],
    "right_leg": ["thigh_r", "shin_r", "foot_r"],
}


class RigV2Error(ValueError):
    pass


def template(character_id: str, rig_id: str, profile: str, character_name: str = "") -> dict[str, Any]:
    if profile not in {"GODOT_UPPER_BODY_IK", "GODOT_FULL_BODY_IK"}:
        raise RigV2Error(f"unsupported Rig V2 profile: {profile}")
    return {
        "schema_version": 1,
        "rig_id": rig_id,
        "character_id": character_id,
        "character_name": character_name or character_id,
        "profile": profile,
        "source_asset_id": "",
        "layers": [
            {
                "name": name,
                "path": "",
                "parent": PARENTS[name],
                "pivot": {"x": 0, "y": 0},
                "z_index": index,
            }
            for index, name in enumerate(PROFILE_REQUIREMENTS[profile])
        ],
    }


def _read_spec(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RigV2Error(f"cannot read Rig V2 spec: {error}") from error
    if not isinstance(payload, dict):
        raise RigV2Error("Rig V2 spec must be an object")
    return payload


def _project_file(project_dir: Path, relative: str) -> Path:
    rel = Path(str(relative))
    path = (project_dir / rel).resolve()
    if rel.is_absolute() or (path != project_dir and project_dir not in path.parents):
        raise RigV2Error(f"layer path escapes project: {relative}")
    if not path.is_file():
        raise RigV2Error(f"layer file not found: {relative}")
    return path


def _validate_layers(project_dir: Path, spec: dict[str, Any]) -> tuple[list[dict[str, Any]], tuple[int, int]]:
    profile = str(spec.get("profile") or "")
    if profile not in {"GODOT_UPPER_BODY_IK", "GODOT_FULL_BODY_IK"}:
        raise RigV2Error(f"unsupported Rig V2 profile: {profile}")

    raw_layers = spec.get("layers")
    if not isinstance(raw_layers, list):
        raise RigV2Error("layers must be a list")

    by_name: dict[str, dict[str, Any]] = {}
    expected_size: tuple[int, int] | None = None
    validated: list[dict[str, Any]] = []
    for layer in raw_layers:
        if not isinstance(layer, dict):
            raise RigV2Error("each layer must be an object")
        name = str(layer.get("name") or "").strip()
        if name not in PARENTS or name in by_name:
            raise RigV2Error(f"invalid or duplicate layer: {name}")
        if layer.get("parent") != PARENTS[name]:
            raise RigV2Error(f"layer {name} parent must be {PARENTS[name]!r}")
        pivot = layer.get("pivot")
        if not isinstance(pivot, dict) or not all(isinstance(pivot.get(axis), (int, float)) for axis in ("x", "y")):
            raise RigV2Error(f"layer {name} requires numeric pivot x/y")
        path = _project_file(project_dir, str(layer.get("path") or ""))
        try:
            with Image.open(path) as image:
                if image.mode != "RGBA":
                    raise RigV2Error(f"layer {name} must be RGBA")
                if image.getchannel("A").getbbox() is None:
                    raise RigV2Error(f"layer {name} is fully transparent")
                if expected_size is None:
                    expected_size = image.size
                elif image.size != expected_size:
                    raise RigV2Error(f"layer {name} size {image.size} != {expected_size}")
                width, height = image.size
        except OSError as error:
            raise RigV2Error(f"cannot read layer {name}: {error}") from error
        if not 0 <= float(pivot["x"]) <= width or not 0 <= float(pivot["y"]) <= height:
            raise RigV2Error(f"layer {name} pivot is outside canvas")
        normalized = {
            "name": name,
            "path": path.relative_to(project_dir).as_posix(),
            "parent": PARENTS[name],
            "pivot": {"x": float(pivot["x"]), "y": float(pivot["y"])},
            "z_index": int(layer.get("z_index", 0)),
        }
        by_name[name] = normalized
        validated.append(normalized)

    missing = [name for name in PROFILE_REQUIREMENTS[profile] if name not in by_name]
    if missing:
        raise RigV2Error(f"{profile} missing layers: {', '.join(missing)}")
    return validated, expected_size or (0, 0)


def build_rig_v2(project_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    layers, canvas = _validate_layers(project_dir, spec)
    rig_id = str(spec.get("rig_id") or "").strip()
    character_id = str(spec.get("character_id") or "").strip()
    source_asset_id = str(spec.get("source_asset_id") or "").strip()
    if not rig_id or not character_id or not source_asset_id:
        raise RigV2Error("rig_id, character_id and source_asset_id are required")

    repository = NovelAnimeRepository(project_dir)
    asset_prefix = character_id.removeprefix("CHR-")
    registered_layers = []
    for layer in layers:
        name = layer["name"]
        asset_id = f"AST-RIG2-{asset_prefix}-{name.upper()}"
        registered = repository.register_asset(
            asset_id,
            "character",
            project_dir / layer["path"],
            metadata={
                "title": f"{spec.get('character_name') or character_id} Rig V2 {name}",
                "rig_id": rig_id,
                "rig_profile": spec["profile"],
                "layer": name,
                "parent": layer["parent"],
                "pivot": layer["pivot"],
                "z_index": layer["z_index"],
            },
            source_entity_ids=[source_asset_id],
        )
        registered_layers.append({**layer, "asset_id": registered["asset_id"], "version": registered["version"]})

    active_names = {item["name"] for item in registered_layers}
    chains = {
        name: chain
        for name, chain in JOINT_CHAINS.items()
        if all(part in active_names for part in chain)
    }
    rig = {
        "id": rig_id,
        "rig_version": 2,
        "character_id": character_id,
        "character_name": str(spec.get("character_name") or character_id),
        "source_asset_id": source_asset_id,
        "profile": spec["profile"],
        "canvas": {"width": canvas[0], "height": canvas[1]},
        "layers": registered_layers,
        "joint_chains": chains,
        "human_review": {
            "required": True,
            "status": "PENDING",
            "reviewed_at": None,
            "reviewed_by": None,
        },
    }

    path = project_dir / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    rigs = [item for item in existing.get("rigs", []) if isinstance(item, dict) and item.get("id") != rig_id]
    rigs.append(rig)
    payload = {
        "schema_version": 2,
        "project_id": project_dir.name,
        "revision": int(existing.get("revision", 0)) + 1,
        "rigs": rigs,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"manifest": MANIFEST.as_posix(), "rig": rig}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    make_template = sub.add_parser("template")
    make_template.add_argument("--character-id", required=True)
    make_template.add_argument("--rig-id", required=True)
    make_template.add_argument("--profile", choices=("GODOT_UPPER_BODY_IK", "GODOT_FULL_BODY_IK"), required=True)
    make_template.add_argument("--character-name", default="")
    make_template.add_argument("--output", required=True, type=Path)

    build = sub.add_parser("build")
    build.add_argument("project_dir", type=Path)
    build.add_argument("--spec", required=True, type=Path)

    args = parser.parse_args()
    try:
        if args.command == "template":
            payload = template(args.character_id, args.rig_id, args.profile, args.character_name)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = {"output": str(args.output)}
        else:
            result = build_rig_v2(args.project_dir, _read_spec(args.spec))
    except (RigV2Error, OSError, RuntimeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
