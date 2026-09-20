#!/usr/bin/env python3
"""Web-facing project creation and local TXT import for novel-anime projects."""

from __future__ import annotations

import hashlib
import re
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from scripts.novel_anime_project import build_project, utc_timestamp, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_anime_runtime import NovelAnimeRuntime
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_source_ingest import MAX_SOURCE_BYTES, ingest_source
from scripts.novel_story_bible import build_bible, bind_continuity_refs, write_bible
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, write_script_package
from scripts.novel_story_review import audit_story, write_report
from scripts.novel_visual_bible import build_visual_bible, write_visual_bible
from scripts.novel_character_designs import build_character_designs, write_character_designs
from scripts.novel_environment_assets import build_environment_assets, write_environment_assets
from scripts.novel_asset_review import build_asset_review, write_asset_review
from scripts.novel_shot_breakdown import build_shot_breakdown, write_shot_breakdown
from scripts.novel_storyboard import build_storyboard, write_storyboard
from scripts.novel_animatic import build_animatic, write_animatic
from scripts.novel_animatic_review import build_review, write_review
from scripts.novel_voice_profiles import build_voice_profiles, write_voice_profiles
from scripts.novel_audio_assets import build_audio_assets, write_audio_assets
from scripts.novel_audio_mix import build_audio_mix, write_audio_mix
from scripts.novel_dynamic_shots import build_dynamic_shots, write_dynamic_shots
from scripts.novel_edit_timelines import build_edit_timelines, write_edit_timelines
from scripts.novel_qc import build_qc_report, write_qc_report


MAX_WEB_UPLOAD_BYTES = MAX_SOURCE_BYTES + 4 * 1024 * 1024
RIGHTS_MODES = {"OWNED_OR_LICENSED", "TECHNICAL_TEST"}


class NovelWebImportError(RuntimeError):
    pass


def _identity(projects_root: Path, title: str) -> tuple[str, str]:
    seed = f"{title}|{time.time_ns()}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    project_id = f"novel-{digest[:10]}"
    ip_code = f"N{digest[:9]}".upper()
    if (projects_root / project_id).exists():
        raise NovelWebImportError("generated project id already exists; retry creation")
    return project_id, ip_code


def _safe_filename(value: str) -> str:
    name = Path(str(value or "novel.txt")).name.strip()
    if not name.lower().endswith(".txt"):
        raise NovelWebImportError("novel file must be a .txt file")
    name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "-", name).strip(".-")
    if not name:
        name = "novel.txt"
    if not name.lower().endswith(".txt"):
        name += ".txt"
    return name[:160]


def _configure_catalog(
    catalog: dict[str, Any],
    *,
    ip_code: str,
    title: str,
    author: str,
    source_name: str,
    source_sha256: str,
    rights_mode: str,
    rights_confirmed: bool,
) -> tuple[dict[str, Any], str, bool]:
    rights_mode = str(rights_mode or "").strip().upper()
    if rights_mode not in RIGHTS_MODES:
        raise NovelWebImportError("rights_mode must be OWNED_OR_LICENSED or TECHNICAL_TEST")
    formal = rights_mode == "OWNED_OR_LICENSED"
    if formal and rights_confirmed is not True:
        raise NovelWebImportError("owned/licensed import requires explicit rights confirmation")

    edition_id = f"SRC-{ip_code}-001"
    source_url = f"local://upload/{quote(catalog['project_id'], safe='')}/{quote(source_name, safe='')}"
    rights_status = "LICENSED" if formal else "UNASSESSED"
    catalog["status"] = rights_status
    catalog["rights_assessment"]["status"] = rights_status
    catalog["rights_assessment"]["publication_allowed"] = False
    catalog["rights_assessment"]["evidence"] = []
    catalog["adaptation_policy"]["publication_allowed"] = False
    if formal:
        reviewed_at = utc_timestamp()
        catalog["rights_assessment"].update({
            "basis": "User attested original authorship or explicit adaptation authorization in the local Web console. Publication remains blocked pending release review/evidence.",
            "jurisdictions": [],
            "territories": [],
            "human_review": {
                "required": True,
                "status": "APPROVED",
                "reviewed_at": reviewed_at,
                "reviewed_by": "web-user-attestation",
                "note": "Adaptation authority attested by the user; this is not independent legal verification and does not enable automatic publication.",
            },
        })
        catalog["adaptation_policy"].update({
            "script_adaptation_allowed": True,
            "allowed_transformations": ["script_adaptation", "visual_adaptation", "voice_synthesis", "video_rendering"],
        })
    else:
        catalog["rights_assessment"]["basis"] = "Local technical test only; adaptation/publication rights are not assessed."
        catalog["adaptation_policy"]["script_adaptation_allowed"] = False

    catalog["editions"] = [{
        "id": edition_id,
        "title": title,
        "edition_label": "Local Web TXT upload",
        "author": author or "未填写",
        "language": "zh-CN",
        "publication_year": None,
        "publisher": None,
        "source_url": source_url,
        "file_checksum": source_sha256,
        "rights_status": rights_status,
        "chapter_ids": [],
        "modern_contributions": [],
    }]
    return catalog, edition_id, formal


