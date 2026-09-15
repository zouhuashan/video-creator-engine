"""Load deterministic, seekable HyperFrames motion defaults."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

try:
    from .project_state import ROOT
except ImportError:
    from project_state import ROOT


CONFIG_PATH = ROOT / "config" / "hyperframes-motion.json"
PRESET_DIR = ROOT / "brand" / "motion"
STYLE_PRESET_NAMES = ("minimal", "tech", "review", "warning", "comparison", "tutorial")
CONTENT_TYPES = (
    "title",
    "data",
    "comparison_table",
    "ui",
    "card",
    "price",
    "ranking",
    "steps",
    "flowchart",
    "emphasis_text",
)
REQUIRED_MOTION_FIELDS = {"pattern", "duration_frames", "easing", "properties"}
REQUIRED_PRESET_FIELDS = {"schema_version", "name", "purpose", "palette", "typography", "shape", "motion"}
HEX_COLOR = re.compile(r"^#[0-9A-F]{6}([0-9A-F]{2})?$")


class HyperFramesMotionError(ValueError):
    pass


def load_motion_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HyperFramesMotionError(f"invalid HyperFrames motion config: {error}") from error

    if config.get("schema_version") != 1 or config.get("renderer") != "hyperframes":
        raise HyperFramesMotionError("unsupported HyperFrames motion config")
    if config.get("runtime") != "gsap":
        raise HyperFramesMotionError("default HyperFrames runtime must be gsap")
    defaults = config.get("defaults")
    if not isinstance(defaults, dict) or defaults.get("fps") != 30 or defaults.get("seekable") is not True:
        raise HyperFramesMotionError("motion defaults must use 30 fps and seekable timelines")

    motions = config.get("motions")
    if not isinstance(motions, dict) or tuple(motions) != CONTENT_TYPES:
        raise HyperFramesMotionError("motion config must declare every supported content type in order")
    for content_type, motion in motions.items():
        if not isinstance(motion, dict) or not REQUIRED_MOTION_FIELDS.issubset(motion):
            raise HyperFramesMotionError(f"{content_type}: incomplete motion declaration")
        if not isinstance(motion["duration_frames"], int) or motion["duration_frames"] <= 0:
            raise HyperFramesMotionError(f"{content_type}: duration_frames must be positive")
        if "stagger_frames" in motion and (
            not isinstance(motion["stagger_frames"], int) or motion["stagger_frames"] < 0
        ):
            raise HyperFramesMotionError(f"{content_type}: stagger_frames must be non-negative")
        if not isinstance(motion["properties"], list) or not motion["properties"]:
            raise HyperFramesMotionError(f"{content_type}: properties must be a non-empty list")
    return config


def motion_for(content_type: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    active = config or load_motion_config()
    try:
        motion = active["motions"][content_type]
    except (KeyError, TypeError) as error:
        raise HyperFramesMotionError(f"unsupported motion content type: {content_type}") from error
    return copy.deepcopy(motion)


def build_motion_plan(
    elements: list[dict[str, Any]], config: dict[str, Any] | None = None
) -> dict[str, Any]:
    active = config or load_motion_config()
    if not isinstance(elements, list) or not elements:
        raise HyperFramesMotionError("motion plan requires at least one element")

    seen_ids: set[str] = set()
    planned: list[dict[str, Any]] = []
    for element in elements:
        if not isinstance(element, dict):
            raise HyperFramesMotionError("motion plan elements must be objects")
        element_id = element.get("id")
        content_type = element.get("content_type")
        start_frame = element.get("start_frame", 0)
        if not isinstance(element_id, str) or not element_id or element_id in seen_ids:
            raise HyperFramesMotionError("motion element ids must be unique non-empty strings")
        if not isinstance(start_frame, int) or start_frame < 0:
            raise HyperFramesMotionError(f"{element_id}: start_frame must be a non-negative integer")
        seen_ids.add(element_id)
        planned.append(
            {
                "id": element_id,
                "content_type": content_type,
                "start_frame": start_frame,
                "motion": motion_for(str(content_type), active),
            }
        )

    return {
        "renderer": active["renderer"],
        "runtime": active["runtime"],
        "fps": active["defaults"]["fps"],
        "seekable": active["defaults"]["seekable"],
        "reduced_motion": active["defaults"]["reduced_motion"],
        "elements": planned,
    }


def load_style_preset(name: str, preset_dir: Path = PRESET_DIR) -> dict[str, Any]:
    if name not in STYLE_PRESET_NAMES:
        raise HyperFramesMotionError(f"unsupported HyperFrames style preset: {name}")
    path = preset_dir / f"{name}.json"
    try:
        preset = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HyperFramesMotionError(f"invalid HyperFrames style preset {name}: {error}") from error

    if not isinstance(preset, dict) or not REQUIRED_PRESET_FIELDS.issubset(preset):
        raise HyperFramesMotionError(f"{name}: incomplete style preset")
    if preset["schema_version"] != 1 or preset["name"] != name:
        raise HyperFramesMotionError(f"{name}: preset identity does not match its filename")
    palette = preset["palette"]
    required_colors = {"background", "surface", "foreground", "muted", "accent"}
    if not isinstance(palette, dict) or not required_colors.issubset(palette):
        raise HyperFramesMotionError(f"{name}: palette is incomplete")
    if any(not isinstance(value, str) or not HEX_COLOR.fullmatch(value) for value in palette.values()):
        raise HyperFramesMotionError(f"{name}: palette colors must use uppercase hex values")
    typography = preset["typography"]
    if not isinstance(typography, dict) or not {"display", "body", "headline_weight", "body_weight"}.issubset(typography):
        raise HyperFramesMotionError(f"{name}: typography is incomplete")
    motion = preset["motion"]
    if not isinstance(motion, dict) or not {"duration_scale", "stagger_scale", "transition"}.issubset(motion):
        raise HyperFramesMotionError(f"{name}: motion modifiers are incomplete")
    if not all(isinstance(motion[key], (int, float)) and motion[key] > 0 for key in ("duration_scale", "stagger_scale")):
        raise HyperFramesMotionError(f"{name}: motion scales must be positive")
    return preset


def apply_style_preset(
    plan: dict[str, Any], preset_name: str, preset_dir: Path = PRESET_DIR
) -> dict[str, Any]:
    preset = load_style_preset(preset_name, preset_dir)
    styled = copy.deepcopy(plan)
    if not isinstance(styled.get("elements"), list):
        raise HyperFramesMotionError("invalid motion plan: elements are missing")

    duration_scale = preset["motion"]["duration_scale"]
    stagger_scale = preset["motion"]["stagger_scale"]
    for element in styled["elements"]:
        motion = element.get("motion", {})
        if "duration_frames" not in motion:
            raise HyperFramesMotionError("invalid motion plan: duration_frames is missing")
        motion["duration_frames"] = max(1, round(motion["duration_frames"] * duration_scale))
        if "stagger_frames" in motion:
            motion["stagger_frames"] = max(1, round(motion["stagger_frames"] * stagger_scale))
    styled["style_preset"] = preset["name"]
    styled["style"] = {
        "purpose": preset["purpose"],
        "palette": preset["palette"],
        "typography": preset["typography"],
        "shape": preset["shape"],
        "transition": preset["motion"]["transition"],
    }
    return styled
