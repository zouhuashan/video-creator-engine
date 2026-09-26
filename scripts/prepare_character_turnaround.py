#!/usr/bin/env python3
"""Split a Codex-generated 2x2 transparent turnaround into reusable view cards."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image


VIEWS = {
    "front": (0, 0),
    "three_quarter": (1, 0),
    "profile": (0, 1),
    "back": (1, 1),
}


def split_turnaround(source: Path, output_dir: Path, *, character_id: str, reference: str = "") -> dict[str, Any]:
    source = Path(source).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if not source.is_file():
        raise ValueError("turnaround image does not exist")
    image = Image.open(source).convert("RGBA")
    width, height = image.size
    if width < 512 or height < 512 or width % 2 or height % 2:
        raise ValueError("turnaround sheet must be an even-sized 2x2 image")
    if image.getpixel((0, 0))[3] != 0:
        raise ValueError("turnaround sheet background must have transparent alpha")
    half_width, half_height = width // 2, height // 2
    output_dir.mkdir(parents=True, exist_ok=True)
    portable_source = output_dir / "turnaround-sheet.png"
    if source.resolve() != portable_source.resolve():
        shutil.copy2(source, portable_source)
    cards: dict[str, dict[str, Any]] = {}
    for view, (column, row) in VIEWS.items():
        left, top = column * half_width, row * half_height
        card = image.crop((left, top, left + half_width, top + half_height))
        alpha = card.getchannel("A")
        bbox = alpha.getbbox()
        if bbox is None:
            raise ValueError(f"{view} quadrant contains no visible character")
        path = output_dir / f"{view}.png"
        card.save(path, optimize=True)
        cards[view] = {
            "path": path.name,
            "width": card.width,
            "height": card.height,
            "alpha_bbox": list(bbox),
        }
    manifest = {
        "schema_version": 1,
        "character_id": str(character_id).strip(),
        "status": "DRAFT",
        "review_status": "PENDING",
        "source": portable_source.name,
        "reference": str(reference),
        "layout": "2x2",
        "views": cards,
        "animation_binding": {
            "source": "BLENDER_ACTOR_ROOT",
            "mode": "CAMERA_FACING_CARD",
            "rotation_switching": "front/three_quarter/profile/back by camera-relative yaw",
            "requires_human_review": True,
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--reference", default="")
    args = parser.parse_args()
    result = split_turnaround(args.input, args.output_dir, character_id=args.character_id, reference=args.reference)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
