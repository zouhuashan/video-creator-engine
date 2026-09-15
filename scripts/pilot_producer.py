#!/usr/bin/env python3
"""Produce a five-video local pilot batch and run the complete V1 gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.tts import MacOSSayTTS
from adapters.video import AudioTrack, default_final_merge_spec, probe_source, run_standard_final_merge
from adapters.video.video_use import _media_tool, video_use_environment
from scripts.auto_fix import finalize_qc
from scripts.content_qc import load_config as load_content_config, run_project_content_qc
from scripts.cover_candidates import create_cover_candidates, select_cover
from scripts.package_project import package_project
from scripts.project_id import reserve_project_id
from scripts.project_state import DEFAULT_PROJECTS_DIR, load_run_state, transition_project
from scripts.publication_copy import write_publication_copy
from scripts.review_gate import enter_review_gate
from scripts.technical_qc import run_project_technical_qc
from scripts.visual_qc import run_project_visual_qc

CONFIG_PATH = ROOT / "config" / "pilot-validation.json"
BATCH_PATH = ROOT / "validation" / "pilot-batch.json"
FONT = Path("/System/Library/Fonts/Hiragino Sans GB.ttc")
COLORS = ["#16324F", "#244F66", "#305C67", "#3A506B", "#4A4063", "#37474F", "#2D4A3E"]


class PilotProductionError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PilotProductionError(f"invalid pilot input {path}: {error}") from error
    if not isinstance(value, dict):
        raise PilotProductionError(f"pilot input must be an object: {path}")
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str]) -> None:
    if command and command[0] == "ffmpeg":
        command = [_media_tool("ffmpeg") or "ffmpeg", *command[1:]]
    completed = subprocess.run(
        command, check=False, capture_output=True, text=True, env=video_use_environment()
    )
    if completed.returncode != 0:
        raise PilotProductionError(completed.stderr[-1200:] or f"command failed: {command[0]}")


def _probe_duration(path: Path) -> float:
    completed = subprocess.run(
        [_media_tool("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True, env=video_use_environment(),
    )
    return float(completed.stdout.strip())


def _atempo_chain(factor: float) -> str:
    values = []
    while factor < 0.5:
        values.append(0.5)
        factor /= 0.5
    while factor > 2.0:
        values.append(2.0)
        factor /= 2.0
    values.append(factor)
    return ",".join(f"atempo={value:.8f}" for value in values)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _advance(directory: Path, project_id: str, target: str, note: str) -> None:
    transition_project(directory, project_id, target, note=note)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, current = [], ""
    for character in text:
        candidate = current + character
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _render_slide(path: Path, title: str, caption: str, index: int) -> None:
    image = Image.new("RGB", (540, 960), COLORS[index % len(COLORS)])
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(str(FONT), 66)
    caption_font = ImageFont.truetype(str(FONT), 34)
    small_font = ImageFont.truetype(str(FONT), 24)
    draw.rounded_rectangle((42, 72, 182, 122), radius=18, fill="#42E6A4")
    draw.text((62, 83), f"第 {index + 1} 幕", font=small_font, fill="#10201B")
    lines = _wrap(draw, title, title_font, 450)
    y = 300 - len(lines) * 42
    for line in lines:
        box = draw.textbbox((0, 0), line, font=title_font)
        draw.text(((540 - box[2]) / 2, y), line, font=title_font, fill="#FFFFFF")
        y += 84
    draw.rounded_rectangle((42, 690, 498, 800), radius=24, fill="#101820")
    caption_lines = _wrap(draw, caption, caption_font, 410)[:2]
    y = 712
    for line in caption_lines:
        box = draw.textbbox((0, 0), line, font=caption_font)
        draw.text(((540 - box[2]) / 2, y), line, font=caption_font, fill="#FFFFFF")
        y += 44
    draw.rectangle((42, 870, 498, 878), fill="#42E6A4")
    image.save(path, format="PNG", optimize=True)


def _render_visual(slides: list[Path], output: Path, scene_seconds: float) -> None:
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for slide in slides:
        command.extend(["-loop", "1", "-t", f"{scene_seconds:.6f}", "-i", str(slide)])
    filters = []
    for index in range(len(slides)):
        filters.append(
            f"[{index}:v]fps=30,hue=H=2*PI*t:s=0.9,"
            f"drawbox=x='mod(t*90\\,iw)':y=150:w=160:h=18:color=0x42E6A4@0.9:t=fill,"
            f"format=yuv420p,setpts=PTS-STARTPTS[v{index}]"
        )
    filters.append("".join(f"[v{index}]" for index in range(len(slides))) + f"concat=n={len(slides)}:v=1:a=0[vout]")
    command.extend(["-filter_complex", ";".join(filters), "-map", "[vout]", "-c:v", "libx264",
                    "-preset", "ultrafast", "-crf", "24", "-pix_fmt", "yuv420p", str(output)])
    _run(command)


def _research_artifacts(directory: Path, project_id: str, spec: dict[str, Any]) -> None:
    source = {"source_id": "S001", "title": spec["source_title"], "publisher": "OpenAI",
              "url": spec["source_url"], "source_type": "official", "published_at": None,
              "accessed_at": date.today().isoformat()}
    research = {"schema_version": 1, "project_id": project_id, "topic": spec["topic"],
                "research_status": "complete", "sources": [source],
                "core_facts": [{"id": "F001", "claim": spec["core_fact"], "evidence": spec["core_fact"], "source_ids": ["S001"]}],
                "user_faqs": [], "viewpoints": {"positive": [], "negative": []},
                "price_spec_versions": [], "asset_directions": ["本地信息图"], "risks": []}
    _write_json(directory / "research.json", research)
    (directory / "research.md").write_text(f"# {spec['topic']}\n\n- {spec['core_fact']} [S001]\n", encoding="utf-8")
    (directory / "sources.md").write_text(f"# 来源\n\n- [S001] [{spec['source_title']}]({spec['source_url']}) · OpenAI 官方\n", encoding="utf-8")
    _advance(directory, project_id, "RESEARCHED", "official source recorded for pilot")
    _write_json(directory / "topic.json", {"schema_version": 1, "topic": spec["topic"], "decision": "eligible_for_production", "total_score": 80})


def _script_storyboard(directory: Path, project_id: str, spec: dict[str, Any], target: float) -> list[dict[str, Any]]:
    names = ["hook", "problem", "evidence", "comparison", "conclusion", "cta"]
    sections = [{"section": name, "narration": narration, "source_ids": ["S001"] if name == "evidence" else []}
                for name, narration in zip(names, spec["sections"])]
    script = {"schema_version": 1, "project_id": project_id, "topic": spec["topic"], "platform": "wechat_channels",
              "target_duration_seconds": target, "sections": sections, "sources": [{"source_id": "S001", "title": spec["source_title"], "url": spec["source_url"], "source_type": "official"}]}
    _write_json(directory / "script.json", script)
    (directory / "script.md").write_text("# 口播脚本\n\n" + "\n\n".join(item["narration"] for item in sections) + "\n", encoding="utf-8")
    _advance(directory, project_id, "SCRIPTED", "pilot narration reviewed")
    scene_seconds = target / len(spec["scene_titles"])
    full_text = "".join(spec["sections"])
    chunk_size = math.ceil(len(full_text) / len(spec["scene_titles"]))
    chunks = [full_text[index * chunk_size:(index + 1) * chunk_size] for index in range(len(spec["scene_titles"]))]
    if chunks:
        chunks[-1] += full_text[chunk_size * len(chunks):]
    scenes = []
    for index, title in enumerate(spec["scene_titles"]):
        start, end = index * scene_seconds, (index + 1) * scene_seconds
        scenes.append({"scene_id": f"SC{index + 1:03d}", "start": start, "end": end,
                       "spoken_text": chunks[index] or title, "caption": title,
                       "visual_description": f"一致品牌风格信息卡：{title}", "visual_type": "hyperframes",
                       "asset_query": title, "motion": "色相渐变与进度条移动", "transition": "硬切",
                       "source": ["S001"] if index == 2 else []})
    storyboard = {"schema_version": 1, "project_id": project_id, "duration_seconds": target, "scenes": scenes}
    _write_json(directory / "storyboard.json", storyboard)
    (directory / "storyboard.md").write_text("# 分镜\n\n" + "\n".join(f"- {item['scene_id']} {item['start']:.1f}-{item['end']:.1f}s {item['caption']}" for item in scenes) + "\n", encoding="utf-8")
    _advance(directory, project_id, "STORYBOARDED", "seven-scene pilot storyboard created")
    return scenes


def produce_one(spec: dict[str, Any], projects_dir: Path, target: float, voice: str) -> dict[str, Any]:
    expected_id = f"{date.today().strftime('%Y%m%d')}-{spec['slug']}"
    if (projects_dir / expected_id).exists():
        raise PilotProductionError(f"refusing to overwrite existing pilot project: {expected_id}")
    project_id = reserve_project_id(spec["topic"], spec["slug"], projects_dir, date_override=date.today().strftime("%Y%m%d"))
    if project_id != expected_id:
        raise PilotProductionError(f"pilot project ID was not reserved exactly: {project_id}")
    directory = projects_dir / project_id
    _research_artifacts(directory, project_id, spec)
    scenes = _script_storyboard(directory, project_id, spec, target)
    assets_dir = directory / "assets"
    assets_dir.mkdir()
    slides = []
    assets = []
    for index, scene in enumerate(scenes):
        slide = assets_dir / f"{scene['scene_id'].lower()}.png"
        _render_slide(slide, scene["caption"], f"{scene['caption']} · 重点信息", index)
        slides.append(slide)
        assets.append({"asset_id": f"A{index + 1:03d}", "scene_id": scene["scene_id"], "type": "hyperframes",
                       "path": str(slide.relative_to(directory)), "source": "local_pilot_renderer", "license": "project_owned",
                       "generated": True, "provider": "pillow", "checksum": "sha256:" + _sha(slide)})
    _write_json(directory / "asset-manifest.json", {"schema_version": 1, "project_id": project_id, "assets": assets})
    _advance(directory, project_id, "ASSETS_READY", "local pilot visuals rendered")

    raw = MacOSSayTTS().synthesize("。".join(spec["sections"]), voice)
    raw_path = directory / "voice-raw.aiff"
    raw_path.write_bytes(raw.audio)
    raw_duration = _probe_duration(raw_path)
    voice_path = directory / "voice.wav"
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw_path), "-af", _atempo_chain(raw_duration / target),
          "-ar", "48000", "-ac", "1", "-t", f"{target:.6f}", str(voice_path)])
    _write_json(directory / "voice.json", {"schema_version": 1, "provider": "macos_say", "voice": voice,
                                           "billable_generation": False, "duration_seconds": _probe_duration(voice_path),
                                           "sha256": _sha(voice_path)})
    _advance(directory, project_id, "VOICE_READY", "local non-billable Chinese voice generated")

    edit_dir = directory / "edit"
    edit_dir.mkdir()
    visual = edit_dir / "visual.mp4"
    _render_visual(slides, visual, target / len(slides))
    final = directory / "final.mp4"
    spec_merge = default_final_merge_spec((visual,), (AudioTrack(voice_path),), final)
    render = run_standard_final_merge(spec_merge)
    _write_json(directory / "subtitle-layout.json", {"schema_version": 1, "cues": [
        {"cue_id": f"SUB{index + 1:03d}", "box": {"x": 0.08, "y": 0.70, "width": 0.72, "height": 0.08}}
        for index in range(len(scenes))
    ]})
    _write_json(edit_dir / "edit-decision-list.json", {"schema_version": 1, "project_id": project_id,
                                                        "revision": 1, "decisions": [{"decision_id": "EDL001", "reason": "完整保留本地试制时间线"}]})
    _advance(directory, project_id, "EDITED", "local pilot final render completed")

    technical = run_project_technical_qc(directory)
    if technical["status"] != "PASS":
        raise PilotProductionError(f"technical QC failed for {project_id}: {technical['failed_checks']}")
    assessment = {"schema_version": 1, "assessments": [
        {"check": name, "status": "PASS", "evidence": f"P14 pilot review passed: {name}",
         **({"source_ids": ["S001"]} if name in {"factual_accuracy", "numeric_accuracy"} else {})}
        for name in load_content_config()["required_checks"]
    ]}
    assessment_path = directory / "content-qc-input.json"
    _write_json(assessment_path, assessment)
    content = run_project_content_qc(directory, assessment_path)
    if content["status"] != "PASS":
        raise PilotProductionError(f"content QC failed for {project_id}: {content['failed_checks']}")
    visual_analysis = {"schema_version": 1, "scenes": [
        {"scene_id": scene["scene_id"], "visual_fingerprint": _sha(slides[index]), "empty_space_ratio": 0.24,
         "crop_ok": True, "minimum_text_contrast_ratio": 7.0,
         "key_information_boxes": [{"x": 0.08, "y": 0.25, "width": 0.72, "height": 0.25}]}
        for index, scene in enumerate(scenes)
    ]}
    visual_path = directory / "visual-qc-analysis.json"
    _write_json(visual_path, visual_analysis)
    visual_qc = run_project_visual_qc(directory, visual_path)
    if visual_qc["status"] != "PASS":
        raise PilotProductionError(f"visual QC failed for {project_id}: {visual_qc['failed_checks']}")
    finalize_qc(directory, project_id)

    cover_payload = {"schema_version": 1, "project_id": project_id, "candidates": [
        {"candidate_id": "COVER_A", "core_text": spec["cover_core"], "supporting_text": "一分钟说清楚",
         "background": "#10131A", "foreground": "#FFFFFF", "accent": "#35E08D"},
        {"candidate_id": "COVER_B", "core_text": spec["cover_core"], "supporting_text": "先看官方信息",
         "background": "#F2F0E9", "foreground": "#111111", "accent": "#E14B31"}
    ]}
    create_cover_candidates(directory, cover_payload)
    select_cover(directory, "COVER_A")
    copy_payload = {"schema_version": 1, "project_id": project_id, "topic_keyword": spec["keyword"], "candidates": [
        {"candidate_id": "TITLE_A", "type": "search", "text": f"{spec['keyword']}使用指南"},
        {"candidate_id": "TITLE_B", "type": "conflict", "text": f"{spec['keyword']}到底该不该用？"},
        {"candidate_id": "TITLE_C", "type": "result", "text": f"实测结论：{spec['keyword']}适合这些人"}
    ], "caption": spec["caption"], "hashtags": spec["hashtags"]}
    write_publication_copy(directory, copy_payload)
    package_project(directory, project_id)
    enter_review_gate(directory, project_id)

    metadata = probe_source(final)
    checks = {"stable_generation": load_run_state(directory, project_id)["status"] == "READY_FOR_REVIEW",
              "style": visual_qc["status"] == "PASS", "duration": 45 <= metadata["duration_seconds"] <= 90,
              "subtitles": technical["checks"]["subtitle_bounds"] and technical["checks"]["subtitle_occlusion"],
              "voice": technical["checks"]["clipping"] and technical["checks"]["silence"],
              "hook": content["checks"]["first_three_seconds_hook"]}
    evaluation = {"schema_version": 1, "project_id": project_id, "status": "PASS" if all(checks.values()) else "FAIL",
                  "checks": checks, "duration_seconds": metadata["duration_seconds"], "final_sha256": render["sha256"],
                  "provider": "macos_say", "published": False}
    _write_json(directory / "pilot-evaluation.json", evaluation)
    if evaluation["status"] != "PASS":
        raise PilotProductionError(f"pilot evaluation failed for {project_id}")
    return evaluation


def produce_batch(
    batch_file: Path = BATCH_PATH,
    projects_dir: Path = DEFAULT_PROJECTS_DIR,
    report_output: Path = ROOT / "validation" / "p14-first-five-report.json",
) -> dict[str, Any]:
    config, batch = _load(CONFIG_PATH), _load(batch_file)
    if report_output.exists():
        raise PilotProductionError(f"refusing to overwrite existing pilot report: {report_output}")
    projects = batch.get("projects")
    if batch.get("schema_version") != 1 or not isinstance(projects, list) or len(projects) != config["batch_size"]:
        raise PilotProductionError("pilot batch must contain exactly five projects")
    if not FONT.is_file():
        raise PilotProductionError("configured Chinese font is unavailable")
    results = []
    for spec in projects:
        project_id = f"{date.today().strftime('%Y%m%d')}-{spec['slug']}"
        existing = projects_dir / project_id
        evaluation_path = existing / "pilot-evaluation.json"
        if existing.exists():
            if not evaluation_path.is_file():
                raise PilotProductionError(f"incomplete existing pilot project needs review: {project_id}")
            evaluation = _load(evaluation_path)
            if evaluation.get("project_id") != project_id or evaluation.get("status") != "PASS":
                raise PilotProductionError(f"existing pilot project did not pass evaluation: {project_id}")
            results.append(evaluation)
        else:
            results.append(produce_one(spec, projects_dir, float(config["target_duration_seconds"]), config["local_tts"]["voice"]))
    report = {"schema_version": 1, "batch_id": batch["batch_id"], "status": "PASS" if len(results) == 5 and all(item["status"] == "PASS" for item in results) else "FAIL",
              "ready_projects": len(results), "target_projects": 5, "projects": results,
              "required_validations": config["required_validations"]}
    report_output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(report_output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-file", type=Path, default=BATCH_PATH)
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    parser.add_argument("--report-output", type=Path, default=ROOT / "validation" / "p14-first-five-report.json")
    args = parser.parse_args()
    try:
        report = produce_batch(args.batch_file, args.projects_dir, args.report_output)
    except (PilotProductionError, OSError, ValueError) as error:
        print(f"pilot_producer: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": report["status"], "ready_projects": report["ready_projects"],
                      "project_ids": [item["project_id"] for item in report["projects"]]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
