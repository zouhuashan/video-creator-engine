#!/usr/bin/env python3
"""Render approved local final previews for shots covered by one character Rig."""

from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.mux_timeline_shot import mux
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.render_character_rig_preview import render


def _expression(emotion: str) -> str:
    if emotion in {"向往", "轻松", "喜悦"}:
        return "soft_smile"
    if emotion in {"疑惑", "为难", "担忧", "克制"}:
        return "concerned"
    if emotion in {"惊异", "惊讶"}:
        return "surprised"
    return "neutral"


def _scene_id(shot_id: str) -> str:
    return shot_id.removeprefix("SHOT-").rsplit("-", 1)[0]


def _background_for_shot(project: Path, shot_id: str) -> tuple[Path, str]:
    """Resolve a scene-specific location plate, with Kunlun as legacy fallback."""
    scene_id = _scene_id(shot_id)
    manifest_path = project / "lookdev" / "generation-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for asset in reversed(manifest.get("assets", [])):
            if not str(asset.get("type", "")).startswith("environment_") or scene_id not in asset.get("references", []):
                continue
            path = project / str(asset.get("path", ""))
            if path.is_file():
                return path, str(asset["asset_id"])
    fallback = project / "assets" / "locations" / "LOCN-JHY-KUNLUN" / "kunlun-yaochi-night-v1.png"
    if not fallback.is_file():
        raise ValueError(f"no registered background is available for {scene_id}")
    return fallback, "AST-LOC-JHY-KUNLUN-NIGHT"


def _particle_effect(background_asset_id: str) -> str:
    quiet_plates = {
        "AST-LOC-JHY-NUANGE-SNOW-NIGHT",
        "AST-LOC-JHY-MAGUDONG-SNOW-NIGHT",
        "AST-LOC-JHY-BATTLEFIELD-AFTERMATH-DAY",
    }
    return "none" if background_asset_id in quiet_plates else "petals"


def render_batch(project: Path, shot_ids: list[str], rig_id: str) -> dict[str, object]:
    project = project.expanduser().resolve()
    rigs = json.loads((project / "visual-bible" / "character-rigs.json").read_text(encoding="utf-8")).get("rigs", [])
    rig = next((item for item in rigs if item.get("id") == rig_id), None)
    if not rig:
        raise ValueError("approved Rig is missing")
    timeline = json.loads((project / "dynamic" / "mouth-cues.json").read_text(encoding="utf-8")).get("timeline", [])
    by_shot = {str(item["shot_id"]): item for item in timeline}
    layers = [project / str(layer["path"]) for layer in rig.get("layers", []) if layer.get("name") in {"head", "torso", "lower"}]
    repository = NovelAnimeRepository(project); results = []
    for shot_id in shot_ids:
        cue = by_shot.get(shot_id)
        if not cue:
            continue
        seconds = min(8.0, max(2.0, float(cue.get("end_seconds") or 4.0)))
        background, background_asset_id = _background_for_shot(project, shot_id)
        stem = shot_id.lower(); draft = project / "lookdev" / "batch" / f"{stem}-draft.mp4"; final = project / "renders" / "batch" / f"{stem}-final.mp4"
        video, _ = render(project, background, layers, draft, seconds, 24, _expression(str(cue.get("emotion") or "")), cue.get("mouth_cues", []), _particle_effect(background_asset_id))
        mux(video, project / str(cue["audio"]["path"]), final)
        scene_id = _scene_id(shot_id)
        source_ids = [str(layer["asset_id"]) for layer in rig["layers"]] + [str(cue["audio"]["asset_id"]), str(cue["audio"]["mix_asset_id"]), str(cue["subtitle_asset_id"]), background_asset_id, scene_id]
        asset = repository.register_asset(f"AST-VIDEO-JHY-BATCH-{shot_id.replace('-', '')}", "video", final, metadata={"title": f"批量最终镜头 · {shot_id}", "provider": "local_timeline_final", "rig_id": rig_id, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, source_entity_ids=source_ids)
        results.append({"shot_id": shot_id, "rig_id": rig_id, "background_asset_id": background_asset_id, "output": final.relative_to(project).as_posix(), "asset_id": asset["asset_id"], "version": asset["version"], "duration_seconds": seconds})
    manifest = project / "dynamic" / "final-batch.json"
    existing: dict[str, object] = {}
    if manifest.is_file():
        try:
            existing = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    merged = {str(item.get("shot_id")): item for item in existing.get("results", []) if isinstance(item, dict)}
    merged.update({str(item["shot_id"]): item for item in results})
    all_results = sorted(merged.values(), key=lambda item: str(item.get("shot_id", "")))
    rig_ids = {str(item.get("rig_id")) for item in all_results if item.get("rig_id")}
    if existing.get("rig_id"):
        rig_ids.add(str(existing["rig_id"]))
    rig_ids.add(rig_id)
    result = {"schema_version": 1, "project_id": project.name, "rig_id": rig_id, "rig_ids": sorted(rig_ids), "status": "COMPLETED", "count": len(all_results), "results": all_results, "human_review": {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None}}
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
