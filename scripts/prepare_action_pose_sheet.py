#!/usr/bin/env python3
"""Split a transparent 2x2 ImageGen action sheet into reusable pose assets."""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

from PIL import Image


POSE_NAMES = ("pose-01", "pose-02", "pose-03", "pose-04")


def _largest_alpha_component(alpha: Image.Image) -> Image.Image:
    """Remove pose fragments that spill across a sprite-sheet cell edge."""
    width, height = alpha.size
    source = alpha.tobytes()
    visible = bytearray(1 if value >= 18 else 0 for value in source)
    seen = bytearray(width * height)
    largest: list[int] = []
    for start, enabled in enumerate(visible):
        if not enabled or seen[start]:
            continue
        queue: deque[int] = deque((start,))
        seen[start] = 1
        component: list[int] = []
        while queue:
            index = queue.popleft()
            component.append(index)
            x = index % width
            for neighbor in (index - width, index + width, index - 1, index + 1):
                if neighbor < 0 or neighbor >= len(visible) or seen[neighbor] or not visible[neighbor]:
                    continue
                if neighbor == index - 1 and x == 0:
                    continue
                if neighbor == index + 1 and x == width - 1:
                    continue
                seen[neighbor] = 1
                queue.append(neighbor)
        if len(component) > len(largest):
            largest = component

    cleaned = bytearray(len(source))
    for index in largest:
        cleaned[index] = source[index]
    return Image.frombytes("L", (width, height), bytes(cleaned))


def split_sheet(source: Path, output_dir: Path, *, prefix: str) -> dict[str, object]:
    image = Image.open(source).convert("RGBA")
    if image.width % 2 or image.height % 2:
        raise ValueError("pose sheet width and height must both be divisible by 2")

    output_dir.mkdir(parents=True, exist_ok=True)
    cell_width = image.width // 2
    cell_height = image.height // 2
    poses: list[dict[str, object]] = []
    for index, pose_name in enumerate(POSE_NAMES):
        column = index % 2
        row = index // 2
        cell = image.crop(
            (
                column * cell_width,
                row * cell_height,
                (column + 1) * cell_width,
                (row + 1) * cell_height,
            )
        )
        alpha = _largest_alpha_component(cell.getchannel("A"))
        alpha = alpha.point(lambda value: 0 if value < 18 else min(255, round((value - 18) * 255 / 236)))
        cell.putalpha(alpha)
        bbox = alpha.getbbox()
        if bbox is None:
            raise ValueError(f"{pose_name} contains no visible character pixels")
        output_path = output_dir / f"{prefix}-{pose_name}.png"
        cell.save(output_path)
        poses.append(
            {
                "id": f"{prefix}-{pose_name}",
                "path": output_path.name,
                "bbox": list(bbox),
                "foot_anchor": [round((bbox[0] + bbox[2]) / 2), bbox[3]],
                "cell": [column, row],
            }
        )

    manifest = {
        "schema_version": 1,
        "source": str(source),
        "layout": {"columns": 2, "rows": 2, "cell_width": cell_width, "cell_height": cell_height},
        "poses": poses,
        "local_only": True,
        "billable_video": False,
        "review_status": "PENDING",
    }
    manifest_path = output_dir / f"{prefix}-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"manifest": str(manifest_path), "poses": poses}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()
    result = split_sheet(args.source.resolve(), args.output_dir.resolve(), prefix=args.prefix)
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
