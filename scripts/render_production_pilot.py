#!/usr/bin/env python3
"""Render a short, local-only production acceptance clip.

The clip is deliberately designed as a motion-comic scene: it uses distinct
shot sizes, local 2.5D character motion, procedural rain/fog/light, final TTS,
subtitles and an audio mix. It does not pretend that whole-image zooms are
character animation and it never calls a remote provider.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


WIDTH = 720
HEIGHT = 1280
FPS = 24
DURATION = 9.5
VOICE_START = 2.125
VOICE_END = 5.55
SUBTITLE = ("这盏灯……", "为什么照不出我的影子？")


class ProductionPilotError(RuntimeError):
    pass


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size, index=0)
    raise ProductionPilotError("Chinese subtitle font not found")


def _cover(source: Image.Image, zoom: float = 1.0, anchor: tuple[float, float] = (0.5, 0.5)) -> Image.Image:
    source = source.convert("RGB")
    scale = max(WIDTH / source.width, HEIGHT / source.height) * max(1.0, zoom)
    resized = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
    anchor_x = max(0.0, min(1.0, anchor[0])) * resized.width
    anchor_y = max(0.0, min(1.0, anchor[1])) * resized.height
    left = round(anchor_x - WIDTH / 2)
    top = round(anchor_y - HEIGHT / 2)
    left = max(0, min(resized.width - WIDTH, left))
    top = max(0, min(resized.height - HEIGHT, top))
    return resized.crop((left, top, left + WIDTH, top + HEIGHT))


def _clean_cutout(source: Image.Image) -> Image.Image:
    source = source.convert("RGBA")
    alpha = source.getchannel("A")
    # ImageGen preserves a useful alpha channel but may leave a very faint
    # studio glow. Removing only low-alpha pixels gives the compositor a clean
    # edge without eroding hair strands or embroidery.
    alpha = alpha.point(lambda value: 0 if value < 24 else min(255, round((value - 24) * 255 / 230)))
    source.putalpha(alpha)
    return source


def _character_layers(source: Image.Image) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int], tuple[float, float]]:
    alpha = source.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ProductionPilotError("character cutout has no visible pixels")
    left, top, right, bottom = bbox
    width, height = right - left, bottom - top

    # A soft head/hair mask creates one independent performance group. Motion
    # stays intentionally small so the neck seam remains invisible.
    polygon = [
        (left + width * 0.08, top),
        (left + width * 0.78, top),
        (left + width * 0.78, top + height * 0.27),
        (left + width * 0.66, top + height * 0.36),
        (left + width * 0.36, top + height * 0.35),
        (left + width * 0.08, top + height * 0.24),
    ]
    mask = Image.new("L", source.size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(8))

    head_alpha = Image.composite(alpha, Image.new("L", source.size, 0), mask)
    body_alpha = Image.composite(Image.new("L", source.size, 0), alpha, mask)
    head = source.copy()
    head.putalpha(head_alpha)
    body = source.copy()
    body.putalpha(body_alpha)
    pivot = (left + width * 0.54, top + height * 0.31)
    return body.crop(bbox), head.crop(bbox), bbox, (pivot[0] - left, pivot[1] - top)


def _animated_character(
    body: Image.Image,
    head: Image.Image,
    pivot: tuple[float, float],
    local_time: float,
    *,
    scale: float,
    target_face: tuple[float, float],
    closeup: bool,
) -> Image.Image:
    cycle = math.sin(local_time * math.tau / 3.2)
    lift = _smoothstep((local_time - 0.8) / 2.6)
    angle = (-0.25 * cycle) - (0.65 * lift if closeup else 0.38 * lift)
    head_motion = head.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        center=pivot,
        translate=(round(cycle * 0.8), round(-lift * 2.2)),
    )
    combined = Image.new("RGBA", body.size, (0, 0, 0, 0))
    combined.alpha_composite(body)
    combined.alpha_composite(head_motion)

    breath_scale = 1.0 + 0.0035 * cycle
    scaled = combined.resize(
        (round(combined.width * scale * breath_scale), round(combined.height * scale)),
        Image.Resampling.LANCZOS,
    )
    face_x = combined.width * 0.58 * scale * breath_scale
    face_y = combined.height * 0.145 * scale
    left = round(target_face[0] - face_x)
    top = round(target_face[1] - face_y - cycle * 1.8)
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    layer.alpha_composite(scaled, (left, top))
    return layer


def _glow(size: int = 300) -> Image.Image:
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = glow.load()
    center = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            distance = math.hypot(x - center, y - center) / center
            alpha = round(max(0.0, 1.0 - distance) ** 2.3 * 95)
            pixels[x, y] = (255, 132, 45, alpha)
    return glow.filter(ImageFilter.GaussianBlur(10))


def _fog_texture() -> Image.Image:
    fog = Image.new("RGBA", (1100, 260), (0, 0, 0, 0))
    draw = ImageDraw.Draw(fog)
    for index in range(18):
        x = 35 + index * 59
        y = 115 + int(math.sin(index * 1.7) * 42)
        draw.ellipse((x - 120, y - 65, x + 120, y + 65), fill=(176, 198, 212, 22))
    return fog.filter(ImageFilter.GaussianBlur(34))


def _rain_layer(frame_index: int) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for index in range(86):
        x = (index * 97 + 31) % (WIDTH + 100) - 50
        speed = 17 + (index % 7) * 3
        y = (index * 151 + frame_index * speed) % (HEIGHT + 180) - 90
        length = 16 + (index % 5) * 5
        alpha = 32 + (index % 4) * 10
        draw.line((x, y, x - 5, y + length), fill=(176, 203, 222, alpha), width=1 + index % 2)
    return layer


def _vignette() -> Image.Image:
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((-210, -130, WIDTH + 210, HEIGHT + 180), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(130))
    dark = Image.new("RGBA", (WIDTH, HEIGHT), (2, 6, 15, 155))
    dark.putalpha(Image.eval(mask, lambda value: 155 - round(value * 0.53)))
    return dark


def _subtitle(frame: Image.Image, current_time: float, font: ImageFont.FreeTypeFont) -> None:
    if not VOICE_START <= current_time <= VOICE_END:
        return
    draw = ImageDraw.Draw(frame)
    line = SUBTITLE[0] if current_time < 3.0 else SUBTITLE[1]
    box = draw.textbbox((0, 0), line, font=font, stroke_width=1)
    width = box[2] - box[0]
    height = box[3] - box[1]
    center_y = 735 if current_time >= 3.0 else 1085
    background_box = (
        round((WIDTH - width) / 2 - 22),
        round(center_y - height / 2 - 12),
        round((WIDTH + width) / 2 + 22),
        round(center_y + height / 2 + 12),
    )
    subtitle_backdrop = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    ImageDraw.Draw(subtitle_backdrop).rounded_rectangle(
        background_box,
        radius=14,
        fill=(3, 6, 12, 104),
    )
    frame.alpha_composite(subtitle_backdrop)
    subtitle_layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    ImageDraw.Draw(subtitle_layer).text(
        ((WIDTH - width) / 2, center_y - height / 2),
        line,
        font=font,
        fill=(245, 239, 222, 255),
        stroke_width=4,
        stroke_fill=(5, 8, 14, 230),
    )
    frame.alpha_composite(subtitle_layer)


def _reflection_template(body: Image.Image, head: Image.Image) -> Image.Image:
    character = Image.new("RGBA", body.size, (0, 0, 0, 0))
    character.alpha_composite(body)
    character.alpha_composite(head)
    target_height = 280
    target_width = round(character.width * target_height / character.height * 2.0)
    character = character.resize((target_width, target_height), Image.Resampling.LANCZOS)
    character = ImageOps.flip(character)
    alpha = character.getchannel("A")
    gradient = Image.new("L", character.size, 0)
    pixels = gradient.load()
    for y in range(character.height):
        progress = y / max(1, character.height - 1)
        strength = 0.55 + 0.45 * (1.0 - progress)
        value = round(235 * strength)
        for x in range(character.width):
            pixels[x, y] = value
    alpha = Image.composite(alpha, Image.new("L", character.size, 0), gradient)
    silhouette = Image.new("RGBA", character.size, (0, 2, 8, 255))
    silhouette.putalpha(alpha.filter(ImageFilter.GaussianBlur(1.8)))
    return silhouette


def _ground_light_pool(current_time: float) -> Image.Image:
    """Keep the wet ground bright enough for the shadow beat to read.

    The light belongs to the lantern, so it stays after the supernatural
    shadow has vanished. That persistent contrast is what makes the absence
    understandable on a phone-sized preview.
    """
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    pulse = 1.0
    pool = Image.new("RGBA", (660, 390), (0, 0, 0, 0))
    draw = ImageDraw.Draw(pool)
    draw.ellipse((30, 20, 630, 360), fill=(255, 123, 42, round(82 * pulse)))
    draw.ellipse((120, 70, 560, 325), fill=(255, 187, 91, round(42 * pulse)))
    pool = pool.filter(ImageFilter.GaussianBlur(56))
    layer.alpha_composite(pool, (30, 790))

    # Thin vertical glints suggest a wet floor without adding a second visual
    # effect that competes with the shadow.
    glints = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glint_draw = ImageDraw.Draw(glints)
    for index, x in enumerate((166, 255, 347, 448, 548)):
        width = 12 + (index % 3) * 7
        glint_draw.rounded_rectangle(
            (x - width, 1010 + (index % 2) * 28, x + width, 1240),
            radius=width,
            fill=(255, 181, 96, round((26 + index * 3) * pulse)),
        )
    layer.alpha_composite(glints.filter(ImageFilter.GaussianBlur(18)))
    return layer


def _vanishing_shadow(current_time: float, reflection: Image.Image) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    if current_time < 3.0 or current_time > 5.55:
        return layer
    # Hold long enough for the audience to register the cast shadow, then
    # visibly pull it back into the boots instead of merely cross-fading it.
    fade = 1.0 - _smoothstep((current_time - 3.45) / 0.95)
    if fade <= 0.002:
        return layer

    contraction = 0.18 + 0.82 * fade
    reflected = reflection.resize(
        (reflection.width, max(12, round(reflection.height * contraction))),
        Image.Resampling.LANCZOS,
    )
    reflected.putalpha(
        reflected.getchannel("A").point(lambda value: round(value * fade * 0.94))
    )
    layer.alpha_composite(reflected, (round(360 - reflected.width / 2), 1000))

    contact = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    contact_mask = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(contact_mask).ellipse((205, 982, 520, 1052), fill=round(92 * fade))
    contact.putalpha(contact_mask.filter(ImageFilter.GaussianBlur(18)))
    layer.alpha_composite(contact)

    if 3.55 <= current_time <= 4.25:
        wisps = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        wisp_draw = ImageDraw.Draw(wisps)
        progress = _smoothstep((current_time - 3.55) / 0.70)
        for index in range(9):
            x = 250 + index * 29 + math.sin(index * 1.8) * 18
            y = 930 - progress * (55 + index * 5)
            alpha = round(95 * (1.0 - progress) * (0.55 + (index % 3) * 0.2))
            wisp_draw.ellipse((x - 5, y - 16, x + 5, y + 16), fill=(4, 7, 17, alpha))
        layer.alpha_composite(wisps.filter(ImageFilter.GaussianBlur(5)))
    return layer


def _render_frames(background_path: Path, character_path: Path, output: Path, ffmpeg: str) -> None:
    background = Image.open(background_path).convert("RGB")
    character = _clean_cutout(Image.open(character_path))
    body, head, _, pivot = _character_layers(character)
    reflection = _reflection_template(body, head)
    glow = _glow()
    fog = _fog_texture()
    vignette = _vignette()
    subtitle_font = _font(42)
    total_frames = round(DURATION * FPS)

    command = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", str(FPS),
        "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_index in range(total_frames):
            # Animation is intentionally held on twos, matching limited anime
            # timing while retaining a standard 24 fps delivery container.
            held_index = frame_index - frame_index % 2
            current_time = held_index / FPS

            if current_time < 1.125:
                progress = current_time / 1.125
                frame = _cover(background, 1.0 + progress * 0.035, (0.50, 0.52)).convert("RGBA")
                lantern = (360, 475)
            elif current_time < 2.125:
                local = current_time - 1.125
                frame = _cover(background, 1.10 + local * 0.012, (0.50, 0.53)).convert("RGBA")
                char = _animated_character(
                    body, head, pivot, local,
                    scale=1.22,
                    target_face=(410, 300),
                    closeup=False,
                )
                frame.alpha_composite(char)
                lantern = (350, 435)
            elif current_time < 3.0:
                local = current_time - 2.125
                frame = _cover(background, 2.15 + local * 0.09, (0.50, 0.405)).convert("RGBA")
                lantern = (360, 585)
            elif current_time < 5.55:
                local = current_time - 3.0
                # Keep the camera nearly locked during the vanish so the
                # audience attributes the change to the shadow, not a zoom.
                frame = _cover(background, 1.50, (0.50, 0.82)).convert("RGBA")
                frame.alpha_composite(_ground_light_pool(current_time))
                frame.alpha_composite(_vanishing_shadow(current_time, reflection))
                feet = _animated_character(
                    body, head, pivot, local + 1.4,
                    scale=1.30,
                    target_face=(390, -570),
                    closeup=False,
                )
                frame.alpha_composite(feet)
                lantern = (650, 120)
            else:
                local = current_time - 5.55
                frame = _cover(background, 1.22 + local * 0.018, (0.50, 0.48)).filter(ImageFilter.GaussianBlur(2.2)).convert("RGBA")
                shade = Image.new("RGBA", (WIDTH, HEIGHT), (5, 10, 20, 70))
                frame.alpha_composite(shade)
                char = _animated_character(
                    body, head, pivot, local + 2.8,
                    scale=2.18,
                    target_face=(385, 420),
                    closeup=True,
                )
                frame.alpha_composite(char)
                lantern = (610, 390)

            flicker = 0.88 + 0.12 * math.sin(current_time * 19.0) + 0.05 * math.sin(current_time * 43.0)
            glow_frame = glow.copy()
            glow_frame.putalpha(glow_frame.getchannel("A").point(lambda value: round(value * flicker)))
            frame.alpha_composite(glow_frame, (round(lantern[0] - glow.width / 2), round(lantern[1] - glow.height / 2)))

            fog_x = round(-300 + (current_time * 26) % 360)
            frame.alpha_composite(fog, (fog_x, 865))
            frame.alpha_composite(_rain_layer(held_index))
            frame.alpha_composite(vignette)
            _subtitle(frame, current_time, subtitle_font)
            process.stdin.write(frame.convert("RGB").tobytes())
    finally:
        process.stdin.close()
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    return_code = process.wait()
    if return_code != 0 or not output.is_file():
        raise ProductionPilotError(f"video render failed: {stderr[-2000:]}")


def _mix_audio(silent_video: Path, voice: Path, output: Path, ffmpeg: str) -> None:
    delay = round(VOICE_START * 1000)
    filter_complex = (
        f"[1:a]aresample=48000,loudnorm=I=-18:TP=-2:LRA=7,adelay={delay}|{delay}[voice];"
        "[2:a]highpass=f=650,lowpass=f=9500,volume=0.040[rain];"
        "[3:a]lowpass=f=190,volume=0.022[wind];"
        "[4:a]afade=t=out:st=0.08:d=0.30,adelay=5550|5550,volume=0.045[creak];"
        "[voice][rain][wind][creak]amix=inputs=4:duration=longest:normalize=0,"
        "loudnorm=I=-16:TP=-1:LRA=7,volume=1.5dB,alimiter=limit=0.891[aout]"
    )
    command = [
        ffmpeg, "-y", "-loglevel", "error", "-i", str(silent_video), "-i", str(voice),
        "-f", "lavfi", "-i", f"anoisesrc=color=pink:duration={DURATION}:sample_rate=48000",
        "-f", "lavfi", "-i", f"anoisesrc=color=brown:duration={DURATION}:sample_rate=48000",
        "-f", "lavfi", "-i", "sine=frequency=145:duration=0.38:sample_rate=48000",
        "-filter_complex", filter_complex, "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-ac", "2",
        "-t", str(DURATION), "-movflags", "+faststart", str(output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if completed.returncode != 0 or not output.is_file():
        raise ProductionPilotError(f"audio mix failed: {completed.stderr[-2000:]}")


def render(background: Path, character: Path, voice: Path, output: Path) -> dict[str, object]:
    for path, label in ((background, "background"), (character, "character"), (voice, "voice")):
        if not path.is_file():
            raise ProductionPilotError(f"{label} file not found: {path}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ProductionPilotError("ffmpeg not found")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="video-creator-pilot-") as directory:
        silent = Path(directory) / "silent.mp4"
        _render_frames(background, character, silent, ffmpeg)
        _mix_audio(silent, voice, output, ffmpeg)

    manifest = {
        "schema_version": 1,
        "status": "HUMAN_REVIEW_PENDING",
        "review_status": "PENDING",
        "provider": "codex_local_production_pilot",
        "output": str(output),
        "duration_seconds": DURATION,
        "fps": FPS,
        "width": WIDTH,
        "height": HEIGHT,
        "audio_sample_rate": 48000,
        "local_only": True,
        "billable": False,
        "images_uploaded": False,
        "shots": [
            {"start": 0.0, "end": 1.125, "type": "ESTABLISHING", "motion": ["camera_push", "rain", "fog", "lantern_flicker"]},
            {"start": 1.125, "end": 2.125, "type": "MEDIUM", "motion": ["breathing", "head_lift", "rain", "fog", "lantern_flicker"]},
            {"start": 2.125, "end": 3.0, "type": "INSERT", "motion": ["camera_push", "lantern_flicker", "rain"]},
            {"start": 3.0, "end": 5.55, "type": "DETAIL", "motion": ["shadow_vanish", "locked_camera", "rain"]},
            {"start": 5.55, "end": DURATION, "type": "CLOSEUP", "motion": ["breathing", "head_reaction", "camera_push", "rain"]},
        ],
        "voice": {"start": VOICE_START, "end": VOICE_END, "kind": "INNER_MONOLOGUE", "text": "这盏灯，为什么照不出我的影子。"},
        "sources": {"background": str(background), "character": str(character), "voice": str(voice)},
        "limitations": [
            "首版验证片使用本地2.5D克制表演，不包含走路或打斗",
            "角色脸、声音和镜头仍需人工审看后才能标记为可发布",
        ],
    }
    manifest_path = output.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"output": output, "manifest": manifest_path, **manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--background", required=True, type=Path)
    parser.add_argument("--character", required=True, type=Path)
    parser.add_argument("--voice", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = render(args.background.resolve(), args.character.resolve(), args.voice.resolve(), args.output.resolve())
    except (OSError, ProductionPilotError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    printable = dict(result)
    printable["output"] = str(result["output"])
    printable["manifest"] = str(result["manifest"])
    print(json.dumps({"status": "PASS", "result": printable}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
