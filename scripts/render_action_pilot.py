#!/usr/bin/env python3
"""Render a local limited-animation pilot from consistent action pose assets."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from scripts.render_production_pilot import (
    HEIGHT,
    WIDTH,
    _cover,
    _fog_texture,
    _font,
    _glow,
    _rain_layer,
    _smoothstep,
    _vignette,
)


FPS = 24
DURATION = 8.75
VOICE_START = 2.70
VOICE_END = 6.20


class ActionPilotError(RuntimeError):
    pass


def _load_pose(path: Path) -> Image.Image:
    pose = Image.open(path).convert("RGBA")
    bbox = pose.getchannel("A").getbbox()
    if bbox is None:
        raise ActionPilotError(f"pose has no visible pixels: {path}")
    return pose.crop(bbox)


def _opacity(image: Image.Image, amount: float) -> Image.Image:
    result = image.copy()
    result.putalpha(result.getchannel("A").point(lambda value: round(value * amount)))
    return result


def _pose_layer(
    pose: Image.Image,
    *,
    height: int,
    anchor: tuple[float, float],
    scale: float = 1.0,
    rotate: float = 0.0,
    offset: tuple[float, float] = (0.0, 0.0),
) -> Image.Image:
    target_height = max(8, round(height * scale))
    target_width = max(8, round(pose.width * target_height / pose.height))
    sprite = pose.resize((target_width, target_height), Image.Resampling.LANCZOS)
    if abs(rotate) > 0.01:
        sprite = sprite.rotate(rotate, resample=Image.Resampling.BICUBIC, expand=True)
    x = round(anchor[0] - sprite.width / 2 + offset[0])
    y = round(anchor[1] - sprite.height + offset[1])
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    layer.alpha_composite(sprite, (x, y))
    return layer


def _trail_layer(pose: Image.Image, *, height: int, anchor: tuple[float, float], strength: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    for index, distance in enumerate((34, 20, 9)):
        sprite = _pose_layer(
            pose,
            height=height,
            anchor=anchor,
            offset=(-distance, 3 + index),
        ).filter(ImageFilter.GaussianBlur(3.0 - index * 0.7))
        layer.alpha_composite(_opacity(sprite, strength * (0.18 + index * 0.09)))
    return layer


def _speed_lines(frame_index: int, intensity: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    if intensity <= 0.01:
        return layer
    draw = ImageDraw.Draw(layer)
    for index in range(18):
        x = 390 + (index * 43 + frame_index * 7) % 310
        y = 140 + (index * 67) % 620
        length = 30 + (index % 5) * 17
        draw.line(
            (x, y + length, x + 14, y),
            fill=(238, 186, 122, round(92 * intensity)),
            width=1 + index % 2,
        )
    return layer.filter(ImageFilter.GaussianBlur(0.6))


def _lantern_light(position: tuple[int, int], glow: Image.Image, current_time: float) -> Image.Image:
    pulse = 0.90 + 0.10 * math.sin(current_time * 20.0) + 0.035 * math.sin(current_time * 47.0)
    result = glow.copy()
    result.putalpha(result.getchannel("A").point(lambda value: round(value * pulse)))
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    layer.alpha_composite(result, (round(position[0] - result.width / 2), round(position[1] - result.height / 2)))
    return layer


def _shadow_from_pose(pose: Image.Image, current_time: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    # Keep the disappearance moving through the entire insert.  Ending the
    # fade early leaves a visibly static patch before the recoil cut.
    fade = 1.0 - _smoothstep((current_time - 3.35) / 1.20)
    if fade <= 0.002:
        return layer
    silhouette = pose.resize((255, 360), Image.Resampling.LANCZOS)
    silhouette = silhouette.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    alpha = silhouette.getchannel("A")
    alpha = alpha.point(lambda value: round(value * fade * 0.80))
    shadow = Image.new("RGBA", silhouette.size, (0, 3, 12, 255))
    shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(2.0)))
    contraction = 0.20 + 0.80 * fade
    shadow = shadow.resize((shadow.width, max(14, round(shadow.height * contraction))), Image.Resampling.LANCZOS)
    drift = round((1.0 - fade) * 34)
    layer.alpha_composite(shadow, (round(WIDTH / 2 - shadow.width / 2 + drift), 930))
    return layer


def _shadow_wisps(current_time: float) -> Image.Image:
    """Draw visible moving residue so the shadow insert never becomes a hold."""
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    local = max(0.0, current_time - 3.35)
    for index in range(7):
        phase = (local * 0.92 + index / 7.0) % 1.0
        x = 250 + index * 36 + math.sin(local * 5.0 + index) * 18
        y = 1120 - phase * 235
        alpha = round(115 * math.sin(math.pi * phase) ** 1.5)
        draw.ellipse(
            (x - 8 - phase * 9, y - 28, x + 8 + phase * 9, y + 28),
            fill=(7, 10, 20, alpha),
        )
    return layer.filter(ImageFilter.GaussianBlur(8.0))


def _ground_light() -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse((55, 850, 675, 1265), fill=(255, 151, 67, 75))
    return layer.filter(ImageFilter.GaussianBlur(58))


def _ground_ripples(current_time: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for index in range(3):
        progress = (current_time * 0.72 + index / 3.0) % 1.0
        radius_x = 34 + progress * 210
        radius_y = 10 + progress * 58
        alpha = round(74 * (1.0 - progress) ** 1.4)
        draw.ellipse(
            (360 - radius_x, 1125 - radius_y, 360 + radius_x, 1125 + radius_y),
            outline=(255, 186, 108, alpha),
            width=2,
        )
    return layer.filter(ImageFilter.GaussianBlur(1.2))


def _subtitle(frame: Image.Image, current_time: float) -> None:
    if not VOICE_START <= current_time <= VOICE_END:
        return
    line = "这盏灯……" if current_time < 3.35 else "为什么照不出我的影子？"
    center_y = 720 if 3.35 <= current_time < 4.55 else 1080
    font = _font(42)
    probe = ImageDraw.Draw(frame)
    box = probe.textbbox((0, 0), line, font=font, stroke_width=1)
    width = box[2] - box[0]
    height = box[3] - box[1]
    backdrop = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    ImageDraw.Draw(backdrop).rounded_rectangle(
        (
            round((WIDTH - width) / 2 - 20),
            round(center_y - height / 2 - 10),
            round((WIDTH + width) / 2 + 20),
            round(center_y + height / 2 + 10),
        ),
        radius=13,
        fill=(3, 6, 12, 96),
    )
    frame.alpha_composite(backdrop)
    text = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    ImageDraw.Draw(text).text(
        ((WIDTH - width) / 2, center_y - height / 2),
        line,
        font=font,
        fill=(248, 241, 224, 255),
        stroke_width=4,
        stroke_fill=(4, 7, 12, 225),
    )
    frame.alpha_composite(text)


def _render_frames(background_path: Path, pose_dir: Path, output: Path, ffmpeg: str) -> None:
    background = Image.open(background_path).convert("RGB")
    reach = [_load_pose(pose_dir / f"reach-pose-0{index}.png") for index in range(1, 5)]
    recoil = _load_pose(pose_dir / "action-pose-03.png")
    alert = _load_pose(pose_dir / "action-pose-04.png")
    glow = _glow(340)
    fog = _fog_texture()
    vignette = _vignette()
    total_frames = round(DURATION * FPS)

    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{WIDTH}x{HEIGHT}",
        "-framerate",
        str(FPS),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_index in range(total_frames):
            held_index = frame_index - frame_index % 2
            current_time = held_index / FPS
            lantern = (360, 470)
            trail: Image.Image | None = None
            speed_intensity = 0.0

            if current_time < 0.80:
                progress = current_time / 0.80
                frame = _cover(background, 1.0 + 0.025 * progress, (0.50, 0.52)).convert("RGBA")
            elif current_time < 1.40:
                local = current_time - 0.80
                frame = _cover(background, 1.08, (0.50, 0.54)).convert("RGBA")
                breath = 1.0 + 0.003 * math.sin(local * math.tau / 1.8)
                frame.alpha_composite(_pose_layer(reach[0], height=1050, anchor=(370, 1215), scale=breath))
            elif current_time < 2.80:
                local = current_time - 1.40
                step_duration = 0.35
                pose_index = min(3, int(local / step_duration))
                step_local = local - pose_index * step_duration
                frame = _cover(background, 1.08, (0.50, 0.54)).convert("RGBA")
                anchor = (370 + pose_index * 2, 1215)
                if step_local < 0.105 and pose_index > 0:
                    burst = 1.0 - step_local / 0.105
                    trail = _trail_layer(reach[pose_index], height=1050, anchor=anchor, strength=burst)
                    speed_intensity = burst
                if trail is not None:
                    frame.alpha_composite(trail)
                frame.alpha_composite(_pose_layer(reach[pose_index], height=1050, anchor=anchor))
                frame.alpha_composite(_speed_lines(held_index, speed_intensity))
            elif current_time < 3.35:
                local = current_time - 2.80
                frame = _cover(background, 2.10 + local * 0.16, (0.50, 0.405)).convert("RGBA")
                lantern = (360, 585)
            elif current_time < 4.55:
                local = current_time - 3.35
                frame = _cover(background, 1.50, (0.50, 0.82)).convert("RGBA")
                frame.alpha_composite(_ground_light())
                frame.alpha_composite(_ground_ripples(current_time))
                frame.alpha_composite(_shadow_from_pose(reach[0], current_time))
                frame.alpha_composite(_shadow_wisps(current_time))
                feet = _pose_layer(reach[0], height=1080, anchor=(370, 1170), offset=(0, -470))
                frame.alpha_composite(feet)
                lantern = (650, 120)
            elif current_time < 5.40:
                local = current_time - 4.55
                impact = max(0.0, 1.0 - local / 0.32)
                settle = math.sin(local * 13.0) * math.exp(-2.1 * local)
                shake_x = math.sin(local * 76.0) * 10.0 * impact + settle * 4.0
                shake_y = math.cos(local * 63.0) * 6.0 * impact + settle * 2.0
                frame = _cover(background, 1.09 + local * 0.006, (0.50, 0.54)).convert("RGBA")
                if local < 0.18:
                    frame.alpha_composite(_trail_layer(recoil, height=1040, anchor=(375, 1215), strength=1.0 - local / 0.18))
                frame.alpha_composite(
                    _pose_layer(
                        recoil,
                        height=1040,
                        anchor=(375, 1215),
                        rotate=-0.5 * impact + 0.85 * settle,
                        offset=(shake_x, shake_y),
                    )
                )
                flash = round(72 * max(0.0, 1.0 - local / 0.20))
                if flash:
                    frame.alpha_composite(Image.new("RGBA", (WIDTH, HEIGHT), (255, 187, 105, flash)))
            elif current_time < 6.25:
                local = current_time - 5.40
                frame = _cover(background, 1.10, (0.50, 0.53)).convert("RGBA")
                settle = math.sin(local * 10.0) * max(0.0, 1.0 - local / 0.85)
                frame.alpha_composite(_pose_layer(alert, height=1050, anchor=(380, 1215), rotate=0.65 * settle))
            else:
                local = current_time - 6.25
                progress = local / (DURATION - 6.25)
                frame = _cover(background, 1.20 + progress * 0.025, (0.50, 0.48)).filter(ImageFilter.GaussianBlur(2.0)).convert("RGBA")
                frame.alpha_composite(Image.new("RGBA", (WIDTH, HEIGHT), (5, 10, 20, 62)))
                breathe = 1.0 + 0.003 * math.sin(local * math.tau / 2.4)
                frame.alpha_composite(_pose_layer(alert, height=1850, anchor=(370, 1930), scale=breathe))
                lantern = (610, 390)

            frame.alpha_composite(_lantern_light(lantern, glow, current_time))
            frame.alpha_composite(fog, (round(-330 + (current_time * 29) % 360), 880))
            frame.alpha_composite(_rain_layer(held_index))
            frame.alpha_composite(vignette)
            _subtitle(frame, current_time)
            process.stdin.write(frame.convert("RGB").tobytes())
    finally:
        process.stdin.close()
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    return_code = process.wait()
    if return_code != 0 or not output.is_file():
        raise ActionPilotError(f"video render failed: {stderr[-2000:]}")


def _mix_audio(silent_video: Path, voice: Path, output: Path, ffmpeg: str) -> None:
    delay = round(VOICE_START * 1000)
    filter_complex = (
        f"[1:a]aresample=48000,loudnorm=I=-18:TP=-2:LRA=7,adelay={delay}|{delay}[voice];"
        "[2:a]highpass=f=650,lowpass=f=9500,volume=0.036[rain];"
        "[3:a]lowpass=f=190,volume=0.020[wind];"
        "[4:a]afade=t=out:st=0.12:d=0.42,adelay=4550|4550,volume=0.080[impact];"
        "[voice][rain][wind][impact]amix=inputs=4:duration=longest:normalize=0,"
        "loudnorm=I=-16:TP=-1:LRA=7,volume=1.5dB,alimiter=limit=0.891[aout]"
    )
    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(silent_video),
        "-i",
        str(voice),
        "-f",
        "lavfi",
        "-i",
        f"anoisesrc=color=pink:duration={DURATION}:sample_rate=48000",
        "-f",
        "lavfi",
        "-i",
        f"anoisesrc=color=brown:duration={DURATION}:sample_rate=48000",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=92:duration=0.55:sample_rate=48000",
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v:0",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-t",
        str(DURATION),
        "-movflags",
        "+faststart",
        str(output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if completed.returncode != 0 or not output.is_file():
        raise ActionPilotError(f"audio mix failed: {completed.stderr[-2000:]}")


def render(background: Path, pose_dir: Path, voice: Path, output: Path) -> dict[str, object]:
    if not background.is_file():
        raise ActionPilotError(f"background file not found: {background}")
    if not voice.is_file():
        raise ActionPilotError(f"voice file not found: {voice}")
    required = [pose_dir / f"reach-pose-0{index}.png" for index in range(1, 5)]
    required.extend((pose_dir / "action-pose-03.png", pose_dir / "action-pose-04.png"))
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ActionPilotError(f"missing action poses: {missing}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ActionPilotError("ffmpeg not found")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="video-creator-action-pilot-") as directory:
        silent = Path(directory) / "silent.mp4"
        _render_frames(background, pose_dir, silent, ffmpeg)
        _mix_audio(silent, voice, output, ffmpeg)

    manifest = {
        "schema_version": 1,
        "status": "HUMAN_REVIEW_PENDING",
        "review_status": "PENDING",
        "provider": "codex_local_limited_animation",
        "output": str(output),
        "duration_seconds": DURATION,
        "fps": FPS,
        "width": WIDTH,
        "height": HEIGHT,
        "local_only": True,
        "billable_video": False,
        "images_uploaded_to_video_provider": False,
        "pose_animation": {
            "reach_keyframes": 4,
            "reaction_keyframes": 2,
            "method": "held_pose_animation_with_local_motion_trails",
            "whole_image_zoom_is_primary_motion": False,
        },
        "shots": [
            {"start": 0.0, "end": 0.8, "type": "ESTABLISHING"},
            {"start": 0.8, "end": 1.4, "type": "NEUTRAL_HOLD"},
            {"start": 1.4, "end": 2.8, "type": "FOUR_POSE_ARM_RAISE"},
            {"start": 2.8, "end": 3.35, "type": "LANTERN_INSERT"},
            {"start": 3.35, "end": 4.55, "type": "SHADOW_VANISH"},
            {"start": 4.55, "end": 5.4, "type": "RECOIL_ACTION"},
            {"start": 5.4, "end": 6.25, "type": "ALERT_SETTLE"},
            {"start": 6.25, "end": DURATION, "type": "REACTION_CLOSEUP"},
        ],
        "voice": {"start": VOICE_START, "end": VOICE_END, "text": "这盏灯，为什么照不出我的影子。"},
        "sources": {"background": str(background), "pose_dir": str(pose_dir), "voice": str(voice)},
        "limitations": [
            "本片使用六张一致角色动作关键帧做有限动画，不等同于逐帧全动画",
            "人物动作、声音与角色一致性仍需人工审看",
        ],
    }
    manifest_path = output.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"output": str(output), "manifest": str(manifest_path), **manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--background", required=True, type=Path)
    parser.add_argument("--pose-dir", required=True, type=Path)
    parser.add_argument("--voice", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = render(args.background.resolve(), args.pose_dir.resolve(), args.voice.resolve(), args.output.resolve())
    except (OSError, ActionPilotError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
