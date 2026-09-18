#!/usr/bin/env python3
"""Build aligned transparent character layers for the local motion-comic rig."""

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

from scripts.novel_anime_repository import NovelAnimeRepository


LAYER_RANGES = {
    "full": (0.00, 1.00),
    "head": (0.00, 0.34),
    "torso": (0.24, 0.70),
    "lower": (0.62, 1.00),
}


def _layer_image(source: Image.Image, bbox: tuple[int, int, int, int], start: float, end: float) -> Image.Image:
    """Keep the original canvas and alpha-mask a vertical body band."""
    image = source.copy().convert("RGBA")
    if start == 0.0 and end == 1.0:
        return image
    _, top, _, bottom = bbox
    y0 = top + round((bottom - top) * start)
    y1 = top + round((bottom - top) * end)
    alpha = image.getchannel("A")
    band = Image.new("L", image.size, 0)
    band.paste(alpha.crop((0, y0, image.width, y1)), (0, y0))
    image.putalpha(band)
    return image


def build_rig(
    project_dir: Path,
    source: Path,
    source_asset_id: str,
    character_id: str,
    rig_id: str,
    character_name: str | None = None,
) -> dict[str, Any]:
    project_dir = project_dir.expanduser().resolve()
    source = source.expanduser().resolve()
    if project_dir not in source.parents or not source.is_file():
        raise ValueError("source image must be an existing file inside the project")
    relative_source = source.relative_to(project_dir).as_posix()
    original = Image.open(source).convert("RGBA")
    bbox = original.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("source image must contain non-transparent pixels")

    out_dir = project_dir / "assets" / "characters" / character_id / "rig-v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    repository = NovelAnimeRepository(project_dir)
    asset_prefix = character_id.removeprefix("CHR-")
    display_name = (character_name or character_id).strip()
    layers: list[dict[str, Any]] = []
    for name, (start, end) in LAYER_RANGES.items():
        path = out_dir / f"{name}.png"
        _layer_image(original, bbox, start, end).save(path, optimize=True)
        asset_id = f"AST-RIG-{asset_prefix}-FRONT-{name.upper()}"
        registered = repository.register_asset(
            asset_id,
            "character",
            path,
            metadata={"title": f"{display_name} Rig {name}", "rig_id": rig_id, "layer": name, "source_path": relative_source},
            source_entity_ids=[source_asset_id],
        )
        layers.append({"id": asset_id, "name": name, "path": path.relative_to(project_dir).as_posix(), "asset_id": registered["asset_id"], "version": registered["version"]})

    visual_dir = project_dir / "visual-bible"
    visual_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = visual_dir / "character-rigs.json"
    rig = {
        "id": rig_id,
        "character_id": character_id,
        "character_name": display_name,
        "source_asset_id": source_asset_id,
        "source_path": relative_source,
        "canvas": {"width": original.width, "height": original.height},
        "alpha_bounds": {"x": bbox[0], "y": bbox[1], "width": bbox[2] - bbox[0], "height": bbox[3] - bbox[1]},
        "layers": layers,
        "motion_channels": ["breath", "blink", "mouth", "hair", "sleeve", "ribbon"],
        "human_review": {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None},
    }
    existing: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing_rigs = [item for item in existing.get("rigs", []) if isinstance(item, dict) and item.get("id") != rig_id]
    existing_rigs.append(rig)
    payload = {
        "schema_version": 1,
        "project_id": project_dir.name,
        "revision": int(existing.get("revision", 0)) + 1,
        "rigs": existing_rigs,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"manifest": manifest_path.relative_to(project_dir).as_posix(), "rig": rig, "reused_layers": sum(1 for layer in layers if layer.get("version") == 1)}


def validate_rig(project_dir: Path, rig: dict[str, Any]) -> dict[str, Any]:
    """Validate alignment and local file presence without changing review status."""
    project_dir = project_dir.expanduser().resolve()
    canvas = rig.get("canvas") or {}
    expected = (int(canvas.get("width", 0)), int(canvas.get("height", 0)))
    findings: list[str] = []
    layer_count = 0
    for layer in rig.get("layers", []):
        path = project_dir / str(layer.get("path", ""))
        if not path.is_file():
            findings.append(f"missing layer: {layer.get('name', 'unknown')}")
            continue
        layer_count += 1
        try:
            with Image.open(path) as image:
                if image.size != expected:
                    findings.append(f"layer {layer.get('name', 'unknown')} size {image.size} != {expected}")
                if image.mode != "RGBA":
                    findings.append(f"layer {layer.get('name', 'unknown')} is not RGBA")
                if image.getchannel("A").getbbox() is None:
                    findings.append(f"layer {layer.get('name', 'unknown')} is fully transparent")
        except OSError as error:
            findings.append(f"cannot read layer {layer.get('name', 'unknown')}: {error}")
    return {"valid": not findings, "layer_count": layer_count, "expected_canvas": {"width": expected[0], "height": expected[1]}, "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-asset-id", required=True)
    parser.add_argument("--character-id", default="CHR-JHY-BAIHUA")
    parser.add_argument("--character-name")
    parser.add_argument("--rig-id", default="RIG-CHR-JHY-BAIHUA-FRONT-V1")
    args = parser.parse_args()
    try:
        print(json.dumps(build_rig(args.project_dir, args.source, args.source_asset_id, args.character_id, args.rig_id, args.character_name), ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
