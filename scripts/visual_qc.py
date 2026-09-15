#!/usr/bin/env python3
"""Evaluate rendered-scene evidence for visual quality defects."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "visual-qc.json"


class VisualQCError(ValueError):
    """Raised when visual QC evidence is incomplete or malformed."""


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VisualQCError(f"invalid {label}: {error}") from error
    if not isinstance(payload, dict):
        raise VisualQCError(f"{label} must be a JSON object")
    return payload


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = _load_json(path, "visual QC config")
    if config.get("schema_version") != 1 or len(config.get("required_checks", [])) != 7:
        raise VisualQCError("unsupported or incomplete visual QC config")
    return config


def _box_valid(box: Any) -> bool:
    if not isinstance(box, dict) or set(box) != {"x", "y", "width", "height"}:
        return False
    try:
        x, y, width, height = (float(box[key]) for key in ("x", "y", "width", "height"))
    except (TypeError, ValueError):
        return False
    return x >= 0 and y >= 0 and width > 0 and height > 0 and x + width <= 1 and y + height <= 1


def _overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return not (
        left["x"] + left["width"] <= right["x"] or right["x"] + right["width"] <= left["x"]
        or left["y"] + left["height"] <= right["y"] or right["y"] + right["height"] <= left["y"]
    )


def evaluate_visual_qc(
    storyboard: dict[str, Any], analysis: dict[str, Any], config: dict[str, Any] | None = None
) -> dict[str, Any]:
    active = config or load_config()
    scenes = storyboard.get("scenes")
    analyzed = analysis.get("scenes")
    if analysis.get("schema_version") != 1 or not isinstance(scenes, list) or not scenes or not isinstance(analyzed, list):
        raise VisualQCError("visual QC requires storyboard scenes and schema_version 1 analysis scenes")
    scene_ids = [scene.get("scene_id") for scene in scenes if isinstance(scene, dict)]
    if len(scene_ids) != len(scenes) or len(set(scene_ids)) != len(scene_ids):
        raise VisualQCError("storyboard scene IDs must be present and unique")
    by_id: dict[str, dict[str, Any]] = {}
    required_fields = {"scene_id", "visual_fingerprint", "empty_space_ratio", "crop_ok", "minimum_text_contrast_ratio", "key_information_boxes"}
    for item in analyzed:
        if not isinstance(item, dict) or set(item) != required_fields:
            raise VisualQCError("each visual analysis scene must contain exactly the required fields")
        scene_id = item["scene_id"]
        if scene_id not in scene_ids or scene_id in by_id:
            raise VisualQCError(f"unknown or duplicate analyzed scene: {scene_id}")
        boxes = item["key_information_boxes"]
        if (
            not isinstance(item["visual_fingerprint"], str) or not item["visual_fingerprint"].strip()
            or type(item["crop_ok"]) is not bool or not isinstance(boxes, list)
            or any(not _box_valid(box) for box in boxes)
        ):
            raise VisualQCError(f"invalid visual evidence for {scene_id}")
        try:
            empty = float(item["empty_space_ratio"])
            contrast = float(item["minimum_text_contrast_ratio"])
        except (TypeError, ValueError) as error:
            raise VisualQCError(f"invalid visual metrics for {scene_id}") from error
        if not 0 <= empty <= 1 or contrast < 0:
            raise VisualQCError(f"visual metrics are out of range for {scene_id}")
        by_id[scene_id] = item
    missing = [scene_id for scene_id in scene_ids if scene_id not in by_id]
    if missing:
        raise VisualQCError(f"visual analysis is missing scenes: {', '.join(missing)}")

    long_shots, dense_subtitles, empty_scenes, bad_crops, low_contrast, ui_occlusion = [], [], [], [], [], []
    fingerprints: list[tuple[str, str]] = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        evidence = by_id[scene_id]
        try:
            duration = float(scene["end"]) - float(scene["start"])
        except (KeyError, TypeError, ValueError) as error:
            raise VisualQCError(f"invalid storyboard timing for {scene_id}") from error
        if duration <= 0:
            raise VisualQCError(f"invalid storyboard duration for {scene_id}")
        if duration > active["max_shot_seconds"]:
            long_shots.append({"scene_id": scene_id, "duration_seconds": duration})
        caption = str(scene.get("caption", "")).strip()
        density = len(caption.replace(" ", "")) / duration
        if density > active["max_subtitle_characters_per_second"]:
            dense_subtitles.append({"scene_id": scene_id, "characters_per_second": round(density, 3)})
        if float(evidence["empty_space_ratio"]) > active["max_empty_space_ratio"]:
            empty_scenes.append(scene_id)
        if not evidence["crop_ok"]:
            bad_crops.append(scene_id)
        if float(evidence["minimum_text_contrast_ratio"]) < active["minimum_text_contrast_ratio"]:
            low_contrast.append(scene_id)
        if any(_overlap(box, zone) for box in evidence["key_information_boxes"] for zone in active["reserved_ui_zones"]):
            ui_occlusion.append(scene_id)
        fingerprints.append((scene_id, evidence["visual_fingerprint"].strip()))
    repeated = [
        {"first_scene_id": fingerprints[index - 1][0], "second_scene_id": fingerprints[index][0], "fingerprint": fingerprints[index][1]}
        for index in range(1, len(fingerprints)) if fingerprints[index][1] == fingerprints[index - 1][1]
    ]
    checks = {
        "shot_too_long": not long_shots,
        "repeated_visuals": not repeated,
        "subtitle_density": not dense_subtitles,
        "abnormal_empty_space": not empty_scenes,
        "incorrect_crop": not bad_crops,
        "key_information_ui_occlusion": not ui_occlusion,
        "text_background_contrast": not low_contrast,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": 1, "status": "PASS" if not failed else "FAIL", "checks": checks,
        "failed_checks": failed,
        "evidence": {"long_shots": long_shots, "repeated_visuals": repeated,
                     "dense_subtitles": dense_subtitles, "abnormal_empty_space_scenes": empty_scenes,
                     "incorrect_crop_scenes": bad_crops, "ui_occluded_scenes": ui_occlusion,
                     "low_contrast_scenes": low_contrast},
    }


def run_project_visual_qc(project_dir: Path, analysis_file: Path) -> dict[str, Any]:
    directory = Path(project_dir).resolve()
    report = evaluate_visual_qc(
        _load_json(directory / "storyboard.json", "storyboard.json"),
        _load_json(analysis_file, "visual QC analysis"),
    )
    report["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    output = directory / "qc" / "visual-qc.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["output"] = str(output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--analysis-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_project_visual_qc(args.project_dir, args.analysis_file)
    except VisualQCError as error:
        print(f"visual_qc: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
