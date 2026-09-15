"""Choose the highest-priority available asset route for storyboard scenes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .project_state import ROOT
except ImportError:
    from project_state import ROOT


CONFIG_PATH = ROOT / "config" / "asset-routing.json"


class AssetRoutingError(ValueError):
    pass


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AssetRoutingError(f"invalid asset routing config: {error}") from error
    priority = config.get("priority") if isinstance(config, dict) else None
    routes = config.get("visual_type_routes") if isinstance(config, dict) else None
    if config.get("schema_version") != 1 or not isinstance(priority, list) or not isinstance(routes, dict):
        raise AssetRoutingError("unsupported asset routing config")
    if priority != ["real_media", "licensed_media", "hyperframes", "generative_media"]:
        raise AssetRoutingError("asset routing priority must be real, licensed, HyperFrames, then generative")
    return config


def choose_route(visual_type: str, available_routes: list[str], config: dict[str, Any] | None = None) -> dict[str, Any]:
    active = config or load_config()
    if visual_type not in active["visual_type_routes"]:
        raise AssetRoutingError(f"unsupported visual_type: {visual_type}")
    if not isinstance(available_routes, list) or any(route not in active["priority"] for route in available_routes):
        raise AssetRoutingError("available_routes must contain only configured routes")
    eligible = active["visual_type_routes"][visual_type]
    chosen = next((route for route in active["priority"] if route in eligible and route in available_routes), None)
    return {"visual_type": visual_type, "route": chosen, "status": "ROUTED" if chosen else "MISSING_ASSET"}
