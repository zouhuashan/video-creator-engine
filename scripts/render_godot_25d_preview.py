#!/usr/bin/env python3
"""Render a short local Godot 2.5D character preview from a Rig V2 manifest."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GODOT_PROJECT = ROOT / "support" / "godot" / "25d-preview"
RIG_V2_MANIFEST = Path("visual-bible/character-rigs-v2.json")

DEPTH = {
    "torso": 0.00,
    "head": 0.10,
    "upper_arm_l": 0.16,
    "forearm_l": 0.20,
    "hand_l": 0.24,
    "upper_arm_r": 0.08,
    "forearm_r": 0.11,
    "hand_r": 0.14,
}
SECONDARY = {
    "torso": 0.02,
    "head": 0.16,
    "upper_arm_l": 0.14,
    "forearm_l": 0.11,
    "hand_l": 0.08,
    "upper_arm_r": 0.14,
    "forearm_r": 0.11,
    "hand_r": 0.08,
}

FRAMING_PROFILES = {
    "UPPER_BODY": {"zoom": 1.34, "bottom_overscan_px": 20.0},
    "CLOSEUP": {"zoom": 1.52, "bottom_overscan_px": 20.0},
}


class Godot25DPreviewError(RuntimeError):
    pass


def _godot_binary() -> str:
    for candidate in (
        "/opt/homebrew/bin/godot",
        "/Applications/Godot.app/Contents/MacOS/Godot",
        shutil.which("godot"),
    ):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise Godot25DPreviewError("Godot binary not found")


def _ffmpeg_binary() -> str:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise Godot25DPreviewError("ffmpeg not found")
    return binary


def _load_rig(project_dir: Path, character_id: str) -> dict[str, Any]:
    path = project_dir / RIG_V2_MANIFEST
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Godot25DPreviewError(f"cannot read Rig V2 manifest: {error}") from error
    for rig in payload.get("rigs", []):
        if isinstance(rig, dict) and rig.get("character_id") == character_id:
            return rig
    raise Godot25DPreviewError(f"Rig V2 not found for {character_id}")


def _discover_background(project_dir: Path) -> Path | None:
    bindings_dir = project_dir / "graybox" / "reference-bindings"
    for binding_path in sorted(bindings_dir.glob("*.json")):
        try:
            payload = json.loads(binding_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        reference = payload.get("scene_reference")
        if not isinstance(reference, dict):
            continue
        relative = str(reference.get("path") or "")
        if not relative:
            continue
        bound = (project_dir / relative).resolve()
        enhanced = bound.with_name(f"{bound.stem}-codex-v1.png")
        if enhanced.is_file():
            return enhanced
        if bound.is_file():
            return bound

    scene_dir = project_dir / "graybox" / "references" / "scenes"
    candidates = [
        path for path in scene_dir.glob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    return max(candidates, key=lambda path: path.stat().st_size) if candidates else None


def _resolve_background(project_dir: Path, background_path: Path | None) -> Path | None:
    if background_path is None:
        return _discover_background(project_dir)
    path = Path(background_path).expanduser()
    if not path.is_absolute():
        path = project_dir / path
    path = path.resolve()
    if not path.is_file():
        raise Godot25DPreviewError(f"background image not found: {path}")
    return path


def _alpha_bounds(path: Path) -> tuple[int, int, int, int] | None:
    try:
        with Image.open(path) as image:
            if "A" not in image.getbands():
                return (0, 0, image.width, image.height)
            return image.getchannel("A").getbbox()
    except OSError as error:
        raise Godot25DPreviewError(f"cannot inspect Rig V2 layer: {path}") from error


def build_preview_config(
    project_dir: Path,
    character_id: str,
    duration_seconds: float = 4.0,
    background_path: Path | None = None,
    framing: str = "UPPER_BODY",
) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    rig = _load_rig(project_dir, character_id)
    if str(rig.get("profile")) not in {"GODOT_UPPER_BODY_IK", "GODOT_FULL_BODY_IK"}:
        raise Godot25DPreviewError("Rig V2 is not IK-ready profile")

    canvas = rig.get("canvas") if isinstance(rig.get("canvas"), dict) else {}
    width, height = int(canvas.get("width", 0)), int(canvas.get("height", 0))
    if width <= 0 or height <= 0:
        raise Godot25DPreviewError("Rig V2 canvas is invalid")

    framing = str(framing).strip().upper()
    if framing not in FRAMING_PROFILES:
        raise Godot25DPreviewError(f"unsupported framing: {framing}")

    layers: list[dict[str, Any]] = []
    names = set()
    content_bounds: list[int] | None = None
    body_bottom: int | None = None
    for layer in rig.get("layers", []):
        if not isinstance(layer, dict):
            continue
        name = str(layer.get("name") or "")
        path = (project_dir / str(layer.get("path") or "")).resolve()
        if not path.is_file():
            raise Godot25DPreviewError(f"missing Rig V2 layer: {name}")
        pivot = layer.get("pivot")
        if not isinstance(pivot, dict):
            raise Godot25DPreviewError(f"missing pivot for {name}")
        names.add(name)
        bounds = _alpha_bounds(path)
        if bounds is not None:
            if name == "torso":
                body_bottom = bounds[3]
            if content_bounds is None:
                content_bounds = list(bounds)
            else:
                content_bounds[0] = min(content_bounds[0], bounds[0])
                content_bounds[1] = min(content_bounds[1], bounds[1])
                content_bounds[2] = max(content_bounds[2], bounds[2])
                content_bounds[3] = max(content_bounds[3], bounds[3])
        layers.append(
            {
                "name": name,
                "path": str(path),
                "parent": layer.get("parent") or "",
                "pivot": {"x": float(pivot["x"]), "y": float(pivot["y"])},
                "z_index": int(layer.get("z_index", 0)),
                "depth": DEPTH.get(name, 0.0),
                "secondary_motion": SECONDARY.get(name, 0.1),
            }
        )

    required = {
        "head", "torso",
        "upper_arm_l", "forearm_l", "hand_l",
        "upper_arm_r", "forearm_r", "hand_r",
    }
    missing = sorted(required - names)
    if missing:
        raise Godot25DPreviewError(f"Rig V2 missing upper-body layers: {', '.join(missing)}")

    if content_bounds is None:
        content_bounds = [0, 0, width, height]
    if body_bottom is None:
        body_bottom = content_bounds[3]
    torso = next(layer for layer in layers if layer["name"] == "torso")
    focus_x = float(torso["pivot"]["x"])
    background = _resolve_background(project_dir, background_path)
    frame_profile = FRAMING_PROFILES[framing]

    return {
        "schema_version": 2,
        "character_id": character_id,
        "rig_id": rig.get("id"),
        "output": {"width": 720, "height": 1280},
        "canvas": {"width": width, "height": height},
        "duration_seconds": max(2.0, min(8.0, float(duration_seconds))),
        "background": {
            "path": str(background) if background else "",
            "zoom": 1.018,
            "dimming": 0.12,
        },
        "framing": {
            "profile": framing,
            "zoom": frame_profile["zoom"],
            "bottom_overscan_px": frame_profile["bottom_overscan_px"],
            "focus_x": focus_x,
            "content_bounds": {
                "left": content_bounds[0],
                "top": content_bounds[1],
                "right": content_bounds[2],
                "bottom": content_bounds[3],
                "body_bottom": body_bottom,
            },
        },
        "layers": layers,
        "visual_features": [
            "real_scene_background" if background else "neutral_background",
            f"{framing.lower()}_framing",
            "hierarchical_pivots",
            "restrained_breathing",
            "head_and_hair_secondary_motion",
            "sleeve_secondary_motion",
            "subtle_layer_parallax",
            "background_slow_push",
        ],
        "human_review": "PENDING",
    }


def render_preview(
    project_dir: Path,
    character_id: str,
    output: Path | None = None,
    duration_seconds: float = 4.0,
    fps: int = 24,
    background_path: Path | None = None,
    framing: str = "UPPER_BODY",
) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    config = build_preview_config(
        project_dir,
        character_id,
        duration_seconds,
        background_path=background_path,
        framing=framing,
    )
    fps = max(12, min(60, int(fps)))
    frames = int(round(float(config["duration_seconds"]) * fps))

    cache_dir = project_dir / "cache" / "godot-25d"
    cache_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    config_path = cache_dir / f"{character_id.lower()}-{stamp}.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if output is None:
        output = project_dir / "lookdev" / f"{character_id.lower()}-godot-25d-{stamp}.mp4"
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    avi = cache_dir / f"{character_id.lower()}-{stamp}.avi"

    env = os.environ.copy()
    env["VIDEO_CREATOR_25D_CONFIG"] = str(config_path)
    command = [
        "/usr/bin/arch",
        "-arm64",
        _godot_binary(),
        "--path",
        str(GODOT_PROJECT),
        "--write-movie",
        str(avi),
        "--fixed-fps",
        str(fps),
        "--quit-after",
        str(frames),
        "--disable-vsync",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, env=env, timeout=180)
    if completed.returncode != 0 or not avi.is_file():
        detail = (completed.stdout or "") + "\n" + (completed.stderr or "")
        raise Godot25DPreviewError(f"Godot 2.5D render failed: {detail[-3000:]}")

    ffmpeg = _ffmpeg_binary()
    converted = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(avi),
            "-an",
            "-vf",
            "scale=in_range=full:out_range=tv,format=yuv420p",
            "-c:v",
            "libx264",
            "-color_range",
            "tv",
            "-movflags",
            "+faststart",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if converted.returncode != 0 or not output.is_file():
        raise Godot25DPreviewError(f"ffmpeg conversion failed: {converted.stderr[-2000:]}")

    return {
        "status": "created",
        "provider": "godot_25d_local",
        "character_id": character_id,
        "rig_id": config["rig_id"],
        "output": output,
        "duration_seconds": config["duration_seconds"],
        "fps": fps,
        "features": config["visual_features"],
        "human_review": "PENDING",
        "config": config_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--background", type=Path)
    parser.add_argument("--framing", choices=("upper_body", "closeup"), default="upper_body")
    args = parser.parse_args()
    try:
        result = render_preview(
            args.project_dir,
            args.character_id,
            args.output,
            args.seconds,
            args.fps,
            background_path=args.background,
            framing=args.framing,
        )
    except (Godot25DPreviewError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1

    printable = dict(result)
    printable["output"] = str(result["output"])
    printable["config"] = str(result["config"])
    print(json.dumps({"status": "PASS", "result": printable}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
