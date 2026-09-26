#!/usr/bin/env python3
"""Render editable, unbranded screen graphics locally with Pillow and FFmpeg."""

from __future__ import annotations

import math
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from scripts.modern_asset_library import SCREEN_TEMPLATES

SIZE = (540, 960)
FPS = 12
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


class ScreenMGError(ValueError):
    pass


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        current = ""
        for character in paragraph:
            candidate = current + character
            if current and draw.textlength(candidate, font=font) > width:
                lines.append(current)
                current = character
            else:
                current = candidate
        lines.append(current)
    return lines


def _card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], *, fill: str, radius: int = 22) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _base(kind: str, title: str, progress: float) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", SIZE, "#101c2c")
    draw = ImageDraw.Draw(image)
    for y in range(SIZE[1]):
        t = y / SIZE[1]
        draw.line((0, y, SIZE[0], y), fill=(int(18 + 13 * t), int(28 + 18 * t), int(44 + 22 * t)))
    draw.ellipse((-110, -150, 360, 290), fill="#1b3554")
    draw.ellipse((310, 740, 730, 1160), fill="#254366")
    _card(draw, (25, 68, 515, 892), fill="#f5f7fa", radius=35)
    draw.rounded_rectangle((215, 83, 325, 94), radius=6, fill="#b9c4d1")
    draw.text((50, 119), "09:41", font=_font(16), fill="#758598")
    draw.text((50, 158), title[:26], font=_font(29), fill="#14253a")
    draw.line((50, 205, 490, 205), fill="#dce4ed", width=2)
    footer = {"chat": "消息", "incoming_call": "通话", "news": "资讯", "report": "资料", "transfer": "交易"}[kind]
    draw.text((49, 850), f"{footer}  ·  本地制作画面", font=_font(15), fill="#8795a5")
    draw.rounded_rectangle((50, 896, int(50 + 440 * min(1, progress)), 900), radius=2, fill="#50d1c4")
    return image, draw


def _draw_lines(draw: ImageDraw.ImageDraw, lines: list[str], *, start_y: int, progress: float, kind: str) -> None:
    body = _font(24)
    caption = _font(17)
    visible = max(0, min(len(lines), int(progress * (len(lines) + 1))))
    y = start_y
    for index, text in enumerate(lines[:visible]):
        wrapped = _wrap(draw, text, body, 350)
        height = min(180, 38 * len(wrapped) + 34)
        if kind == "chat":
            outgoing = index % 2 == 1
            left = 100 if outgoing else 50
            right = 490 if outgoing else 440
            _card(draw, (left, y, right, y + height), fill="#d8f3ee" if outgoing else "#e7edf3", radius=19)
            color = "#123b3c" if outgoing else "#21354b"
        else:
            _card(draw, (50, y, 490, y + height), fill="#e7edf3", radius=19)
            color = "#21354b"
            draw.text((70, y + 8), f"{index + 1:02d}", font=caption, fill="#4d808c")
        text_y = y + (20 if kind == "chat" else 33)
        for line in wrapped[:4]:
            draw.text((left + 20 if kind == "chat" else 70, text_y), line, font=body, fill=color)
            text_y += 37
        y += height + 18
        if y > 815:
            break


def render_screen_mg(project: Path, *, shot_id: str, kind: str, title: str, lines: list[str], duration_seconds: float = 4.0) -> dict[str, Any]:
    project = Path(project).resolve()
    if kind not in SCREEN_TEMPLATES:
        raise ScreenMGError("unsupported screen template")
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,100}", shot_id):
        raise ScreenMGError("invalid shot_id")
    if not title.strip() or len(title) > 80 or not isinstance(lines, list) or not 1 <= len(lines) <= 6 or any(not isinstance(item, str) or not item.strip() or len(item) > 160 for item in lines):
        raise ScreenMGError("title and 1-6 short text lines are required")
    duration = float(duration_seconds)
    if not math.isfinite(duration) or not 1 <= duration <= 12:
        raise ScreenMGError("duration must be between 1 and 12 seconds")
    output = project / "rendering/screen-mg" / f"{shot_id}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, round(duration * FPS))
    with tempfile.TemporaryDirectory(prefix="screen-mg-") as directory:
        work = Path(directory)
        for index in range(frames):
            progress = (index + 1) / frames
            image, draw = _base(kind, title, progress)
            if kind == "incoming_call":
                draw.ellipse((175, 260, 365, 450), fill="#cedfe8")
                draw.text((226, 319), title[:2], font=_font(56), fill="#21435d")
                draw.text((155, 500), lines[0][:20], font=_font(26), fill="#27445d")
                for x, label, color in ((165, "拒接", "#d76d6d"), (365, "接听", "#55ae9d")):
                    draw.ellipse((x - 48, 650, x + 48, 746), fill=color)
                    draw.text((x - 24, 759), label, font=_font(18), fill="#6b7c8d")
            else:
                _draw_lines(draw, lines, start_y=240, progress=progress, kind=kind)
            image.save(work / f"frame_{index:04d}.png")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(work / "frame_%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            raise ScreenMGError(f"FFmpeg screen MG render failed: {result.stderr[-800:]}")
    return {"status": "READY", "renderer": "local_screen_mg", "shot_id": shot_id, "template": kind, "output": output.relative_to(project).as_posix(), "duration_seconds": frames / FPS, "width": SIZE[0], "height": SIZE[1], "fps": FPS}