def _initialize_workspace(project_dir: Path) -> None:
    """Create the existing production-desk skeleton using the same P18-P27 builders."""
    write_bible(project_dir, build_bible(project_dir))
    bind_continuity_refs(project_dir)
    write_plan(project_dir, build_plan(project_dir))
    write_episode_planning(project_dir, build_episode_planning(project_dir))
    write_script_package(project_dir, build_script_package(project_dir))
    write_report(project_dir, audit_story(project_dir))
    write_visual_bible(project_dir, build_visual_bible(project_dir))
    write_character_designs(project_dir, build_character_designs(project_dir))
    write_environment_assets(project_dir, build_environment_assets(project_dir))
    write_asset_review(project_dir, build_asset_review(project_dir))
    write_shot_breakdown(project_dir, build_shot_breakdown(project_dir))
    write_storyboard(project_dir, build_storyboard(project_dir))
    write_animatic(project_dir, build_animatic(project_dir))
    write_review(project_dir, build_review(project_dir))
    write_voice_profiles(project_dir, build_voice_profiles(project_dir))
    write_audio_assets(project_dir, build_audio_assets(project_dir))
    write_audio_mix(project_dir, build_audio_mix(project_dir))
    write_dynamic_shots(project_dir, build_dynamic_shots(project_dir))
    write_edit_timelines(project_dir, build_edit_timelines(project_dir))
    write_qc_report(project_dir, build_qc_report(project_dir))


def create_project_from_web_upload(
    projects_root: Path,
    *,
    title: str,
    author: str,
    episode_count: int,
    rights_mode: str,
    rights_confirmed: bool,
    source_name: str,
    source_text: str,
) -> dict[str, Any]:
    projects_root = Path(projects_root).resolve()
    title = str(title or "").strip()
    author = str(author or "").strip()
    if not title:
        raise NovelWebImportError("novel title is required")
    if isinstance(episode_count, bool) or not isinstance(episode_count, int) or not 1 <= episode_count <= 999:
        raise NovelWebImportError("episode_count must be from 1 to 999")
    source_name = _safe_filename(source_name)
    if not isinstance(source_text, str) or not source_text.strip():
        raise NovelWebImportError("novel text is empty")
    source_bytes = source_text.encode("utf-8")
    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise NovelWebImportError(f"novel TXT exceeds {MAX_SOURCE_BYTES // (1024 * 1024)} MB")

    project_id, ip_code = _identity(projects_root, title)
    project_dir = (projects_root / project_id).resolve()
    if projects_root not in project_dir.parents:
        raise NovelWebImportError("project path escapes projects root")

    try:
        write_project(project_dir, build_project(project_id, ip_code, title, episode_count=episode_count))
        NovelAnimeRepository(project_dir).initialize()
        NovelAnimeRuntime(project_dir).initialize()

        catalog = build_catalog(project_id, f"IP-{ip_code}", title, target_regions=["CN"])
        catalog, edition_id, formal = _configure_catalog(
            catalog,
            ip_code=ip_code,
            title=title,
            author=author,
            source_name=source_name,
            source_sha256=hashlib.sha256(source_bytes).hexdigest(),
            rights_mode=rights_mode,
            rights_confirmed=rights_confirmed,
        )
        write_catalog(project_dir, catalog)

        temp_root = project_dir / ".videocreator" / "upload-tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        temp_path = temp_root / source_name
        try:
            temp_path.write_bytes(source_bytes)
            import_result = ingest_source(
                project_dir,
                edition_id,
                temp_path,
                authorization_confirmed=formal,
                test_only=not formal,
            )
        finally:
            temp_path.unlink(missing_ok=True)
            try:
                temp_root.rmdir()
            except OSError:
                pass

        _initialize_workspace(project_dir)
        return {
            "status": "PASS",
            "project_id": project_id,
            "directory_id": project_dir.name,
            "ip_id": f"IP-{ip_code}",
            "title": title,
            "episode_count": episode_count,
            "rights_mode": rights_mode,
            "publication_allowed": False,
            "script_adaptation_allowed": formal,
            "import": import_result,
            "full_text_stored": False,
            "next": "OPEN_STUDIO",
        }
    except Exception:
        if project_dir.is_dir():
            shutil.rmtree(project_dir, ignore_errors=True)
        raise


__all__ = [
    "MAX_WEB_UPLOAD_BYTES",
    "NovelWebImportError",
    "create_project_from_web_upload",
]
