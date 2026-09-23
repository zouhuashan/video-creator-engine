#!/usr/bin/env python3
"""Web-facing project creation and local TXT import for novel-anime projects."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from scripts.novel_anime_project import MANIFEST_NAME, build_project, load_project, utc_timestamp, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_anime_runtime import NovelAnimeRuntime
from scripts.novel_source_catalog import build_catalog, load_catalog, write_catalog
from scripts.novel_source_ingest import MAX_SOURCE_BYTES, ingest_source
from scripts.novel_character_candidates import (
    build_character_candidates,
    load_character_candidates,
    write_character_candidates,
)
from scripts.novel_story_bible import build_bible, bind_continuity_refs, load_bible, write_bible
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, write_script_package
from scripts.novel_scene_backfill import NovelSceneBackfillError, backfill_episode_scenes
from scripts.novel_story_review import audit_story, write_report
from scripts.novel_visual_bible import NovelVisualBibleError, build_visual_bible, rebind_script_revision, write_visual_bible
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


MAX_WEB_UPLOAD_BYTES = MAX_SOURCE_BYTES * 2 + 1024 * 1024
RIGHTS_MODES = {"OWNED_OR_LICENSED", "TECHNICAL_TEST"}
MAX_AUTO_STORY_CHARACTERS = 12


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


def _import_payloads(project_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    result: list[tuple[Path, dict[str, Any]]] = []
    imports_root = Path(project_dir) / "sources" / "imports"
    if not imports_root.is_dir():
        return result
    for path in sorted(imports_root.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            result.append((path, payload))
    return result


def _matching_existing_project(projects_root: Path, title: str, source_sha256: str) -> tuple[Path, Path, dict[str, Any]] | None:
    """Find an identical prior Web import so retries are idempotent.

    When an old bug already produced duplicates, prefer the copy that has
    recoverable character extraction; otherwise prefer the newest project.
    """
    if not projects_root.is_dir():
        return None
    wanted_title = str(title or "").strip()
    wanted_sha = str(source_sha256 or "").strip().lower()
    matches: list[tuple[int, str, Path, Path, dict[str, Any]]] = []
    for manifest_path in projects_root.glob(f"*/{MANIFEST_NAME}"):
        try:
            project = load_project(manifest_path)
        except Exception:
            continue
        if str(project.get("title") or "").strip() != wanted_title:
            continue
        for import_path, payload in _import_payloads(manifest_path.parent):
            if str(payload.get("source_sha256") or "").strip().lower() != wanted_sha:
                continue
            extraction = payload.get("extraction") if isinstance(payload, dict) else None
            extracted = extraction.get("characters") if isinstance(extraction, dict) else None
            candidate_ready = 0
            try:
                candidate_payload = load_character_candidates(manifest_path.parent)
                candidate_ready = int(bool(isinstance(candidate_payload, dict) and candidate_payload.get("characters")))
            except Exception:
                candidate_ready = 0
            recoverable = max(candidate_ready, int(bool(isinstance(extracted, list) and extracted)))
            created = str(project.get("created_at") or project.get("updated_at") or "")
            matches.append((recoverable, created, manifest_path.parent, import_path, payload))
    if not matches:
        return None
    matches.sort(key=lambda item: (item[0], item[1], item[2].name), reverse=True)
    _recoverable, _created, project_dir, import_path, payload = matches[0]
    return project_dir, import_path, payload


def _chapter_refs_for_candidate(project_dir: Path, candidate: dict[str, Any], source_sha256: str = "") -> list[str]:
    refs = [
        str(item.get("chapter_id") or "").strip()
        for item in candidate.get("mentions", [])
        if isinstance(item, dict) and str(item.get("chapter_id") or "").strip()
    ]
    if refs:
        return list(dict.fromkeys(refs))[:8]

    wanted_sha = str(source_sha256 or "").strip().lower()
    for _path, payload in _import_payloads(project_dir):
        if wanted_sha and str(payload.get("source_sha256") or "").strip().lower() != wanted_sha:
            continue
        refs = [
            str(item.get("chapter_id") or "").strip()
            for item in payload.get("chapters", [])
            if isinstance(item, dict) and str(item.get("chapter_id") or "").strip()
        ]
        if refs:
            return list(dict.fromkeys(refs))[:8]
    return []


def _candidate_story_characters(project_dir: Path, candidate_payload: dict[str, Any]) -> list[dict[str, Any]]:
    characters = candidate_payload.get("characters")
    if not isinstance(characters, list):
        return []

    seeded: list[dict[str, Any]] = []
    source_sha = str(candidate_payload.get("source_sha256") or "")
    for index, item in enumerate(characters[:MAX_AUTO_STORY_CHARACTERS]):
        if not isinstance(item, dict):
            continue
        character_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not character_id or not name:
            continue
        source_refs = _chapter_refs_for_candidate(project_dir, item, source_sha)
        if not source_refs:
            continue
        mentions = int(item.get("total_mentions") or 0)
        seeded.append({
            "id": character_id,
            "name": name,
            "aliases": [str(value).strip() for value in item.get("aliases", []) if str(value).strip()],
            "role": "主角候选（自动抽取）" if index == 0 else "主要角色候选（自动抽取）",
            "description": f"由导入底本自动抽取；当前共识别 {mentions} 次出场或提及。身份与视觉细节等待人工定妆审核。",
            "goals": [],
            "traits": [],
            "baseline_state": {
                "location_id": None,
                "costume_id": None,
                "carried_prop_ids": [],
                "injuries": [],
                "knowledge": [],
                "emotional_state": "",
            },
            "provenance": {
                "kind": "SOURCE",
                "source_refs": source_refs,
                "note": "由本地小说导入自动抽取，正文未落库；角色信息需人工复核。",
            },
            "human_review": {
                "required": True,
                "status": "PENDING",
                "reviewed_at": None,
                "reviewed_by": None,
                "note": "",
            },
        })
    return seeded


def promote_character_candidates(project_dir: Path, candidate_payload: dict[str, Any]) -> dict[str, Any]:
    """Promote persisted extraction candidates into Story/Character Bible data.

    This is safe to run repeatedly.  Existing non-empty Story Bible characters
    win; automatic promotion only fills projects that previously had none.
    """
    project_dir = Path(project_dir).resolve()
    try:
        bible = load_bible(project_dir)
        bible_exists = True
    except Exception:
        bible = build_bible(project_dir)
        bible_exists = False

    current = bible.get("characters") if isinstance(bible, dict) else None
    if isinstance(current, list) and current:
        return {
            "status": "READY",
            "character_count": len(current),
            "promoted": False,
            "source": "story-bible",
        }

    characters = _candidate_story_characters(project_dir, candidate_payload)
    if not characters:
        return {
            "status": "BLOCKED",
            "character_count": 0,
            "promoted": False,
            "source": "character-candidates-empty",
        }

    bible["characters"] = characters
    if bible_exists:
        # This repairs data that should have been present in the same import;
        # keep the existing revision so already-built downstream packages do
        # not become stale solely because of the P31 persistence bug.
        bible["updated_at"] = utc_timestamp()
    write_bible(project_dir, bible, overwrite=bible_exists)
    bind_continuity_refs(project_dir)

    # Old Web imports may already have an empty Character Designs file.  Once
    # Story Bible is repaired, rebuild that derived package so Image Studio
    # sees the real project character immediately.
    try:
        write_character_designs(project_dir, build_character_designs(project_dir), overwrite=True)
    except Exception:
        # During a brand-new import the Visual Bible does not exist yet; the
        # normal workspace initializer will create Character Designs later.
        pass

    return {
        "status": "READY",
        "character_count": len(characters),
        "promoted": True,
        "source": "local-character-candidates",
        "characters": [{"id": item["id"], "name": item["name"], "role": item["role"]} for item in characters],
    }


def recover_project_characters(project_dir: Path) -> dict[str, Any]:
    """Recover an old Web-import project without asking for the TXT again."""
    project_dir = Path(project_dir).resolve()
    try:
        existing = load_bible(project_dir)
        existing_characters = existing.get("characters") if isinstance(existing, dict) else []
        if isinstance(existing_characters, list) and existing_characters:
            return {
                "status": "READY",
                "character_count": len(existing_characters),
                "promoted": False,
                "source": "story-bible",
            }
    except Exception:
        pass

    try:
        candidates = load_character_candidates(project_dir)
    except Exception:
        candidates = None
    if isinstance(candidates, dict) and candidates.get("characters"):
        return promote_character_candidates(project_dir, candidates)

    # Older imports persist extraction metadata even though they intentionally
    # discard the original prose.  Rebuild the candidate file from that
    # metadata, then promote it into Story Bible.
    for _path, import_payload in _import_payloads(project_dir):
        extraction = import_payload.get("extraction") if isinstance(import_payload, dict) else None
        characters = extraction.get("characters") if isinstance(extraction, dict) else None
        if not isinstance(characters, list) or not characters:
            continue
        candidate_payload = build_character_candidates(
            project_dir,
            source_file_name=str(import_payload.get("source_file_name") or "novel.txt"),
            source_sha256=str(import_payload.get("source_sha256") or ""),
            provider=str(extraction.get("provider") or "local_lexicon"),
            characters=characters,
        )
        write_character_candidates(project_dir, candidate_payload)
        return promote_character_candidates(project_dir, candidate_payload)

    # P31 previously allowed duplicate projects for the same exact TXT.  If
    # this copy lost its character extraction but a sibling duplicate retained
    # it, migrate only the extracted character names/counts into the current
    # project's IDs and provenance.  The original prose is still never stored.
    try:
        current_manifest = load_project(project_dir / MANIFEST_NAME)
        current_title = str(current_manifest.get("title") or "")
        current_ip = str(current_manifest.get("ip", {}).get("id") or "").removeprefix("IP-")
    except Exception:
        current_manifest = {}
        current_title = ""
        current_ip = ""

    current_imports = _import_payloads(project_dir)
    current_by_sha = {
        str(payload.get("source_sha256") or "").strip().lower(): payload
        for _path, payload in current_imports
        if str(payload.get("source_sha256") or "").strip()
    }
    if current_title and current_ip and current_by_sha:
        for sibling_manifest in project_dir.parent.glob(f"*/{MANIFEST_NAME}"):
            sibling = sibling_manifest.parent.resolve()
            if sibling == project_dir:
                continue
            try:
                sibling_project = load_project(sibling_manifest)
            except Exception:
                continue
            if str(sibling_project.get("title") or "") != current_title:
                continue

            sibling_characters: list[dict[str, Any]] = []
            sibling_sha = ""
            try:
                sibling_candidates = load_character_candidates(sibling)
            except Exception:
                sibling_candidates = None
            if isinstance(sibling_candidates, dict):
                candidate_sha = str(sibling_candidates.get("source_sha256") or "").strip().lower()
                if candidate_sha in current_by_sha and isinstance(sibling_candidates.get("characters"), list):
                    sibling_sha = candidate_sha
                    sibling_characters = [item for item in sibling_candidates["characters"] if isinstance(item, dict)]

            if not sibling_characters:
                for _path, sibling_import in _import_payloads(sibling):
                    candidate_sha = str(sibling_import.get("source_sha256") or "").strip().lower()
                    if candidate_sha not in current_by_sha:
                        continue
                    extraction = sibling_import.get("extraction") if isinstance(sibling_import, dict) else None
                    extracted = extraction.get("characters") if isinstance(extraction, dict) else None
                    if isinstance(extracted, list) and extracted:
                        sibling_sha = candidate_sha
                        sibling_characters = [item for item in extracted if isinstance(item, dict)]
                        break

            if not sibling_characters or sibling_sha not in current_by_sha:
                continue

            remapped = []
            for index, item in enumerate(sibling_characters[:MAX_AUTO_STORY_CHARACTERS], start=1):
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                remapped.append({
                    "id": f"CHR-{current_ip}-AUTO-{index:03d}",
                    "name": name,
                    "aliases": [str(value) for value in item.get("aliases", []) if str(value).strip()],
                    "mentions": [],
                    "total_mentions": int(item.get("total_mentions") or 0),
                })
            if not remapped:
                continue
            own_import = current_by_sha[sibling_sha]
            migrated = build_character_candidates(
                project_dir,
                source_file_name=str(own_import.get("source_file_name") or "novel.txt"),
                source_sha256=sibling_sha,
                provider="duplicate-project-character-recovery",
                characters=remapped,
            )
            write_character_candidates(project_dir, migrated)
            result = promote_character_candidates(project_dir, migrated)
            result["source"] = "duplicate-project-character-recovery"
            result["recovered_from_project_id"] = sibling.name
            return result

    return {
        "status": "BLOCKED",
        "character_count": 0,
        "promoted": False,
        "source": "no-persisted-character-extraction",
        "detail": "当前项目及同底本重复项目都没有可恢复的角色抽取元数据；新导入已改为在项目创建阶段强制完成角色抽取。",
    }


def _initialize_workspace(
    project_dir: Path,
    candidate_payload: dict[str, Any],
    *,
    source_text: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Create the production desk with extracted characters and source scene seeds connected."""
    bible = build_bible(project_dir)
    characters = _candidate_story_characters(project_dir, candidate_payload)
    if not characters:
        raise NovelWebImportError("novel import did not produce stable character candidates")
    bible["characters"] = characters
    write_bible(project_dir, bible)
    bind_continuity_refs(project_dir)
    write_plan(project_dir, build_plan(project_dir))
    write_episode_planning(project_dir, build_episode_planning(project_dir))
    write_script_package(project_dir, build_script_package(project_dir))
    scene_backfill = backfill_episode_scenes(project_dir, source_text, source_sha256=source_sha256)
    write_report(project_dir, audit_story(project_dir))
    write_visual_bible(project_dir, build_visual_bible(project_dir))
    write_character_designs(project_dir, build_character_designs(project_dir))
    write_environment_assets(project_dir, build_environment_assets(project_dir))
    write_asset_review(project_dir, build_asset_review(project_dir))
    shot_breakdown = build_shot_breakdown(project_dir)
    write_shot_breakdown(project_dir, shot_breakdown)
    scene_backfill = {
        **scene_backfill,
        "shot_count": sum(len(item.get("shots") or []) for item in shot_breakdown.get("scene_breakdowns", [])),
    }
    write_storyboard(project_dir, build_storyboard(project_dir))
    write_animatic(project_dir, build_animatic(project_dir))
    write_review(project_dir, build_review(project_dir))
    write_voice_profiles(project_dir, build_voice_profiles(project_dir))
    write_audio_assets(project_dir, build_audio_assets(project_dir))
    write_audio_mix(project_dir, build_audio_mix(project_dir))
    write_dynamic_shots(project_dir, build_dynamic_shots(project_dir))
    write_edit_timelines(project_dir, build_edit_timelines(project_dir))
    write_qc_report(project_dir, build_qc_report(project_dir))
    return scene_backfill


