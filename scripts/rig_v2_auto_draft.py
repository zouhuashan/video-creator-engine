#!/usr/bin/env python3
"""Propose editable upper-body Rig V2 polygons and pivots from a local source image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image


class RigV2AutoDraftError(ValueError):
    pass


def _safe_source(project_dir: Path, relative: str) -> Path:
    project_dir = Path(project_dir).expanduser().resolve()
    rel = Path(str(relative))
    path = (project_dir / rel).resolve()
    if rel.is_absolute() or (path != project_dir and project_dir not in path.parents):
        raise RigV2AutoDraftError(f"path escapes project: {relative}")
    if not path.is_file():
        raise RigV2AutoDraftError(f"source image not found: {relative}")
    return path


def _rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _visible_bbox(alpha: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    left, top, right, bottom = box
    left = max(0, min(alpha.width, left))
    right = max(left + 1, min(alpha.width, right))
    top = max(0, min(alpha.height, top))
    bottom = max(top + 1, min(alpha.height, bottom))
    local = alpha.crop((left, top, right, bottom)).getbbox()
    if not local:
        return None
    return (left + local[0], top + local[1], left + local[2], top + local[3])


def _band_bbox(alpha: Image.Image, bbox: tuple[int, int, int, int], start: float, end: float) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    height = bottom - top
    y0 = int(round(top + height * start))
    y1 = int(round(top + height * end))
    visible = _visible_bbox(alpha, (left, y0, right, y1))
    return visible or (left, y0, right, y1)


def _padded(box: tuple[int, int, int, int], pad_x: float, pad_y: float, canvas: tuple[int, int]) -> tuple[float, float, float, float]:
    left, top, right, bottom = box
    width, height = canvas
    return (
        _clamp(left - pad_x, 0, width),
        _clamp(top - pad_y, 0, height),
        _clamp(right + pad_x, 0, width),
        _clamp(bottom + pad_y, 0, height),
    )


def propose_upper_body(project_dir: Path, source_path: str) -> dict[str, Any]:
    source = _safe_source(project_dir, source_path)
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        raise RigV2AutoDraftError("source image has no visible pixels")

    left, top, right, bottom = bbox
    body_w = float(right - left)
    body_h = float(bottom - top)
    cx = (left + right) / 2.0
    canvas = (image.width, image.height)

    # V1 already uses roughly 0-.34 head / .24-.70 torso.  The draft keeps
    # those proven proportions, then splits side masses into overlapping arm
    # bands. Overlap is deliberate: it is safer for cutout joints than gaps.
    head_box = _padded(_band_bbox(alpha, bbox, 0.00, 0.34), body_w * 0.015, body_h * 0.01, canvas)
    torso_band = _band_bbox(alpha, bbox, 0.23, 0.68)
    torso_half = body_w * 0.24
    torso_box = (
        _clamp(cx - torso_half, 0, image.width),
        float(torso_band[1]),
        _clamp(cx + torso_half, 0, image.width),
        float(torso_band[3]),
    )

    shoulder_y = top + body_h * 0.30
    elbow_y = top + body_h * 0.47
    wrist_y = top + body_h * 0.61
    hand_end_y = top + body_h * 0.72
    inner = body_w * 0.10

    # For a front-facing character, the character's left side is screen-right.
    screen_left_outer = float(left)
    screen_right_outer = float(right)
    screen_left_inner = cx - inner
    screen_right_inner = cx + inner

    layers: dict[str, dict[str, Any]] = {
        "head": {
            "polygon": _rect(*head_box),
            "pivot": {"x": cx, "y": top + body_h * 0.30},
            "confidence": "HIGH",
            "note": "V1 头部透明像素带自动提取；检查长发是否需要保留在头层。",
        },
        "torso": {
            "polygon": _rect(*torso_box),
            "pivot": {"x": cx, "y": top + body_h * 0.46},
            "confidence": "HIGH",
            "note": "按身体中心自动生成；宽袖会与手臂层重叠，这是允许的。",
        },
        "upper_arm_l": {
            "polygon": _rect(screen_right_inner, shoulder_y, screen_right_outer, elbow_y + body_h * 0.04),
            "pivot": {"x": cx + body_w * 0.18, "y": shoulder_y},
            "confidence": "MEDIUM",
            "note": "人物左上臂（画面右侧）自动草稿；肩部允许与躯干重叠。",
        },
        "forearm_l": {
            "polygon": _rect(screen_right_inner, elbow_y - body_h * 0.04, screen_right_outer, wrist_y + body_h * 0.04),
            "pivot": {"x": cx + body_w * 0.24, "y": elbow_y},
            "confidence": "MEDIUM",
            "note": "人物左前臂（画面右侧）自动草稿；重点检查袖摆是否过宽。",
        },
        "hand_l": {
            "polygon": _rect(cx + body_w * 0.06, wrist_y - body_h * 0.04, screen_right_outer, hand_end_y),
            "pivot": {"x": cx + body_w * 0.28, "y": wrist_y},
            "confidence": "LOW",
            "note": "人物左手（画面右侧）最难自动判断，优先检查手腕 Pivot 和手掌区域。",
        },
        "upper_arm_r": {
            "polygon": _rect(screen_left_outer, shoulder_y, screen_left_inner, elbow_y + body_h * 0.04),
            "pivot": {"x": cx - body_w * 0.18, "y": shoulder_y},
            "confidence": "MEDIUM",
            "note": "人物右上臂（画面左侧）自动草稿；肩部允许与躯干重叠。",
        },
        "forearm_r": {
            "polygon": _rect(screen_left_outer, elbow_y - body_h * 0.04, screen_left_inner, wrist_y + body_h * 0.04),
            "pivot": {"x": cx - body_w * 0.24, "y": elbow_y},
            "confidence": "MEDIUM",
            "note": "人物右前臂（画面左侧）自动草稿；重点检查袖摆。",
        },
        "hand_r": {
            "polygon": _rect(screen_left_outer, wrist_y - body_h * 0.04, cx - body_w * 0.06, hand_end_y),
            "pivot": {"x": cx - body_w * 0.28, "y": wrist_y},
            "confidence": "LOW",
            "note": "人物右手（画面左侧）最难自动判断，优先检查手腕 Pivot 和手掌区域。",
        },
    }

    for index, name in enumerate(layers):
        layers[name]["z_index"] = index

    return {
        "status": "DRAFT",
        "provider": "local_geometry_heuristic",
        "generative": False,
        "remote": False,
        "source_path": source.relative_to(Path(project_dir).resolve()).as_posix(),
        "canvas": {"width": image.width, "height": image.height},
        "alpha_bounds": {
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
        },
        "assumptions": [
            "front-facing character",
            "character-left maps to screen-right",
            "overlapping polygons are intentional",
            "hands and wide sleeves require human review",
        ],
        "layers": layers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--source-path", required=True)
    args = parser.parse_args()
    try:
        result = propose_upper_body(args.project_dir, args.source_path)
    except (OSError, RigV2AutoDraftError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
