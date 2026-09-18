#!/usr/bin/env python3
"""Render a low-cost layered motion-comic proof from reusable PNG assets."""

from __future__ import annotations

import argparse
import math
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


WIDTH, HEIGHT = 1080, 1920


def _inside(project: Path, value: Path) -> Path:
    path = value.expanduser().resolve()
    if project not in path.parents or not path.is_file():
        raise ValueError(f"asset must be a file inside the project: {value}")
    return path


def _cover(image: Image.Image) -> Image.Image:
    scale = max((WIDTH + 220) / image.width, HEIGHT / image.height)
    size = (math.ceil(image.width * scale), math.ceil(image.height * scale))
    return image.resize(size, Image.Resampling.LANCZOS).convert("RGBA")


def _mist(frame_index: int, fps: int) -> Image.Image:
    small = Image.new("RGBA", (270, 480), (0, 0, 0, 0))
    draw = ImageDraw.Draw(small)
    offset = frame_index / fps * 13
    for index in range(7):
        x = int(((index * 61 + offset) % 390) - 90)
        y = 180 + (index % 3) * 48
        draw.ellipse((x, y, x + 155, y + 44), fill=(235, 241, 236, 18))
    return small.filter(ImageFilter.GaussianBlur(17)).resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)


def _petals(frame_index: int, fps: int) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for index in range(12):
        rng = random.Random(index * 193)
        x = int((rng.randrange(WIDTH) + frame_index * (6 + index % 4) / fps * 24) % (WIDTH + 100) - 50)
        y = int((rng.randrange(HEIGHT) + frame_index * (13 + index % 5) / fps * 24) % (HEIGHT + 140) - 70)
        radius = 3 + index % 4
        draw.ellipse((x - radius * 2, y - radius, x + radius * 2, y + radius), fill=(217, 138, 155, 105))
    return layer.filter(ImageFilter.GaussianBlur(0.5))


def render(project: Path, background_path: Path, character_path: Path, output: Path, seconds: float, fps: int) -> tuple[Path, Path]:
    project = project.expanduser().resolve()
    background_path = _inside(project, background_path)
    character_path = _inside(project, character_path)
    output = output.expanduser().resolve()
    if project not in output.parents:
        raise ValueError("output must be inside the project")
    output.parent.mkdir(parents=True, exist_ok=True)

    background = _cover(Image.open(background_path).convert("RGBA"))
    character_source = Image.open(character_path).convert("RGBA")
    character_height = 1320
    character_width = round(character_source.width * character_height / character_source.height)
    character = character_source.resize((character_width, character_height), Image.Resampling.LANCZOS)
    total_frames = max(1, round(seconds * fps))
    keyframe = output.with_suffix(".png")
    shade = Image.new("RGBA", (WIDTH, 360), (22, 26, 34, 0))
    gradient = Image.new("L", (1, 360))
    gradient.putdata([round(90 * (y / 359) ** 2) for y in range(360)])
    shade.putalpha(gradient.resize(shade.size))

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(fps), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_index in range(total_frames):
            progress = frame_index / max(1, total_frames - 1)
            pan_x = round((background.width - WIDTH) * (0.35 + progress * 0.25))
            frame = background.crop((pan_x, 0, pan_x + WIDTH, HEIGHT))
            frame.alpha_composite(_mist(frame_index, fps))

            breath = 1 + 0.004 * math.sin(frame_index / fps * math.tau / 3.2)
            live_character = character.resize((round(character.width * breath), round(character.height * breath)), Image.Resampling.LANCZOS)
            char_x = round((WIDTH - live_character.width) / 2 + 74)
            char_y = round(510 + 5 * math.sin(frame_index / fps * math.tau / 3.2))
            frame.alpha_composite(live_character, (char_x, char_y))
            frame.alpha_composite(_petals(frame_index, fps))

            frame.alpha_composite(shade, (0, HEIGHT - 360))

            if frame_index == 0:
                frame.save(keyframe)
            process.stdin.write(frame.convert("RGB").tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed to encode the motion test")
    return output, keyframe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--background", required=True, type=Path)
    parser.add_argument("--character", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--fps", type=int, default=24)
    args = parser.parse_args()
    try:
        video, keyframe = render(args.project_dir.resolve(), args.background, args.character, args.output, args.seconds, args.fps)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(f"video={video}\nkeyframe={keyframe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
