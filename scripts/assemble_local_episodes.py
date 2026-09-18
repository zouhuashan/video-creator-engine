#!/usr/bin/env python3
"""Assemble the five local Jing Hua Yuan pilot episodes from unit-level media."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.batch_render_final_shots import _background_for_shot, _particle_effect
from scripts.mux_timeline_shot import mux
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.render_character_rig_preview import render


def _shot_id(unit_id: str) -> str:
    return f"SHOT-{unit_id.removeprefix('UNIT-')}"


def _srt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _subtitle_blocks(text: str, max_line_chars: int = 15, max_lines: int = 2) -> list[str]:
    """Wrap Chinese subtitles into portrait-safe blocks.

    SRT/libass does not reliably wrap CJK text at the same width on every host.
    Writing explicit line breaks keeps subtitles inside a 9:16 safe area.
    """
    compact = re.sub(r"\s+", "", text.strip())
    if not compact:
        return []
    lines: list[str] = []
    current = ""
    for character in compact:
        if character in "，。！？；：、,.!?;:" and current:
            current += character
            continue
        if len(current) >= max_line_chars:
            lines.append(current)
            current = character
        else:
            current += character
    if current:
        lines.append(current)
    return ["\n".join(lines[index:index + max_lines]) for index in range(0, len(lines), max_lines)]


def _subtitle_entries(text: str, start: float, end: float) -> list[tuple[float, float, str]]:
    blocks = _subtitle_blocks(text)
    if not blocks:
        return []
    weights = [max(1, len(block.replace("\n", ""))) for block in blocks]
    total_weight = sum(weights)
    duration = max(0.001, end - start)
    entries: list[tuple[float, float, str]] = []
    cursor = start
    for index, (block, weight) in enumerate(zip(blocks, weights)):
        block_end = end if index == len(blocks) - 1 else cursor + duration * weight / total_weight
        entries.append((cursor, block_end, block))
        cursor = block_end
    return entries


def _media_duration(path: Path) -> float:
    result = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path)], text=True, capture_output=True)
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not match:
        raise RuntimeError(f"cannot read media duration: {path}")
    hours, minutes, seconds = match.groups()
    return round(int(hours) * 3600 + int(minutes) * 60 + float(seconds), 3)


def build_plan(project: Path) -> dict[str, Any]:
    project = project.expanduser().resolve()
    timeline = json.loads((project / "dynamic" / "mouth-cues.json").read_text(encoding="utf-8")).get("timeline", [])
    cues = {str(item["dialogue_line_id"]): item for item in timeline}
    batch = json.loads((project / "dynamic" / "final-batch.json").read_text(encoding="utf-8")).get("results", [])
    dialogue_videos = {str(item["shot_id"]): item for item in batch}
    episodes = []
    for script_path in sorted((project / "writing-room" / "episodes").glob("*/script.json")):
        episode = json.loads(script_path.read_text(encoding="utf-8"))["episode_script"]
        segments = []
        for scene in episode.get("scenes", []):
            for unit in scene.get("units", []):
                unit_id = str(unit["id"]); shot_id = _shot_id(unit_id); kind = str(unit["kind"])
                cue = cues.get(unit_id)
                duration = float(cue["end_seconds"]) if cue else float(unit.get("estimated_duration_seconds") or 3.0)
                background, background_asset_id = _background_for_shot(project, shot_id)
                segment: dict[str, Any] = {
                    "unit_id": unit_id,
                    "shot_id": shot_id,
                    "scene_id": str(scene["id"]),
                    "kind": kind,
                    "text": str(unit.get("text") or ""),
                    "duration_seconds": duration,
                    "background": background.relative_to(project).as_posix(),
                    "background_asset_id": background_asset_id,
                    "particle_effect": _particle_effect(background_asset_id),
                    "cue": cue,
                }
                if kind == "DIALOGUE":
                    media = dialogue_videos.get(shot_id)
                    if not media:
                        raise ValueError(f"dialogue final is missing: {shot_id}")
                    segment["source"] = "dialogue_final"
                    segment["media"] = media
                elif kind == "NARRATION":
                    if not cue or not cue.get("audio", {}).get("mix_asset_id"):
                        raise ValueError(f"narration timeline mix is missing: {unit_id}")
                    segment["source"] = "narration_render"
                else:
                    segment["source"] = "visual_render"
                segments.append(segment)
        episodes.append({"episode_id": str(episode["episode_id"]), "segments": segments})
    return {"schema_version": 1, "project_id": project.name, "episodes": episodes}


def _add_silence(video: Path, output: Path, seconds: float) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{seconds:.3f}",
        "-movflags", "+faststart", str(output),
    ], check=True, capture_output=True)
    return output


def _concat(clips: list[Path], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as handle:
        concat_path = Path(handle.name)
        for clip in clips:
            handle.write("file '" + str(clip.resolve()).replace("'", "'\\''") + "'\n")
    try:
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_path), "-c", "copy", "-movflags", "+faststart", str(output),
        ], check=True, capture_output=True)
    finally:
        concat_path.unlink(missing_ok=True)
    return output


def _burn_subtitles(video: Path, subtitles: Path, output: Path) -> Path:
    escaped = str(subtitles.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    style = "FontName=PingFang SC,FontSize=9,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=1,Outline=1,Shadow=0,MarginL=20,MarginR=20,MarginV=45,Alignment=2,WrapStyle=2"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-vf", f"subtitles='{escaped}':force_style='{style}'", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(output),
    ], check=True, capture_output=True)
    return output


def assemble(project: Path, episode_ids: set[str] | None = None) -> dict[str, Any]:
    project = project.expanduser().resolve(); plan = build_plan(project); repository = NovelAnimeRepository(project)
    segment_dir = project / "renders" / "episode-segments"; episode_dir = project / "renders" / "episodes"
    segment_dir.mkdir(parents=True, exist_ok=True); episode_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for episode in plan["episodes"]:
        episode_id = str(episode["episode_id"])
        if episode_ids and episode_id not in episode_ids:
            continue
        clips: list[Path] = []; srt: list[str] = []; cursor = 0.0; source_ids: list[str] = [episode_id]
        output_segments = []
        for segment in episode["segments"]:
            if segment["source"] == "dialogue_final":
                clip = project / str(segment["media"]["output"])
                source_ids.append(str(segment["media"]["asset_id"]))
            else:
                stem = str(segment["shot_id"]).lower(); draft = segment_dir / f"{stem}-draft.mp4"; clip = segment_dir / f"{stem}-final.mp4"
                render(project, project / str(segment["background"]), [], draft, float(segment["duration_seconds"]), 24, "neutral", [], str(segment["particle_effect"]))
                cue = segment.get("cue")
                if segment["source"] == "narration_render":
                    mux(draft, project / str(cue["audio"]["path"]), clip)
                    source_ids.extend([str(cue["audio"]["asset_id"]), str(cue["audio"]["mix_asset_id"]), str(cue["subtitle_asset_id"])])
                else:
                    _add_silence(draft, clip, float(segment["duration_seconds"]))
            if not clip.is_file():
                raise RuntimeError(f"segment render is missing: {clip}")
            actual = _media_duration(clip); clips.append(clip)
            cue = segment.get("cue")
            if cue:
                end = min(cursor + actual, cursor + float(cue["end_seconds"]))
                for subtitle_start, subtitle_end, subtitle_text in _subtitle_entries(str(cue["text"]), cursor, end):
                    srt.extend([str(len(srt) // 4 + 1), f"{_srt_time(subtitle_start)} --> {_srt_time(subtitle_end)}", subtitle_text, ""])
            source_ids.extend([str(segment["scene_id"]), str(segment["background_asset_id"])])
            output_segments.append({"unit_id": segment["unit_id"], "shot_id": segment["shot_id"], "kind": segment["kind"], "source": segment["source"], "output": clip.relative_to(project).as_posix(), "start_seconds": round(cursor, 3), "duration_seconds": actual})
            cursor += actual
        subtitle_path = episode_dir / f"{episode_id.lower()}-local-pilot-v1.srt"
        subtitle_path.write_text("\n".join(srt), encoding="utf-8")
        clean = episode_dir / f"{episode_id.lower()}-local-pilot-v1-clean.mp4"
        final = episode_dir / f"{episode_id.lower()}-local-pilot-v1.mp4"
        _concat(clips, clean); _burn_subtitles(clean, subtitle_path, final)
        source_ids = list(dict.fromkeys(source_ids))
        subtitle_asset = repository.register_asset(f"AST-SUBTITLE-JHY-EPISODE-{episode_id}-LOCAL-V1", "subtitle", subtitle_path, metadata={"title": f"{episode_id} 本地试播字幕", "provider": "local_episode_assembly"}, source_entity_ids=source_ids)
        video_asset = repository.register_asset(f"AST-VIDEO-JHY-EPISODE-{episode_id}-LOCAL-V1", "video", final, metadata={"title": f"{episode_id} 本地动态漫试播母版", "provider": "local_episode_assembly", "duration_seconds": round(cursor, 3), "subtitle_asset_id": subtitle_asset["asset_id"]}, source_entity_ids=source_ids + [subtitle_asset["asset_id"]])
        results.append({"episode_id": episode_id, "output": final.relative_to(project).as_posix(), "clean_output": clean.relative_to(project).as_posix(), "subtitle": subtitle_path.relative_to(project).as_posix(), "video_asset_id": video_asset["asset_id"], "subtitle_asset_id": subtitle_asset["asset_id"], "duration_seconds": round(cursor, 3), "segment_count": len(output_segments), "segments": output_segments, "status": "COMPLETED", "human_review": {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None}})
    manifest = {"schema_version": 1, "project_id": project.name, "status": "COMPLETED" if len(results) == 5 else "PARTIAL", "episode_count": len(results), "episodes": results, "human_review": {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None}}
    manifest_path = episode_dir / "episode-masters.json"; manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("project_dir", type=Path); parser.add_argument("--episode", action="append", default=[]); parser.add_argument("--plan-only", action="store_true"); args = parser.parse_args()
    result = build_plan(args.project_dir) if args.plan_only else assemble(args.project_dir, set(args.episode) or None)
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
