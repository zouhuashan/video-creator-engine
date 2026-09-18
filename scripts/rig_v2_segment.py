#!/usr/bin/env python3
"""Create local Rig V2 transparent layers from human-drawn polygons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from scripts.build_character_rig_v2 import PARENTS, RigV2Error, build_rig_v2
from scripts.godot_rig_readiness import PROFILE_REQUIREMENTS

WORK_RELATIVE = Path("visual-bible/rig-v2-work")


class RigV2SegmentError(ValueError):
    pass


def _project_file(project_dir: Path, relative: str) -> Path:
    rel = Path(str(relative))
    path = (project_dir / rel).resolve()
    if rel.is_absolute() or (path != project_dir and project_dir not in path.parents):
        raise RigV2SegmentError(f"path escapes project: {relative}")
    if not path.is_file():
        raise RigV2SegmentError(f"file not found: {relative}")
    return path


def _point(value: Any, width: int, height: int) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise RigV2SegmentError("polygon points must be [x, y]")
    x, y = float(value[0]), float(value[1])
    if not 0 <= x <= width or not 0 <= y <= height:
        raise RigV2SegmentError(f"point outside canvas: {x}, {y}")
    return x, y


def _pivot(value: Any, width: int, height: int) -> dict[str, float]:
    if not isinstance(value, dict):
        raise RigV2SegmentError("pivot must be an object")
    try:
        x, y = float(value["x"]), float(value["y"])
    except (KeyError, TypeError, ValueError) as error:
        raise RigV2SegmentError("pivot requires numeric x/y") from error
    if not 0 <= x <= width or not 0 <= y <= height:
        raise RigV2SegmentError("pivot outside canvas")
    return {"x": x, "y": y}


def segment_layers(
    project_dir: Path,
    source_path: str,
    character_id: str,
    character_name: str,
    source_asset_id: str,
    rig_id: str,
    profile: str,
    layer_inputs: dict[str, Any],
    *,
    finalize: bool = True,
) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    if profile not in {"GODOT_UPPER_BODY_IK", "GODOT_FULL_BODY_IK"}:
        raise RigV2SegmentError(f"unsupported profile: {profile}")
    source = _project_file(project_dir, source_path)
    image = Image.open(source).convert("RGBA")
    width, height = image.size

    required = PROFILE_REQUIREMENTS[profile]
    missing_inputs = [name for name in required if name not in layer_inputs]
    if missing_inputs:
        raise RigV2SegmentError(f"missing layer inputs: {', '.join(missing_inputs)}")

    out_dir = project_dir / "assets" / "characters" / character_id / "rig-v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    spec_layers: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    source_alpha = image.getchannel("A")
    for index, name in enumerate(required):
        raw = layer_inputs.get(name)
        if not isinstance(raw, dict):
            raise RigV2SegmentError(f"layer {name} must be an object")
        polygon_raw = raw.get("polygon")
        if not isinstance(polygon_raw, list) or len(polygon_raw) < 3:
            raise RigV2SegmentError(f"layer {name} requires at least 3 polygon points")
        polygon = [_point(item, width, height) for item in polygon_raw]
        pivot = _pivot(raw.get("pivot"), width, height)

        polygon_mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(polygon_mask).polygon(polygon, fill=255)
        mask = Image.new("L", image.size, 0)
        mask = Image.composite(source_alpha, mask, polygon_mask)

        bbox = mask.getbbox()
        if bbox is None:
            raise RigV2SegmentError(f"layer {name} polygon contains no visible source pixels")

        layer_image = image.copy()
        layer_image.putalpha(mask)
        layer_path = out_dir / f"{name}.png"
        layer_image.save(layer_path, optimize=True)

        spec_layers.append(
            {
                "name": name,
                "path": layer_path.relative_to(project_dir).as_posix(),
                "parent": PARENTS[name],
                "pivot": pivot,
                "z_index": int(raw.get("z_index", index)),
            }
        )
        summaries.append(
            {
                "name": name,
                "path": layer_path.relative_to(project_dir).as_posix(),
                "polygon_point_count": len(polygon),
                "pivot": pivot,
                "alpha_bounds": {
                    "x": bbox[0],
                    "y": bbox[1],
                    "width": bbox[2] - bbox[0],
                    "height": bbox[3] - bbox[1],
                },
            }
        )

    spec = {
        "schema_version": 1,
        "rig_id": rig_id,
        "character_id": character_id,
        "character_name": character_name or character_id,
        "profile": profile,
        "source_asset_id": source_asset_id,
        "source_path": source.relative_to(project_dir).as_posix(),
        "canvas": {"width": width, "height": height},
        "layers": spec_layers,
    }

    work_dir = project_dir / WORK_RELATIVE
    work_dir.mkdir(parents=True, exist_ok=True)
    spec_path = work_dir / f"{character_id.lower()}-{profile.lower()}.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result: dict[str, Any] = {
        "spec": spec_path.relative_to(project_dir).as_posix(),
        "source": source.relative_to(project_dir).as_posix(),
        "canvas": spec["canvas"],
        "layers": summaries,
        "profile": profile,
        "rig_id": rig_id,
        "finalized": False,
    }
    if finalize:
        built = build_rig_v2(project_dir, spec)
        result["finalized"] = True
        result["rig"] = built["rig"]
        result["manifest"] = built["manifest"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--input", required=True, type=Path, help="JSON segmentation request")
    parser.add_argument("--no-finalize", action="store_true")
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = segment_layers(
            args.project_dir,
            str(payload.get("source_path") or ""),
            str(payload.get("character_id") or ""),
            str(payload.get("character_name") or ""),
            str(payload.get("source_asset_id") or ""),
            str(payload.get("rig_id") or ""),
            str(payload.get("profile") or ""),
            payload.get("layers") if isinstance(payload.get("layers"), dict) else {},
            finalize=not args.no_finalize,
        )
    except (OSError, json.JSONDecodeError, RigV2Error, RigV2SegmentError, RuntimeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
