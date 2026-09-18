#!/usr/bin/env python3
"""Create or inspect the metadata-only ArcReel mirror for a novel project."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.workspaces import ArcReelWorkspace
from scripts.novel_anime_project import MANIFEST_NAME, load_project
from scripts.novel_shot_breakdown import load_shot_breakdown


def mirror_project(project_dir: Path, base_url: str, api_key: str | None = None, sync_source: bool = False) -> dict[str, object]:
    project = load_project(project_dir / MANIFEST_NAME)
    breakdown = load_shot_breakdown(project_dir)
    shots = [shot["id"] for scene in breakdown["scene_breakdowns"] for shot in scene["shots"]]
    style_path = project_dir / "visual-bible" / "style.json"
    style_data = json.loads(style_path.read_text(encoding="utf-8")) if style_path.is_file() else {}
    style_block = style_data.get("style", {}) if isinstance(style_data, dict) else {}
    style = str(style_block.get("title") or style_block.get("art_direction") or "低成本国风小说动态漫")
    client = ArcReelWorkspace(base_url, api_key=api_key, timeout_seconds=10)
    mirror = client.ensure_project(name=project["project_id"], title=f"{project['title']}·国风动态漫", style=style, generation_mode="storyboard", aspect_ratio="9:16")
    source_result = None
    if sync_source:
        source_files = sorted((project_dir / "sources" / "input").glob("*.txt"))
        if len(source_files) != 1:
            raise ValueError(f"expected exactly one source .txt file, found {len(source_files)}")
        source_path = source_files[0]
        source_result = client.put_source_text(project["project_id"], source_path.name, source_path.read_text(encoding="utf-8"))
    return {
        "status": mirror["status"],
        "project_id": project["project_id"],
        "episode_ids": [episode["id"] for episode in project["episodes"]],
        "shot_ids": shots,
        "shot_count": len(shots),
        "source_sync": source_result,
        "uploads_performed": source_result is not None,
        "generation_started": False,
        "workflow": client.workflow_status(project["project_id"]),
        "tasks": client.list_tasks(project["project_id"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:1241")
    parser.add_argument("--api-key")
    parser.add_argument("--sync-source", action="store_true", help="copy the single local source text into the local ArcReel mirror without generating an overview")
    args = parser.parse_args()
    print(json.dumps(mirror_project(args.project_dir.resolve(), args.base_url, args.api_key, sync_source=args.sync_source), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
