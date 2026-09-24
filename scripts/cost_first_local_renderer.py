#!/usr/bin/env python3
"""Execute P36 local routes without any remote/billable provider."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Sequence

from adapters.video_generation import (
    LocalMicroMotionVideo,
    LocalScenePlateVideo,
    LocalTwoCutVideo,
    VideoGenerationRequest,
)
from adapters.video_generation.local_vfx_compositor import apply_recipe
from scripts.cost_first_hybrid_router import CostFirstRoutingError, load_plan


OUTPUT_DIR = Path("rendering/local-previews")


class CostFirstLocalRenderError(RuntimeError):
    pass


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-._") or "shot"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def render_local_shot(
    project: Path,
    shot_id: str,
    image_paths: Sequence[Path | str],
    *,
    ffmpeg: str = "ffmpeg",
) -> dict[str, Any]:
    project = Path(project).resolve()
    shot_id = str(shot_id or "").strip()
    if not shot_id:
        raise CostFirstLocalRenderError("shot_id is required")
    try:
        plan = load_plan(project)
    except CostFirstRoutingError as error:
        raise CostFirstLocalRenderError(str(error)) from error
    route = next((item for item in plan.get("routes", []) if item.get("shot_id") == shot_id), None)
    if route is None:
        raise CostFirstLocalRenderError("unknown shot_id")
    route_name = str(route.get("route") or "")
    providers = {
        "LOCAL_SCENE_PLATE": LocalScenePlateVideo,
        "LOCAL_MICRO_MOTION": LocalMicroMotionVideo,
        "LOCAL_TWO_CUT": LocalTwoCutVideo,
    }
    provider_type = providers.get(route_name)
    if provider_type is None:
        raise CostFirstLocalRenderError("H3 candidates cannot be rendered by the local preview endpoint")

    images = tuple(Path(path).expanduser().resolve() for path in image_paths)
    expected = int(route.get("required_new_stills") or 0)
    if expected not in {1, 2} or len(images) != expected:
        raise CostFirstLocalRenderError(f"{route_name} requires exactly {expected} image(s)")
    if any(not path.is_file() for path in images):
        raise CostFirstLocalRenderError("every local preview image must exist")

    output_dir = project / OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{_safe(shot_id)}-{route_name.lower()}.mp4"
    fps = int((plan.get("policy") or {}).get("default_local_fps") or 24)
    width = int((plan.get("policy") or {}).get("local_preview_width") or 720)
    height = int((plan.get("policy") or {}).get("local_preview_height") or 1280)
    request = VideoGenerationRequest(
        image_paths=images,
        output_path=output.with_name(output.stem + "-base.mp4") if (route.get("vfx_recipe") or {}).get("recipe", {}).get("layers") else output,
        shot_duration_seconds=float(route["duration_seconds"]),
        fps=fps,
        width=width,
        height=height,
    )
    try:
        result = provider_type(ffmpeg=ffmpeg).generate(request)
        vfx_metadata = route.get("vfx_recipe") or None
        if vfx_metadata and (vfx_metadata.get("recipe") or {}).get("layers"):
            apply_recipe(
                result.output_path,
                output,
                vfx_metadata["recipe"],
                width=width,
                height=height,
                fps=fps,
                duration_seconds=float(route["duration_seconds"]),
                ffmpeg=ffmpeg,
            )
            result.output_path.unlink(missing_ok=True)
    except Exception as error:
        request.output_path.unlink(missing_ok=True)
        raise CostFirstLocalRenderError(str(error)) from error

    relative = output.relative_to(project).as_posix()
    metadata = {
        "schema_version": 1,
        "status": "READY",
        "shot_id": shot_id,
        "route": route_name,
        "provider": result.provider,
        "remote_generation": False,
        "billable": False,
        "duration_seconds": result.duration_seconds,
        "timing_source": str(route.get("timing_source") or "SHOT_BREAKDOWN"),
        "image_count": len(images),
        "source_images": [
            path.relative_to(project).as_posix() if project in path.parents else str(path)
            for path in images
        ],
        "output": relative,
        "media_url": f"/media/{project.name}/{relative}",
        "created_at": _now(),
        "vfx_recipe": {
            "provider": vfx_metadata.get("provider"),
            "summary": (vfx_metadata.get("recipe") or {}).get("summary"),
            "layer_types": [layer.get("type") for layer in (vfx_metadata.get("recipe") or {}).get("layers", [])],
            "codex_usage_confirmed": bool(vfx_metadata.get("codex_usage_confirmed")),
            "images_uploaded": False,
        } if vfx_metadata else None,
    }
    _atomic_json(output.with_suffix(".json"), metadata)
    route["local_preview"] = metadata
    plan["updated_at"] = _now()
    _atomic_json(project / Path("rendering/cost-first-plan.json"), plan)
    return metadata


__all__ = ["CostFirstLocalRenderError", "render_local_shot"]
