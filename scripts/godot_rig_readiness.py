#!/usr/bin/env python3
"""Assess existing character rigs for Godot Skeleton2D/IK readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RIG_MANIFEST_V1 = Path("visual-bible/character-rigs.json")
RIG_MANIFEST_V2 = Path("visual-bible/character-rigs-v2.json")

PROFILE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "LOCAL_CUTOUT_RIG": ("head", "torso", "lower"),
    "GODOT_UPPER_BODY_IK": (
        "head", "torso",
        "upper_arm_l", "forearm_l", "hand_l",
        "upper_arm_r", "forearm_r", "hand_r",
    ),
    "GODOT_FULL_BODY_IK": (
        "head", "torso", "pelvis",
        "upper_arm_l", "forearm_l", "hand_l",
        "upper_arm_r", "forearm_r", "hand_r",
        "thigh_l", "shin_l", "foot_l",
        "thigh_r", "shin_r", "foot_r",
    ),
}


class GodotRigReadinessError(ValueError):
    pass


def layer_names(rig: dict[str, Any]) -> set[str]:
    return {
        str(layer.get("name") or "").strip().lower()
        for layer in rig.get("layers", [])
        if isinstance(layer, dict) and str(layer.get("name") or "").strip()
    }


def assess_rig(rig: dict[str, Any]) -> dict[str, Any]:
    present = layer_names(rig)
    profiles: dict[str, dict[str, Any]] = {}
    for profile, requirements in PROFILE_REQUIREMENTS.items():
        missing = [name for name in requirements if name not in present]
        profiles[profile] = {
            "ready": not missing,
            "required_layers": list(requirements),
            "missing_layers": missing,
        }
    return {
        "rig_id": str(rig.get("id") or ""),
        "character_id": str(rig.get("character_id") or ""),
        "character_name": str(rig.get("character_name") or rig.get("character_id") or ""),
        "present_layers": sorted(present),
        "profiles": profiles,
        "recommended_next_profile": (
            "GODOT_FULL_BODY_IK"
            if profiles["GODOT_FULL_BODY_IK"]["ready"]
            else "GODOT_UPPER_BODY_IK"
            if profiles["GODOT_UPPER_BODY_IK"]["ready"]
            else "RIG_V2_SEGMENTATION"
        ),
    }


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GodotRigReadinessError(f"cannot read character rigs: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("rigs"), list):
        raise GodotRigReadinessError(f"character rig manifest is invalid: {path.name}")
    return payload


def load_manifest(project_dir: Path) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    manifests: list[tuple[int, Path, dict[str, Any]]] = []
    for priority, relative in ((1, RIG_MANIFEST_V1), (2, RIG_MANIFEST_V2)):
        path = project_dir / relative
        if path.is_file():
            manifests.append((priority, path, _read_manifest(path)))
    if not manifests:
        raise GodotRigReadinessError("cannot read character rigs: no V1 or V2 manifest found")

    selected: dict[str, dict[str, Any]] = {}
    sources: dict[str, str] = {}
    project_id = project_dir.name
    for priority, path, payload in manifests:
        project_id = str(payload.get("project_id") or project_id)
        for rig in payload["rigs"]:
            if not isinstance(rig, dict):
                continue
            key = str(rig.get("character_id") or rig.get("id") or "")
            if not key:
                continue
            current = selected.get(key)
            current_priority = int(current.get("_manifest_priority", 0)) if current else 0
            if priority >= current_priority:
                item = dict(rig)
                item["_manifest_priority"] = priority
                item["_source_manifest"] = path.relative_to(project_dir).as_posix()
                selected[key] = item
                sources[key] = path.relative_to(project_dir).as_posix()

    rigs = []
    for item in selected.values():
        normalized = dict(item)
        normalized.pop("_manifest_priority", None)
        rigs.append(normalized)
    return {
        "schema_version": "merged",
        "project_id": project_id,
        "rigs": rigs,
        "source_manifests": sorted(set(sources.values())),
    }


def summarize_project(project_dir: Path, rig_id: str | None = None) -> dict[str, Any]:
    payload = load_manifest(project_dir)
    rigs = [item for item in payload["rigs"] if isinstance(item, dict)]
    if rig_id:
        rigs = [item for item in rigs if item.get("id") == rig_id]
        if not rigs:
            raise GodotRigReadinessError(f"rig not found: {rig_id}")
    assessments = [assess_rig(rig) for rig in rigs]
    return {
        "project_id": payload.get("project_id") or Path(project_dir).name,
        "rig_count": len(assessments),
        "local_cutout_ready": sum(1 for item in assessments if item["profiles"]["LOCAL_CUTOUT_RIG"]["ready"]),
        "godot_upper_body_ik_ready": sum(1 for item in assessments if item["profiles"]["GODOT_UPPER_BODY_IK"]["ready"]),
        "godot_full_body_ik_ready": sum(1 for item in assessments if item["profiles"]["GODOT_FULL_BODY_IK"]["ready"]),
        "rigs": assessments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--rig-id")
    args = parser.parse_args()
    try:
        result = summarize_project(args.project_dir, args.rig_id)
    except GodotRigReadinessError as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
