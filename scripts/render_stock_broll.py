#!/usr/bin/env python3
"""Trim and fit locally registered rights-declared B-roll for one Shot."""

from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.modern_asset_library import load_library


class StockBrollError(ValueError):
    pass


def render_stock_broll(project: Path, *, shot_id: str, asset_path: str, duration_seconds: float) -> dict[str, Any]:
    project = Path(project).resolve()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,100}", shot_id):
        raise StockBrollError("invalid shot_id")
    duration = float(duration_seconds)
    if not math.isfinite(duration) or not 1 <= duration <= 30:
        raise StockBrollError("B-roll duration must be 1-30 seconds")
    asset = next((item for item in load_library(project)["assets"] if item["kind"] == "stock" and item["path"] == asset_path), None)
    if not asset or asset.get("license_note") not in {"owned", "CC0", "licensed"}:
        raise StockBrollError("select registered B-roll with a rights declaration")
    source = (project / asset["path"]).resolve()
    if not source.is_file() or project not in source.parents:
        raise StockBrollError("registered B-roll file is missing")
    output = project / "rendering/stock-broll" / f"{shot_id}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-vf", "scale=540:960:force_original_aspect_ratio=increase,crop=540:960,fps=24,tpad=stop_mode=clone:stop_duration=30",
        "-t", f"{duration:.3f}", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        output.unlink(missing_ok=True)
        raise StockBrollError(f"local B-roll render failed: {result.stderr[-800:]}")
    return {"status": "READY", "renderer": "stock_broll_library", "shot_id": shot_id, "asset_path": asset_path, "license_note": asset["license_note"], "output": output.relative_to(project).as_posix(), "duration_seconds": duration, "width": 540, "height": 960, "fps": 24}
