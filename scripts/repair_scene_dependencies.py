#!/usr/bin/env python3
"""Reconcile downstream metadata after local episode scene backfill.

Existing visual designs and human reviews are retained. Only stale upstream
references and scene environment assignments are changed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.novel_anime_project import utc_timestamp
from scripts.novel_asset_review import validate_asset_review, write_asset_review
from scripts.novel_environment_assets import validate_environment_assets, write_environment_assets
from scripts.novel_episode_script import load_script_package
from scripts.novel_visual_bible import rebind_script_revision


def reconcile_after_scene_backfill(project_dir: Path) -> dict[str, Any]:
    """Preserve curated content while making new script scenes routable."""
    project = Path(project_dir).expanduser().resolve()
    scripts = load_script_package(project)
    visual = rebind_script_revision(project, scripts["revision"])

    environment_path = project / "visual-bible/environment-assets.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    existing = {item["scene_id"]: item for item in environment["scene_environment_assignments"]}
    assignments = []
    for episode in scripts["episode_scripts"]:
        for scene in episode["scenes"]:
            if not scene["location_id"]:
                continue
            previous = existing.get(scene["id"])
            if previous and previous["location_id"] == scene["location_id"]:
                assignments.append(previous)
            else:
                assignments.append({
                    "scene_id": scene["id"], "episode_id": episode["episode_id"],
                    "location_id": scene["location_id"], "location_variant_id": None,
                    "weather": "", "time_of_day": scene["time_of_day"],
                    "lighting": "", "prop_state_ids": [],
                })
    assignments_changed = assignments != environment["scene_environment_assignments"]
    if assignments_changed:
        environment["scene_environment_assignments"] = assignments
        environment["revision"] += 1
        environment["updated_at"] = utc_timestamp()
        write_environment_assets(project, validate_environment_assets(project, environment), overwrite=True)
    else:
        validate_environment_assets(project, environment)

    review_path = project / "visual-bible/asset-review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review["environment_assets_revision"] != environment["revision"] or review["visual_bible_revision"] != visual["revision"]:
        review["environment_assets_revision"] = environment["revision"]
        review["visual_bible_revision"] = visual["revision"]
        review["updated_at"] = utc_timestamp()
        write_asset_review(project, validate_asset_review(project, review), overwrite=True)
    return {
        "script_revision": scripts["revision"],
        "visual_revision": visual["revision"],
        "environment_revision": environment["revision"],
        "environment_assignments": len(assignments),
        "asset_review_revision": review["revision"],
    }
