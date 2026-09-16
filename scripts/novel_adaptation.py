#!/usr/bin/env python3
"""Validate a rights-gated short-story adaptation and render a rough animatic."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    Path("/System/Library/Fonts/PingFang.ttc"),
)
RIGHTS_ALLOWED = {"public_domain_source_verified", "licensed"}
CHANGE_TYPES = {"condensed", "omitted", "reordered", "added", "rephrased"}
COLORS = ("#182B3A", "#253D4B", "#334E56", "#35485B", "#4B3D4C", "#3D4A3D")


class NovelAdaptationError(ValueError):
    """Raised when adaptation input fails rights, source, or storyboard checks."""


def _required_text(value: Any, label: str, maximum: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise NovelAdaptationError(f"{label} must be 1 to {maximum} characters")
    return value.strip()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NovelAdaptationError(f"cannot read adaptation input: {error}") from error
    if not isinstance(payload, dict):
        raise NovelAdaptationError("adaptation input must be a JSON object")
    return payload


def _valid_url(value: Any, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    text = _required_text(value, label, 2000)
    from urllib.parse import urlsplit

    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise NovelAdaptationError(f"{label} must be an absolute http(s) URL without embedded credentials")
    return text


def validate_adaptation(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise NovelAdaptationError("adaptation input must use schema_version 1")
    if payload.get("test_only") is not True or payload.get("is_main_ip") is not False:
        raise NovelAdaptationError("pilot must be test_only and cannot be marked as the main IP")

    novel = payload.get("novel")
    source = payload.get("source")
    rights = payload.get("rights")
    episode = payload.get("episode")
    adaptation = payload.get("adaptation")
    if not all(isinstance(item, dict) for item in (novel, source, rights, episode, adaptation)):
        raise NovelAdaptationError("novel, source, rights, episode, and adaptation must be objects")

    normalized_novel = {
        "title": _required_text(novel.get("title"), "novel.title", 200),
        "author": _required_text(novel.get("author"), "novel.author", 200),
        "work_type": _required_text(novel.get("work_type"), "novel.work_type", 100),
    }
    normalized_source = {
        "source_title": _required_text(source.get("source_title"), "source.source_title", 300),
        "source_url": _valid_url(source.get("source_url"), "source.source_url"),
        "edition_note": _required_text(source.get("edition_note"), "source.edition_note", 500),
        "accessed_at": _required_text(source.get("accessed_at"), "source.accessed_at", 30),
    }
    try:
        date.fromisoformat(normalized_source["accessed_at"])
    except ValueError as error:
        raise NovelAdaptationError("source.accessed_at must use YYYY-MM-DD") from error
    if date.fromisoformat(normalized_source["accessed_at"]).isoformat() != normalized_source["accessed_at"]:
        raise NovelAdaptationError("source.accessed_at must use YYYY-MM-DD")

    rights_status = rights.get("status")
    if rights_status not in RIGHTS_ALLOWED:
        raise NovelAdaptationError("rights gate blocked: source must be verified public domain or explicitly licensed")
    evidence_urls = rights.get("evidence_urls")
    if not isinstance(evidence_urls, list):
        raise NovelAdaptationError("rights.evidence_urls must be a list")
    normalized_rights = {
        "status": rights_status,
        "basis": _required_text(rights.get("basis"), "rights.basis", 1000),
        "evidence_urls": [
            _valid_url(url, f"rights.evidence_urls[{index}]")
            for index, url in enumerate(evidence_urls)
        ],
        "human_review_required_before_publication": True,
    }
    if not normalized_rights["evidence_urls"]:
        raise NovelAdaptationError("rights.evidence_urls must include at least one evidence URL")

    episode_id = _required_text(episode.get("episode_id"), "episode.episode_id", 100)
    duration = episode.get("target_duration_seconds")
    if type(duration) is not int or not 20 <= duration <= 90:
        raise NovelAdaptationError("episode.target_duration_seconds must be an integer from 20 to 90")
    normalized_episode = {
        "episode_id": episode_id,
        "title": _required_text(episode.get("title"), "episode.title", 200),
        "logline": _required_text(episode.get("logline"), "episode.logline", 500),
        "target_duration_seconds": duration,
    }

    source_segments = adaptation.get("source_segments")
    changes = adaptation.get("changes")
    script = adaptation.get("script")
    storyboard = adaptation.get("storyboard")
    if not isinstance(source_segments, list) or not source_segments:
        raise NovelAdaptationError("adaptation.source_segments must be a non-empty list")
    if not isinstance(changes, list) or not changes:
        raise NovelAdaptationError("adaptation.changes must be a non-empty list")
    segment_map: dict[str, dict[str, Any]] = {}
    for index, segment in enumerate(source_segments):
        if not isinstance(segment, dict):
            raise NovelAdaptationError(f"source_segments[{index}] must be an object")
        segment_id = _required_text(segment.get("segment_id"), f"source_segments[{index}].segment_id", 100)
        if segment_id in segment_map:
            raise NovelAdaptationError(f"duplicate source segment ID: {segment_id}")
        segment_map[segment_id] = {
            "segment_id": segment_id,
            "locator": _required_text(segment.get("locator"), f"source_segments[{index}].locator", 300),
            "summary": _required_text(segment.get("summary"), f"source_segments[{index}].summary", 500),
        }

    change_map: dict[str, dict[str, Any]] = {}
    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            raise NovelAdaptationError(f"changes[{index}] must be an object")
        change_id = _required_text(change.get("change_id"), f"changes[{index}].change_id", 100)
        change_type = change.get("type")
        refs = change.get("source_segment_ids")
        if change_id in change_map:
            raise NovelAdaptationError(f"duplicate adaptation change ID: {change_id}")
        if change_type not in CHANGE_TYPES:
            raise NovelAdaptationError(f"changes[{index}].type must be one of: {', '.join(sorted(CHANGE_TYPES))}")
        if not isinstance(refs, list) or not refs or any(ref not in segment_map for ref in refs):
            raise NovelAdaptationError(f"changes[{index}] must refer to known source segments")
        change_map[change_id] = {
            "change_id": change_id,
            "type": change_type,
            "description": _required_text(change.get("description"), f"changes[{index}].description", 500),
            "source_segment_ids": list(dict.fromkeys(refs)),
        }

    if not isinstance(script, list) or not script:
        raise NovelAdaptationError("adaptation.script must be a non-empty list")
    if not isinstance(storyboard, list) or len(storyboard) != len(script):
        raise NovelAdaptationError("storyboard must contain one scene for each script beat")
    normalized_script: list[dict[str, Any]] = []
    normalized_storyboard: list[dict[str, Any]] = []
    beat_ids: set[str] = set()
    expected_start = 0.0
    for index, beat in enumerate(script):
        label = f"script[{index}]"
        if not isinstance(beat, dict):
            raise NovelAdaptationError(f"{label} must be an object")
        beat_id = _required_text(beat.get("beat_id"), f"{label}.beat_id", 100)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", beat_id):
            raise NovelAdaptationError(f"{label}.beat_id must use letters, numbers, underscores, or hyphens")
        if beat_id in beat_ids:
            raise NovelAdaptationError(f"duplicate script beat ID: {beat_id}")
        beat_ids.add(beat_id)
        segment_ids = beat.get("source_segment_ids")
        change_ids = beat.get("adaptation_change_ids", [])
        if not isinstance(segment_ids, list) or not segment_ids or any(ref not in segment_map for ref in segment_ids):
            raise NovelAdaptationError(f"{label} must refer to known source segments")
        if not isinstance(change_ids, list) or any(ref not in change_map for ref in change_ids):
            raise NovelAdaptationError(f"{label}.adaptation_change_ids contains an unknown change")
        normalized_script.append({
            "beat_id": beat_id,
            "narration": _required_text(beat.get("narration"), f"{label}.narration", 1000),
            "source_segment_ids": list(dict.fromkeys(segment_ids)),
            "adaptation_change_ids": list(dict.fromkeys(change_ids)),
        })

        scene = storyboard[index]
        scene_label = f"storyboard[{index}]"
        if not isinstance(scene, dict):
            raise NovelAdaptationError(f"{scene_label} must be an object")
        scene_id = _required_text(scene.get("scene_id"), f"{scene_label}.scene_id", 100)
        if scene_id != beat_id:
            raise NovelAdaptationError(f"{scene_label}.scene_id must match script beat {beat_id}")
        start, end = scene.get("start"), scene.get("end")
        if type(start) not in {int, float} or type(end) not in {int, float}:
            raise NovelAdaptationError(f"{scene_label} start and end must be numbers")
        if abs(float(start) - expected_start) > 0.001:
            raise NovelAdaptationError(f"{scene_label} timing has a gap or overlap")
        if float(end) <= float(start):
            raise NovelAdaptationError(f"{scene_label} timing must be positive")
        visual_source_refs = scene.get("source_segment_ids")
        if not isinstance(visual_source_refs, list) or not visual_source_refs or any(ref not in segment_map for ref in visual_source_refs):
            raise NovelAdaptationError(f"{scene_label} must cite known source segments")
        if set(visual_source_refs) - set(segment_ids):
            raise NovelAdaptationError(f"{scene_label} source references must be covered by its script beat")
        normalized_storyboard.append({
            "scene_id": scene_id,
            "start": float(start),
            "end": float(end),
            "caption": _required_text(scene.get("caption"), f"{scene_label}.caption", 120),
            "visual_description": _required_text(scene.get("visual_description"), f"{scene_label}.visual_description", 500),
            "source_segment_ids": list(dict.fromkeys(visual_source_refs)),
        })
        expected_start = float(end)
    if abs(expected_start - duration) > 0.001:
        raise NovelAdaptationError("storyboard must cover the full target duration")

    normalized_adaptation = {
        "source_segments": list(segment_map.values()),
        "changes": list(change_map.values()),
        "script": normalized_script,
        "storyboard": normalized_storyboard,
    }
    return {
        "schema_version": 1,
        "test_only": True,
        "is_main_ip": False,
        "novel": normalized_novel,
        "source": normalized_source,
        "rights": normalized_rights,
        "episode": normalized_episode,
        "adaptation": normalized_adaptation,
    }


def _wrap(text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _draw_wrapped(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, xy: tuple[int, int], max_width: int, fill: str, line_spacing: int) -> None:
    x, y = xy
    for line in _wrap(text, font, draw, max_width):
        draw.text((x, y), line, font=font, fill=fill)
        y += line_spacing


def _render_card(path: Path, scene: dict[str, Any], index: int, font_path: Path, novel_title: str) -> None:
    image = Image.new("RGB", (540, 960), COLORS[index % len(COLORS)])
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(str(font_path), 46)
    caption_font = ImageFont.truetype(str(font_path), 31)
    body_font = ImageFont.truetype(str(font_path), 24)
    small_font = ImageFont.truetype(str(font_path), 18)
    draw.rounded_rectangle((32, 36, 206, 78), radius=16, fill="#D9B26F")
    draw.text((48, 46), f"流程测试 · {index + 1:02d}", font=small_font, fill="#1B2630")
    draw.text((32, 126), novel_title, font=caption_font, fill="#F0E4CC")
    draw.line((32, 184, 508, 184), fill="#D9B26F", width=2)
    _draw_wrapped(draw, scene["caption"], title_font, (32, 242), 476, "#FFFFFF", 62)
    draw.rounded_rectangle((30, 510, 510, 830), radius=24, fill="#111C24")
    _draw_wrapped(draw, scene["visual_description"], body_font, (54, 548), 432, "#E6E1D7", 42)
    draw.text((32, 884), f"SCENE {index + 1}  |  {scene['start']:05.1f}s–{scene['end']:05.1f}s", font=small_font, fill="#D9B26F")
    draw.text((32, 916), "静音分镜 Animatic · 非最终画面", font=small_font, fill="#D2D5D7")
    image.save(path, format="PNG", optimize=True)


def _render_rough_cut(output: Path, cards: list[Path], scenes: list[dict[str, Any]]) -> None:
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for card, scene in zip(cards, scenes):
        duration = scene["end"] - scene["start"]
        command.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", str(card)])
    filters: list[str] = []
    for index in range(len(cards)):
        filters.append(f"[{index}:v]fps=30,format=yuv420p,setpts=PTS-STARTPTS[v{index}]")
    filters.append("".join(f"[v{index}]" for index in range(len(cards))) + f"concat=n={len(cards)}:v=1:a=0[vout]")
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "[vout]", "-an",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(output),
    ])
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise NovelAdaptationError("ffmpeg is required to render the rough animatic") from error
    if completed.returncode != 0:
        raise NovelAdaptationError(f"ffmpeg failed: {completed.stderr[-1200:]}")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _markdown_report(adaptation: dict[str, Any]) -> tuple[str, str, str]:
    script = adaptation["adaptation"]["script"]
    storyboard = adaptation["adaptation"]["storyboard"]
    title = adaptation["episode"]["title"]
    script_md = [f"# {title}", "", "> 小说剧情试改稿 · 仅流程测试，不是主 IP，也不是发布稿。", ""]
    for beat, scene in zip(script, storyboard):
        script_md.extend([f"## {beat['beat_id']}", "", beat["narration"], "", f"来源段落：{', '.join(beat['source_segment_ids'])}", ""])
    storyboard_md = [f"# 分镜：{title}", "", "> 静音低保真 animatic；不代表最终国风动画效果。", ""]
    for scene in storyboard:
        storyboard_md.extend([
            f"## {scene['scene_id']} · {scene['start']:.1f}s–{scene['end']:.1f}s",
            "",
            f"字幕：{scene['caption']}",
            f"临时画面：{scene['visual_description']}",
            f"来源段落：{', '.join(scene['source_segment_ids'])}",
            "",
        ])
    checklist_md = [
        "# 人工复核清单",
        "",
        "- [ ] 核对候选作品及具体底本版本的权利状态。",
        "- [ ] 逐场景核对与原作段落的对应关系及改编变化。",
        "- [ ] 审核剧情逻辑、叙事节奏和字幕。",
        "- [ ] 替换所有临时卡片；本阶段未生成或使用正式角色图、配音、音乐。",
        "- [ ] 通过完整技术与内容质检后再讨论发布包。",
        "",
        "本产物为静音流程样片，明确禁止自动发布。",
    ]
    return "\n".join(script_md), "\n".join(storyboard_md), "\n".join(checklist_md)


def build_adaptation_package(payload: Any, output_dir: Path, *, font_path: Path | None = None) -> dict[str, Any]:
    adaptation = validate_adaptation(payload)
    target = Path(output_dir).expanduser().resolve()
    if target.exists():
        raise NovelAdaptationError(f"refusing to overwrite existing output: {target}")
    selected_font = font_path or next((candidate for candidate in FONT_CANDIDATES if candidate.is_file()), None)
    if selected_font is None or not Path(selected_font).is_file():
        raise NovelAdaptationError("a Chinese system font is required to render storyboard cards")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        normalized_payload = adaptation
        _write_json(staging / "source-record.json", {
            "schema_version": 1,
            "novel": normalized_payload["novel"],
            "source": normalized_payload["source"],
            "rights": normalized_payload["rights"],
            "test_only": True,
            "is_main_ip": False,
        })
        _write_json(staging / "adaptation-plan.json", {
            "schema_version": 1,
            "episode": normalized_payload["episode"],
            "source_segments": normalized_payload["adaptation"]["source_segments"],
            "changes": normalized_payload["adaptation"]["changes"],
        })
        _write_json(staging / "story-script.json", {
            "schema_version": 1,
            "episode": normalized_payload["episode"],
            "script": normalized_payload["adaptation"]["script"],
        })
        _write_json(staging / "storyboard.json", {
            "schema_version": 1,
            "episode": normalized_payload["episode"],
            "scenes": normalized_payload["adaptation"]["storyboard"],
        })
        _write_json(staging / "rights-review.json", {
            "schema_version": 1,
            "status": "REQUIRES_HUMAN_REVIEW",
            "automated_gate_status": "PASS_METADATA_ONLY",
            "rights_status": normalized_payload["rights"]["status"],
            "basis": normalized_payload["rights"]["basis"],
            "evidence_urls": normalized_payload["rights"]["evidence_urls"],
            "evidence_checked_by_tool": False,
            "publication_allowed": False,
            "manual_rights_review_required_before_publication": True,
        })
        script_md, storyboard_md, checklist_md = _markdown_report(normalized_payload)
        (staging / "story-script.md").write_text(script_md, encoding="utf-8")
        (staging / "storyboard.md").write_text(storyboard_md, encoding="utf-8")
        (staging / "review-checklist.md").write_text(checklist_md, encoding="utf-8")
        card_dir = staging / "cards"
        card_dir.mkdir()
        scenes = normalized_payload["adaptation"]["storyboard"]
        cards = []
        for index, scene in enumerate(scenes):
            card = card_dir / f"{scene['scene_id']}.png"
            _render_card(card, scene, index, Path(selected_font), normalized_payload["novel"]["title"])
            cards.append(card)
        _render_rough_cut(staging / "rough-cut.mp4", cards, scenes)
        duration = normalized_payload["episode"]["target_duration_seconds"]
        report = {
            "schema_version": 1,
            "status": "READY_FOR_HUMAN_REVIEW",
            "test_only": True,
            "is_main_ip": False,
            "publication_allowed": False,
            "video_kind": "silent_storyboard_animatic",
            "duration_seconds": duration,
            "scene_count": len(scenes),
            "outputs": [
                "source-record.json", "rights-review.json", "adaptation-plan.json",
                "story-script.json", "story-script.md", "storyboard.json",
                "storyboard.md", "rough-cut.mp4", "review-checklist.md",
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        _write_json(staging / "run-report.json", report)
        try:
            os.rename(staging, target)
        except FileExistsError as error:
            raise NovelAdaptationError(f"refusing to overwrite existing output: {target}") from error
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {**report, "output_dir": str(target)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_adaptation_package(_read_json(args.input_file), args.output_dir)
    except (OSError, NovelAdaptationError) as error:
        print(f"novel-adaptation: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
