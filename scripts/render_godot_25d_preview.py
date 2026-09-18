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
    "torso": 0.05,
    "head": 0.10,
    "upper_arm_l": 0.28,
    "forearm_l": 0.42,
    "hand_l": 0.55,
    "upper_arm_r": 0.22,
    "forearm_r": 0.36,
    "hand_r": 0.50,
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


def build_preview_config(project_dir: Path, character_id: str, duration_seconds: float = 4.0) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    rig = _load_rig(project_dir, character_id)
    if str(rig.get("profile")) not in {"GODOT_UPPER_BODY_IK", "GODOT_FULL_BODY_IK"}:
        raise Godot25DPreviewError("Rig V2 is not IK-ready profile")

    canvas = rig.get("canvas") if isinstance(rig.get("canvas"), dict) else {}
    width, height = int(canvas.get("width", 0)), int(canvas.get("height", 0))
    if width <= 0 or height <= 0:
        raise Godot25DPreviewError("Rig V2 canvas is invalid")

    layers: list[dict[str, Any]] = []
    names = set()
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

    return {
        "schema_version": 1,
        "character_id": character_id,
        "rig_id": rig.get("id"),
        "canvas": {"width": width, "height": height},
        "duration_seconds": max(2.0, min(8.0, float(duration_seconds))),
        "layers": layers,
        "visual_features": [
            "hierarchical_pivots",
            "breathing",
            "head_secondary_motion",
            "arm_raise_hold_return",
            "layer_parallax",
            "secondary_squash",
            "contact_shadow",
        ],
        "human_review": "PENDING",
    }


def render_preview(
    project_dir: Path,
    character_id: str,
    output: Path | None = None,
    duration_seconds: float = 4.0,
    fps: int = 24,
) -> dict[str, Any]:
    project_dir = Path(project_dir).expanduser().resolve()
    config = build_preview_config(project_dir, character_id, duration_seconds)
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
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
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
    args = parser.parse_args()
    try:
        result = render_preview(args.project_dir, args.character_id, args.output, args.seconds, args.fps)
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
