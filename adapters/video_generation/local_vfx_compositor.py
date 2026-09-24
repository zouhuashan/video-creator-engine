"""Deterministic local overlays for Codex-authored, schema-limited VFX recipes."""

from __future__ import annotations

import json
import math
import random
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFilter


ALLOWED_EFFECTS = {"snow", "mist", "petals", "embers", "glow", "ink_wash", "lightning", "ripple"}
ANCHORS = {"top", "center", "lower", "left", "right", "screen"}
DIRECTIONS = {"down", "up", "left", "right", "orbit", "pulse", "still"}


class LocalVFXError(ValueError):
    pass


def validate_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(recipe, dict) or recipe.get("schema_version") != 1:
        raise LocalVFXError("unsupported VFX recipe schema")
    layers = recipe.get("layers")
    if not isinstance(layers, list) or len(layers) > 3:
        raise LocalVFXError("VFX recipe must contain up to three layers")
    cleaned = []
    for layer in layers:
        if not isinstance(layer, dict) or layer.get("type") not in ALLOWED_EFFECTS:
            raise LocalVFXError("VFX recipe contains an unsupported effect")
        try:
            intensity = float(layer["intensity"])
        except (KeyError, TypeError, ValueError) as error:
            raise LocalVFXError("VFX intensity must be numeric") from error
        color = str(layer.get("color") or "")
        if not 0.05 <= intensity <= 0.65 or len(color) != 7 or not color.startswith("#"):
            raise LocalVFXError("VFX layer parameters are outside the supported range")
        try:
            int(color[1:], 16)
        except ValueError as error:
            raise LocalVFXError("VFX color must be a hex color") from error
        direction = str(layer.get("direction") or "")
        anchor = str(layer.get("anchor") or "")
        if direction not in DIRECTIONS or anchor not in ANCHORS:
            raise LocalVFXError("VFX layer direction or anchor is unsupported")
        cleaned.append({"type": layer["type"], "intensity": intensity, "color": color, "direction": direction, "anchor": anchor})
    return {"schema_version": 1, "summary": str(recipe.get("summary") or ""), "layers": cleaned}


def _rgba(color: str, alpha: int) -> tuple[int, int, int, int]:
    return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16), max(0, min(255, alpha)))


