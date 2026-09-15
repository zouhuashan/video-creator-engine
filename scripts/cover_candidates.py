#!/usr/bin/env python3
"""Render and select readable vertical-video cover candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "cover.json"
HEX = re.compile(r"#[0-9A-Fa-f]{6}\Z")


class CoverError(ValueError):
    """Raised when cover candidates are invalid or cannot be rendered."""


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoverError(f"invalid cover config: {error}") from error
    if config.get("schema_version") != 1 or config.get("width") != 1080 or config.get("height") != 1920:
        raise CoverError("unsupported cover config")
    return config


def _font_path(config: dict[str, Any]) -> Path:
    for value in config.get("font_candidates", []):
        path = Path(value)
        if path.is_file():
            return path
    raise CoverError("no configured font with Chinese glyph support is available")


def _visible_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def validate_candidates(payload: dict[str, Any], config: dict[str, Any] | None = None) -> list[dict[str, str]]:
    active = config or load_config()
    candidates = payload.get("candidates")
    limits = active["candidate_count"]
    if payload.get("schema_version") != 1 or not isinstance(payload.get("project_id"), str) or not payload["project_id"].strip():
        raise CoverError("cover input requires schema_version 1 and project_id")
    if not isinstance(candidates, list) or not limits["min"] <= len(candidates) <= limits["max"]:
        raise CoverError("cover input requires 2-3 candidates")
    required = {"candidate_id", "core_text", "supporting_text", "background", "foreground", "accent"}
    ids, normalized = set(), []
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != required:
            raise CoverError("each cover candidate must contain exactly the required fields")
        candidate_id = candidate["candidate_id"]
        if not isinstance(candidate_id, str) or not re.fullmatch(r"COVER_[A-C]", candidate_id) or candidate_id in ids:
            raise CoverError("cover candidate IDs must be unique COVER_A through COVER_C")
        core = candidate["core_text"].strip() if isinstance(candidate["core_text"], str) else ""
        supporting = candidate["supporting_text"].strip() if isinstance(candidate["supporting_text"], str) else ""
        core_length = _visible_length(core)
        if not active["core_text_characters"]["min"] <= core_length <= active["core_text_characters"]["max"]:
            raise CoverError("cover core text must contain 3-10 visible characters")
        if not any(pattern in core for pattern in active["question_patterns"]):
            raise CoverError(f"cover {candidate_id} must make the question explicit")
        if _visible_length(supporting) > active["supporting_text_max_characters"] or "\n" in supporting:
            raise CoverError("cover supporting text must be one short line")
        if any(not isinstance(candidate[key], str) or not HEX.fullmatch(candidate[key]) for key in ("background", "foreground", "accent")):
            raise CoverError("cover colors must use six-digit hex values")
        normalized.append({**candidate, "core_text": core, "supporting_text": supporting})
        ids.add(candidate_id)
    return normalized


def _split_core(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text)
    if len(compact) <= 5:
        return [compact]
    midpoint = (len(compact) + 1) // 2
    return [compact[:midpoint], compact[midpoint:]]


def _fit_font(draw: ImageDraw.ImageDraw, lines: list[str], font_path: Path, preferred: int, minimum: int, max_width: int) -> ImageFont.FreeTypeFont:
    for size in range(preferred, minimum - 1, -4):
        font = ImageFont.truetype(str(font_path), size=size)
        if max(draw.textbbox((0, 0), line, font=font)[2] for line in lines) <= max_width:
            return font
    raise CoverError("cover core text cannot fit at the minimum mobile-readable size")


def render_candidate(candidate: dict[str, str], output: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    active = config or load_config()
    font_path = _font_path(active)
    image = Image.new("RGB", (active["width"], active["height"]), candidate["background"])
    draw = ImageDraw.Draw(image)
    margin = active["safe_margin_px"]
    lines = _split_core(candidate["core_text"])
    core_font = _fit_font(draw, lines, font_path, active["core_font_size"]["preferred"], active["core_font_size"]["minimum"], active["width"] - margin * 2)
    support_font = ImageFont.truetype(str(font_path), size=active["supporting_font_size"])
    badge_font = ImageFont.truetype(str(font_path), size=42)
    badge_box = draw.textbbox((0, 0), "视频号封面", font=badge_font)
    badge_width = badge_box[2] - badge_box[0] + 60
    draw.rounded_rectangle((margin, 150, margin + badge_width, 224), radius=24, fill=candidate["accent"])
    draw.text((margin + 30, 164), "视频号封面", font=badge_font, fill=candidate["background"])
    line_height = core_font.size * 1.2
    block_height = len(lines) * line_height
    y = (active["height"] - block_height) / 2 - 80
    for line in lines:
        box = draw.textbbox((0, 0), line, font=core_font)
        x = (active["width"] - (box[2] - box[0])) / 2
        draw.text((x, y), line, font=core_font, fill=candidate["foreground"], stroke_width=2, stroke_fill=candidate["foreground"])
        y += line_height
    if candidate["supporting_text"]:
        box = draw.textbbox((0, 0), candidate["supporting_text"], font=support_font)
        x = (active["width"] - (box[2] - box[0])) / 2
        draw.text((x, y + 80), candidate["supporting_text"], font=support_font, fill=candidate["accent"])
    draw.rectangle((margin, active["height"] - 250, active["width"] - margin, active["height"] - 238), fill=candidate["accent"])
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {"candidate_id": candidate["candidate_id"], "file": output.name, "width": image.width,
            "height": image.height, "core_text": candidate["core_text"], "supporting_text": candidate["supporting_text"],
            "core_font_size": core_font.size, "sha256": digest}


def create_cover_candidates(project_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    directory = Path(project_dir).resolve()
    candidates = validate_candidates(payload)
    if directory.name != payload["project_id"]:
        raise CoverError("cover project_id must match the project directory")
    output_dir = directory / "covers"
    manifest_path = directory / "cover-candidates.json"
    if output_dir.exists() or manifest_path.exists() or (directory / "cover.png").exists():
        raise CoverError("refusing to overwrite existing cover artifacts")
    temp_dir = Path(tempfile.mkdtemp(prefix=".covers.", dir=directory))
    descriptor, temp_manifest = tempfile.mkstemp(prefix=".cover-candidates.", suffix=".tmp", dir=directory)
    try:
        rendered = [render_candidate(item, temp_dir / f"{item['candidate_id'].lower()}.png") for item in candidates]
        manifest = {"schema_version": 1, "project_id": payload["project_id"], "selected": None, "candidates": rendered}
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        os.replace(temp_dir, output_dir)
        os.replace(temp_manifest, manifest_path)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temp_manifest)
        except FileNotFoundError:
            pass
        if output_dir.exists() and not manifest_path.exists():
            shutil.rmtree(output_dir)
        raise
    return manifest


def select_cover(project_dir: Path, candidate_id: str) -> dict[str, Any]:
    directory = Path(project_dir).resolve()
    manifest_path = directory / "cover-candidates.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoverError(f"invalid cover candidate manifest: {error}") from error
    match = next((item for item in manifest.get("candidates", []) if item.get("candidate_id") == candidate_id), None)
    if match is None:
        raise CoverError(f"unknown cover candidate: {candidate_id}")
    destination = directory / "cover.png"
    if destination.exists() or manifest.get("selected") is not None:
        raise CoverError("a cover has already been selected")
    source = directory / "covers" / match["file"]
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != match["sha256"]:
        raise CoverError("selected cover is missing or has changed")
    temporary = destination.with_name(f".{destination.name}.tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)
    manifest["selected"] = candidate_id
    manifest["selected_sha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
    temporary_manifest = manifest_path.with_name(f".{manifest_path.name}.tmp")
    temporary_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_manifest, manifest_path)
    return {"status": "PASS", "selected": candidate_id, "output": "cover.png", "sha256": manifest["selected_sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("project_dir", type=Path)
    create.add_argument("--input-file", type=Path, required=True)
    select = subparsers.add_parser("select")
    select.add_argument("project_dir", type=Path)
    select.add_argument("candidate_id")
    args = parser.parse_args()
    try:
        if args.command == "create":
            payload = json.loads(args.input_file.read_text(encoding="utf-8"))
            result = create_cover_candidates(args.project_dir, payload)
        else:
            result = select_cover(args.project_dir, args.candidate_id)
    except (OSError, json.JSONDecodeError, CoverError) as error:
        print(f"cover_candidates: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
