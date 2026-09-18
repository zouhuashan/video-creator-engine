#!/usr/bin/env python3
"""Render a local layered character Rig preview without remote video providers."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.render_local_motion_test import HEIGHT, WIDTH, _cover, _mist, _petals


def _inside(project: Path, value: Path) -> Path:
    path = value.expanduser().resolve()
    if project not in path.parents or not path.is_file():
        raise ValueError(f"asset must be a file inside the project: {value}")
    return path


def _mouth_overlay(image: Image.Image, mouth: str, brow: int = 0) -> Image.Image:
    """Draw a restrained procedural mouth cue on the aligned head layer."""
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = round(image.width * 0.50), round(image.height * 0.265)
    width = {"rest": 12, "smile": 18, "o": 13, "wide": 24}.get(mouth, 12)
    height = {"rest": 2, "smile": 5, "o": 11, "wide": 15}.get(mouth, 2)
    color = (115, 47, 58, 185)
    if mouth == "smile":
        draw.arc((cx - width, cy - height, cx + width, cy + height * 2), 15, 165, fill=color, width=3)
    elif mouth == "rest":
        draw.line((cx - width, cy, cx + width, cy), fill=color, width=3)
    else:
        draw.ellipse((cx - width, cy - height, cx + width, cy + height), outline=color, width=3)
    if brow:
        brow_color = (77, 53, 48, 120)
        brow_y = cy - 88 - brow * 2
        draw.arc((cx - 80, brow_y - 12, cx - 25, brow_y + 12), 200, 335, fill=brow_color, width=3)
        draw.arc((cx + 25, brow_y - 12, cx + 80, brow_y + 12), 205, 340, fill=brow_color, width=3)
    return overlay


def render(project: Path, background: Path, layers: list[Path], output: Path, seconds: float = 4.0, fps: int = 24, expression: str = "neutral", mouth_cues: list[dict[str, object]] | None = None, particle_effect: str = "petals") -> tuple[Path, Path]:
    project = project.expanduser().resolve()
    background = _inside(project, background)
    layer_paths = [_inside(project, item) for item in layers]
    output = output.expanduser().resolve()
    if project not in output.parents:
        raise ValueError("output must be inside the project")
    output.parent.mkdir(parents=True, exist_ok=True)
    backdrop = _cover(Image.open(background).convert("RGBA"))
    sources = [Image.open(item).convert("RGBA") for item in layer_paths]
    mouth_cues = mouth_cues or []
    target_height = 1320
    resized = [image.resize((round(image.width * target_height / image.height), target_height), Image.Resampling.LANCZOS) for image in sources]
    total_frames = max(1, round(seconds * fps))
    keyframe = output.with_suffix(".png")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_index in range(total_frames):
            progress = frame_index / max(1, total_frames - 1)
            frame = backdrop.crop((round((backdrop.width - WIDTH) * (0.35 + progress * 0.25)), 0, round((backdrop.width - WIDTH) * (0.35 + progress * 0.25)) + WIDTH, HEIGHT))
            frame.alpha_composite(_mist(frame_index, fps))
            current_mouth = "rest"
            if mouth_cues:
                cue = next((item for item in mouth_cues if float(item.get("start", 0)) <= frame_index / fps < float(item.get("end", seconds))), None)
                if cue:
                    current_mouth = str(cue.get("mouth") or "rest")
            expression_brow = {"neutral": 0, "soft_smile": -1, "concerned": 2, "surprised": -2}.get(expression, 0)
            for index, source in enumerate(resized):
                if index == 0:
                    source = Image.alpha_composite(source, _mouth_overlay(source, current_mouth if mouth_cues else {"neutral": "rest", "soft_smile": "smile", "concerned": "o", "surprised": "wide"}.get(expression, "rest"), expression_brow))
                scale = 1 + (0.004 if index == 1 else 0.002) * math.sin(frame_index / fps * math.tau / 3.2)
                live = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
                x = round((WIDTH - live.width) / 2 + 74)
                y = round(510 + (5 if index == 0 else 2) * math.sin(frame_index / fps * math.tau / 3.2 + index * 0.35))
                frame.alpha_composite(live, (x, y))
            if particle_effect == "petals":
                frame.alpha_composite(_petals(frame_index, fps))
            if frame_index == 0:
                frame.save(keyframe)
            process.stdin.write(frame.convert("RGB").tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed to encode the Rig preview")
    return output, keyframe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--background", required=True, type=Path)
    parser.add_argument("--layer", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--expression", default="neutral")
    parser.add_argument("--mouth-cues", type=Path)
    parser.add_argument("--particle-effect", choices=("petals", "none"), default="petals")
    args = parser.parse_args()
    try:
        cues = json.loads(args.mouth_cues.read_text(encoding="utf-8")) if args.mouth_cues else []
        video, keyframe = render(args.project_dir, args.background, args.layer, args.output, args.seconds, args.fps, args.expression, cues, args.particle_effect)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(f"video={video}\nkeyframe={keyframe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