def _anchor(name: str, width: int, height: int) -> tuple[int, int]:
    return {
        "top": (width // 2, height // 4),
        "center": (width // 2, height // 2),
        "lower": (width // 2, height * 3 // 4),
        "left": (width // 4, height // 2),
        "right": (width * 3 // 4, height // 2),
        "screen": (width // 2, height // 2),
    }[name]


def _draw_layer(canvas: Image.Image, layer: dict[str, Any], frame: int, frames: int, fps: int, seed: int) -> None:
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas, "RGBA")
    intensity = float(layer["intensity"])
    color = str(layer["color"])
    kind = str(layer["type"])
    direction = str(layer["direction"])
    ax, ay = _anchor(str(layer["anchor"]), width, height)
    progress = frame / max(1, frames - 1)
    if kind in {"snow", "petals", "embers"}:
        # Local overlays need to remain legible after portrait-video scaling and
        # phone compression; intensity controls both density and opacity.
        count = round((60 if kind == "snow" else 36) * intensity)
        rgba = _rgba(color, round((175 if kind != "embers" else 190) * intensity))
        for index in range(count):
            rng = random.Random(seed + index * 997)
            base_x, base_y = rng.randrange(width), rng.randrange(height)
            drift = frame * (0.45 + rng.random() * 0.8)
            if direction == "up":
                y = int((base_y - drift) % height)
                x = int((base_x + math.sin(frame / fps + index) * 10) % width)
            elif direction == "left":
                x, y = int((base_x - drift) % width), base_y
            elif direction == "right":
                x, y = int((base_x + drift) % width), base_y
            else:
                y = int((base_y + drift) % height)
                x = int((base_x + math.sin(frame / fps + index) * 12) % width)
            radius = max(2, round((2 + rng.random() * 5) * intensity))
            if kind == "petals":
                draw.ellipse((x - radius * 2, y - radius, x + radius * 2, y + radius), fill=rgba)
            else:
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rgba)
    elif kind == "mist":
        for index in range(4):
            drift = int((frame * (0.22 + index * 0.06)) % (width // 3 + 1))
            x = (index * width // 3 + drift) % (width + width // 4) - width // 8
            y = height // 3 + (index % 3) * height // 8
            draw.ellipse((x, y, x + width // 2, y + height // 18), fill=_rgba(color, round(90 * intensity)))
        canvas.alpha_composite(canvas.filter(ImageFilter.GaussianBlur(max(10, width // 36))))
    elif kind in {"glow", "ink_wash"}:
        pulse = 0.78 + 0.22 * math.sin(progress * math.tau * (1.0 if direction == "pulse" else 0.25))
        radius = round(min(width, height) * (0.10 + 0.10 * intensity) * pulse)
        alpha = round((105 if kind == "glow" else 65) * intensity)
        draw.ellipse((ax - radius, ay - radius, ax + radius, ay + radius), fill=_rgba(color, alpha))
        canvas.alpha_composite(canvas.filter(ImageFilter.GaussianBlur(max(8, radius // 3))))
        if kind == "ink_wash":
            radius = round(radius * 1.8)
            draw.ellipse((ax - radius, ay - radius // 2, ax + radius, ay + radius // 2), fill=_rgba(color, round(35 * intensity)))
            canvas.alpha_composite(canvas.filter(ImageFilter.GaussianBlur(max(16, radius // 2))))
    elif kind == "lightning":
        if frame % max(2, fps // 2) < max(1, fps // 8):
            rng = random.Random(seed + frame // max(1, fps // 2))
            x = ax + rng.randrange(-width // 5, width // 5)
            points = [(x, 0)]
            for step in range(1, 8):
                x += rng.randrange(-width // 14, width // 14)
                points.append((x, step * height // 8))
            draw.line(points, fill=_rgba(color, round(170 * intensity)), width=max(2, width // 240))
            canvas.alpha_composite(canvas.filter(ImageFilter.GaussianBlur(max(4, width // 120))))
    elif kind == "ripple":
        radius = round((30 + progress * min(width, height) * 0.22) * intensity)
        alpha = round(125 * intensity * max(0.15, 1.0 - progress * 0.65))
        draw.ellipse((ax - radius, ay - radius, ax + radius, ay + radius), outline=_rgba(color, alpha), width=max(2, width // 260))


def _frames(width: int, height: int, count: int, fps: int, recipe: dict[str, Any]):
    recipe = validate_recipe(recipe)
    seed = sum(ord(char) for char in json.dumps(recipe, sort_keys=True, ensure_ascii=False))
    for frame in range(count):
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for index, layer in enumerate(recipe["layers"]):
            _draw_layer(canvas, layer, frame, count, fps, seed + index * 8191)
        yield canvas


def apply_recipe(
    base_video: Path,
    output: Path,
    recipe: dict[str, Any],
    *,
    width: int,
    height: int,
    fps: int,
    duration_seconds: float,
    ffmpeg: str = "ffmpeg",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Path:
    cleaned = validate_recipe(recipe)
    if not cleaned["layers"]:
        raise LocalVFXError("VFX recipe has no effect layers")
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, round(duration_seconds * fps))
    try:
        with tempfile.TemporaryDirectory(prefix="codex-vfx-") as temporary:
            root = Path(temporary)
            frames_dir = root / "frames"
            frames_dir.mkdir()
            for index, frame in enumerate(_frames(width, height, frame_count, fps, cleaned)):
                frame.save(frames_dir / f"frame-{index:06d}.png")
            overlay = root / "overlay.mov"
            overlay_command = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(fps),
                "-i", str(frames_dir / "frame-%06d.png"), "-frames:v", str(frame_count),
                "-c:v", "qtrle", "-pix_fmt", "argb", str(overlay),
            ]
            completed = runner(overlay_command, check=False, capture_output=True, text=True)
            if completed.returncode != 0:
                raise LocalVFXError("FFmpeg could not encode the transparent VFX layer")
            composite = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(base_video), "-i", str(overlay),
                "-filter_complex", "[0:v:0][1:v:0]overlay=shortest=1:format=auto,format=yuv420p[v]",
                "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(output),
            ]
            completed = runner(composite, check=False, capture_output=True, text=True)
            if completed.returncode != 0:
                raise LocalVFXError("FFmpeg could not composite the VFX layer")
    except OSError as error:
        raise LocalVFXError("FFmpeg is unavailable for local VFX composition") from error
    if not output.is_file() or output.stat().st_size == 0:
        raise LocalVFXError("VFX composition produced no video")
    return output


__all__ = ["ALLOWED_EFFECTS", "LocalVFXError", "apply_recipe", "validate_recipe"]
