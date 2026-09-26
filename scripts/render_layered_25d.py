#!/usr/bin/env python3
"""Local background/transparent-character parallax for low-motion shots."""

from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image


class Layered25DError(ValueError):
    pass


def render_layered_25d(project: Path, *, shot_id: str, background: Path, character: Path, duration_seconds: float) -> dict[str, Any]:
    project = Path(project).resolve()
    duration = float(duration_seconds)
    if not math.isfinite(duration) or not 1 <= duration <= 12:
        raise Layered25DError("layered Shot duration must be 1-12 seconds")
    with Image.open(background) as source_background, Image.open(character) as source_character:
        bg = source_background.convert("RGB")
        fg = source_character.convert("RGBA")
    if fg.getextrema()[3][0] == 255:
        raise Layered25DError("character layer must have a transparent background")
    width, height, fps = 540, 960, 12
    bg_scale = max((width * 1.14) / bg.width, (height * 1.14) / bg.height)
    bg = bg.resize((round(bg.width * bg_scale), round(bg.height * bg_scale)), Image.Resampling.LANCZOS)
    fg_scale = min((width * 0.8) / fg.width, (height * 0.72) / fg.height)
    fg = fg.resize((round(fg.width * fg_scale), round(fg.height * fg_scale)), Image.Resampling.LANCZOS)
    output = project / "rendering/modern-shot-previews" / f"{shot_id}-layered.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    frames = round(duration * fps)
    with tempfile.TemporaryDirectory(prefix="layered-25d-") as directory:
        frame_dir = Path(directory)
        for index in range(frames):
            t = index / max(1, frames - 1)
            bx = (bg.width - width) // 2 + round(10 * (t - 0.5))
            by = (bg.height - height) // 2 - round(5 * (t - 0.5))
            frame = bg.crop((bx, by, bx + width, by + height)).convert("RGBA")
            fx = (width - fg.width) // 2 - round(14 * (t - 0.5))
            fy = height - fg.height - 50 + round(3 * math.sin(t * 2 * math.pi))
            frame.alpha_composite(fg, dest=(fx, fy))
            frame.convert("RGB").save(frame_dir / f"frame_{index:04d}.png")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(fps), "-i", str(frame_dir / "frame_%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
        done = subprocess.run(command, capture_output=True, text=True, check=False)
        if done.returncode:
            raise Layered25DError(f"local layered render failed: {done.stderr[-800:]}")
    return {"status": "READY", "renderer": "local_layered_25d", "shot_id": shot_id, "output": output.relative_to(project).as_posix(), "duration_seconds": frames / fps, "width": width, "height": height, "fps": fps, "motion_note": "camera parallax and slight layer sway; no human body action generated"}