def _sync_scene_dependent_visual_revision(project_dir: Path, script_revision: int) -> None:
    """Keep existing visual work while acknowledging a repaired script revision."""
    try:
        rebind_script_revision(project_dir, int(script_revision))
    except (NovelVisualBibleError, OSError, json.JSONDecodeError):
        write_visual_bible(project_dir, build_visual_bible(project_dir), overwrite=True)


def _existing_import_result(
    project_dir: Path,
    import_path: Path,
    import_payload: dict[str, Any],
    *,
    requested_rights_mode: str,
    scene_backfill: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project = load_project(project_dir / MANIFEST_NAME)
    try:
        catalog = load_catalog(project_dir / "sources" / "source-catalog.json")
    except Exception:
        catalog = {}
    recovery = recover_project_characters(project_dir)
    extraction = import_payload.get("extraction") if isinstance(import_payload, dict) else {}
    characters = extraction.get("characters") if isinstance(extraction, dict) else []
    import_result = {
        "import_id": str(import_payload.get("import_id") or ""),
        "output": import_path.relative_to(project_dir).as_posix(),
        "chapter_count": len(import_payload.get("chapters", [])) if isinstance(import_payload.get("chapters"), list) else 0,
        "character_candidates": len(characters) if isinstance(characters, list) else 0,
        "full_text_stored": False,
        "test_only": bool(import_payload.get("test_only")),
    }
    adaptation = catalog.get("adaptation_policy") if isinstance(catalog, dict) else {}
    rights = catalog.get("rights_assessment") if isinstance(catalog, dict) else {}
    return {
        "status": "PASS",
        "reused_existing": True,
        "project_id": str(project.get("project_id") or project_dir.name),
        "directory_id": project_dir.name,
        "ip_id": str(project.get("ip", {}).get("id") or ""),
        "title": str(project.get("title") or project_dir.name),
        "episode_count": len(project.get("episodes", [])),
        "rights_mode": requested_rights_mode,
        "publication_allowed": bool(rights.get("publication_allowed")) if isinstance(rights, dict) else False,
        "script_adaptation_allowed": bool(adaptation.get("script_adaptation_allowed")) if isinstance(adaptation, dict) else False,
        "import": import_result,
        "character_count": int(recovery.get("character_count") or 0),
        "characters": recovery.get("characters", []),
        "character_recovery": recovery,
        "scene_backfill": scene_backfill or {"status": "NOT_RUN"},
        "full_text_stored": False,
        "next": "OPEN_STUDIO",
    }


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
    rights_mode = str(rights_mode or "").strip().upper()
    if not title:
        raise NovelWebImportError("novel title is required")
    if isinstance(episode_count, bool) or not isinstance(episode_count, int) or not 1 <= episode_count <= 999:
        raise NovelWebImportError("episode_count must be from 1 to 999")
    if rights_mode not in RIGHTS_MODES:
        raise NovelWebImportError("rights_mode must be OWNED_OR_LICENSED or TECHNICAL_TEST")
    if rights_mode == "OWNED_OR_LICENSED" and rights_confirmed is not True:
        raise NovelWebImportError("owned/licensed import requires explicit rights confirmation")
    source_name = _safe_filename(source_name)
    if not isinstance(source_text, str) or not source_text.strip():
        raise NovelWebImportError("novel text is empty")
    source_bytes = source_text.encode("utf-8")
    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise NovelWebImportError(f"novel TXT exceeds {MAX_SOURCE_BYTES // (1024 * 1024)} MB")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()

    # Browser retries/double-clicks and re-importing the same TXT must not
    # create a second project.  Reuse the existing project and repair its
    # character chain from persisted extraction metadata when possible.
    existing = _matching_existing_project(projects_root, title, source_sha256)
    if existing is not None:
        project_dir = existing[0]
        try:
            scene_backfill = backfill_episode_scenes(project_dir, source_text, source_sha256=source_sha256)
            if scene_backfill.get("status") == "READY":
                _sync_scene_dependent_visual_revision(project_dir, int(scene_backfill["script_revision"]))
                write_report(project_dir, audit_story(project_dir), overwrite=True)
            rebuilt_shots = build_shot_breakdown(project_dir)
            write_shot_breakdown(project_dir, rebuilt_shots, overwrite=True)
            scene_backfill = {
                **scene_backfill,
                "shot_count": sum(len(item.get("shots") or []) for item in rebuilt_shots.get("scene_breakdowns", [])),
                "reused_existing_project": True,
            }
        except (NovelSceneBackfillError, ValueError, OSError, json.JSONDecodeError) as error:
            raise NovelWebImportError(f"existing project scene backfill failed: {error}") from error
        return _existing_import_result(
            project_dir,
            existing[1],
            existing[2],
            requested_rights_mode=rights_mode,
            scene_backfill=scene_backfill,
        )

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
            source_sha256=source_sha256,
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

        import_payload_path = project_dir / str(import_result["output"])
        import_payload = json.loads(import_payload_path.read_text(encoding="utf-8"))
        extraction = import_payload.get("extraction") if isinstance(import_payload, dict) else {}
        characters = extraction.get("characters") if isinstance(extraction, dict) else []
        candidate_payload = build_character_candidates(
            project_dir,
            source_file_name=source_name,
            source_sha256=source_sha256,
            provider=str(extraction.get("provider") or "local_lexicon"),
            characters=characters if isinstance(characters, list) else [],
        )
        if not candidate_payload["characters"]:
            raise NovelWebImportError("novel import did not identify any stable character; project creation was rolled back")
        write_character_candidates(project_dir, candidate_payload)

        scene_backfill = _initialize_workspace(
            project_dir,
            candidate_payload,
            source_text=source_text,
            source_sha256=source_sha256,
        )
        story_characters = _candidate_story_characters(project_dir, candidate_payload)
        return {
            "status": "PASS",
            "reused_existing": False,
            "project_id": project_id,
            "directory_id": project_dir.name,
            "ip_id": f"IP-{ip_code}",
            "title": title,
            "episode_count": episode_count,
            "rights_mode": rights_mode,
            "publication_allowed": False,
            "script_adaptation_allowed": formal,
            "import": import_result,
            "character_count": len(story_characters),
            "characters": [{"id": item["id"], "name": item["name"], "role": item["role"]} for item in story_characters],
            "scene_backfill": scene_backfill,
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
    "promote_character_candidates",
    "recover_project_characters",
]
