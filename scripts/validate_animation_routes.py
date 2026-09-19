#!/usr/bin/env python3
"""Validate the machine-readable animation route policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "animation-routes.json"


class AnimationRouteConfigError(ValueError):
    pass


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnimationRouteConfigError(f"cannot read animation route config: {error}") from error
    return validate_config(payload)


def validate_config(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AnimationRouteConfigError("animation route config must be an object")
    if payload.get("schema_version") not in {1, 2}:
        raise AnimationRouteConfigError("schema_version must be 1 or 2")

    policy = payload.get("policy")
    routes = payload.get("routes")
    if not isinstance(policy, dict) or not isinstance(routes, list) or not routes:
        raise AnimationRouteConfigError("policy and non-empty routes are required")

    required_route_fields = {
        "id",
        "category",
        "status",
        "implemented",
        "remote",
        "generative",
        "requires_installation",
        "license_review_required",
        "adapter",
        "use_cases",
    }
    route_by_id: dict[str, dict[str, Any]] = {}
    for route in routes:
        if not isinstance(route, dict):
            raise AnimationRouteConfigError("each route must be an object")
        missing = required_route_fields.difference(route)
        if missing:
            raise AnimationRouteConfigError(f"route is missing fields: {', '.join(sorted(missing))}")
        route_id = str(route["id"])
        if not route_id or route_id in route_by_id:
            raise AnimationRouteConfigError(f"route id must be unique: {route_id}")
        if not isinstance(route["use_cases"], list) or not all(isinstance(item, str) and item for item in route["use_cases"]):
            raise AnimationRouteConfigError(f"route {route_id} use_cases must be a non-empty string list")
        route_by_id[route_id] = route

    default_route_id = str(policy.get("default_route") or "")
    default_route = route_by_id.get(default_route_id)
    if default_route is None:
        raise AnimationRouteConfigError("default_route must reference a configured route")
    if default_route["remote"] or default_route["generative"]:
        raise AnimationRouteConfigError("default route must be local and non-generative")
    if not default_route["implemented"] or default_route["status"] != "ACTIVE":
        raise AnimationRouteConfigError("default route must be ACTIVE and implemented")
    if policy.get("non_generative_first") is not True:
        raise AnimationRouteConfigError("non_generative_first must be true")
    if policy.get("remote_generation_default_enabled") is not False:
        raise AnimationRouteConfigError("remote generation must be disabled by default")
    if policy.get("publish_requires_human_confirmation") is not True:
        raise AnimationRouteConfigError("publishing must require human confirmation")

    animatic_route_id = str(policy.get("animatic_route") or default_route_id)
    animatic_route = route_by_id.get(animatic_route_id)
    if animatic_route is None:
        raise AnimationRouteConfigError("animatic_route must reference a configured route")
    if animatic_route["remote"] or animatic_route["generative"] or not animatic_route["implemented"]:
        raise AnimationRouteConfigError("animatic route must be implemented, local and non-generative")

    production_target_id = str(policy.get("production_target_route") or "")
    if production_target_id:
        production_target = route_by_id.get(production_target_id)
        if production_target is None:
            raise AnimationRouteConfigError("production_target_route must reference a configured route")
        if production_target["remote"] or production_target["generative"]:
            raise AnimationRouteConfigError("production target route must itself be local orchestration")
        if payload.get("schema_version") == 2 and production_target.get("role") != "FINAL_VISUAL_DEFAULT":
            raise AnimationRouteConfigError("schema v2 production target must be FINAL_VISUAL_DEFAULT")
        if payload.get("schema_version") == 2 and policy.get("blender_role") != "AUXILIARY_3D_CONTROL":
            raise AnimationRouteConfigError("schema v2 must demote Blender to AUXILIARY_3D_CONTROL")

    required_remote_gates = set(policy.get("remote_generation_requires") or [])
    if not {"upload_authorized", "confirm_billable"}.issubset(required_remote_gates):
        raise AnimationRouteConfigError("remote generation must require upload and billing confirmation")

    for route in routes:
        if route["remote"] and route["generative"] and route["status"] == "ACTIVE":
            raise AnimationRouteConfigError(f"remote generative route cannot be ACTIVE by default: {route['id']}")

    return payload


def summary(payload: dict[str, Any]) -> dict[str, Any]:
    routes = payload["routes"]
    return {
        "default_route": payload["policy"]["default_route"],
        "animatic_route": payload["policy"].get("animatic_route", payload["policy"]["default_route"]),
        "production_target_route": payload["policy"].get("production_target_route"),
        "active_local_routes": [
            item["id"]
            for item in routes
            if item["status"] == "ACTIVE" and not item["remote"] and not item["generative"]
        ],
        "candidate_routes": [item["id"] for item in routes if item["status"] in {"CANDIDATE", "OPTIONAL"}],
        "remote_generation_default_enabled": payload["policy"]["remote_generation_default_enabled"],
        "final_visual_mode": payload["policy"].get("final_visual_mode"),
        "blender_role": payload["policy"].get("blender_role"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        payload = load_config(args.config)
    except AnimationRouteConfigError as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "PASS", "result": summary(payload)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
