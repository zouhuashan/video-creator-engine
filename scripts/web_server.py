#!/usr/bin/env python3
"""Local web console for the VideoCreator Engine.

The server intentionally stays dependency-free.  It exposes project metadata,
local media previews, and an explicit video-generation action while reusing the
same Provider adapters as the CLI.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import time
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
PROJECTS_ROOT = ROOT / "projects"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.video_generation import (  # noqa: E402
    LocalKenBurnsVideo,
    MiniMaxH3Video,
    OpenAISoraVideo,
    RunwayImageToVideo,
    VideoGenerationError,
    VideoGenerationRequest,
    WanImageToVideo,
    normalize_image_paths,
)
from adapters.workspaces import ArcReelError, ArcReelWorkspace  # noqa: E402
from scripts.local_storyboard_pipeline import LocalStoryboardError, run_local_storyboard  # noqa: E402
from scripts.render_local_motion_test import render as render_local_motion_test  # noqa: E402
from scripts.render_character_rig_preview import render as render_character_rig_preview  # noqa: E402
from scripts.build_character_rig import validate_rig  # noqa: E402
from scripts.godot_rig_readiness import GodotRigReadinessError, summarize_project as godot_rig_readiness_summary  # noqa: E402
from scripts.rig_v2_segment import RigV2SegmentError, segment_layers as segment_rig_v2_layers  # noqa: E402
from scripts.rig_v2_auto_draft import RigV2AutoDraftError, propose_upper_body as propose_rig_v2_upper_body  # noqa: E402
from scripts.render_godot_25d_preview import Godot25DPreviewError, render_preview as render_godot_25d_preview  # noqa: E402
from scripts.mux_timeline_shot import mux as mux_timeline_shot  # noqa: E402
from scripts.batch_render_final_shots import _background_for_shot, _particle_effect, render_batch as render_final_shot_batch  # noqa: E402
from scripts.novel_anime_project import MANIFEST_NAME as NOVEL_ANIME_MANIFEST, NovelAnimeProjectError, load_project as load_novel_anime_project  # noqa: E402
from scripts.novel_anime_repository import NovelAnimeRepository, NovelAnimeRepositoryError, repository_stats  # noqa: E402
from scripts.novel_anime_runtime import NovelAnimeRuntime, NovelAnimeRuntimeError, runtime_stats  # noqa: E402
from scripts.novel_source_catalog import CATALOG_RELATIVE_PATH, NovelSourceCatalogError, load_catalog  # noqa: E402
from scripts.novel_character_candidates import NovelCharacterCandidateError, build_character_candidates, load_character_candidates, summary as character_candidate_summary, write_character_candidates  # noqa: E402
from scripts.novel_source_ingest import NovelSourceIngestError, extract_character_candidates_from_text  # noqa: E402
from scripts.novel_story_bible import NovelStoryBibleError, continuity_input, load_bible, summary as story_bible_summary  # noqa: E402
from scripts.novel_series_plan import NovelSeriesPlanError, load_plan as load_series_plan, summary as series_plan_summary  # noqa: E402
from scripts.novel_episode_planning import NovelEpisodePlanningError, load_episode_planning, summary as episode_planning_summary  # noqa: E402
from scripts.novel_episode_script import NovelEpisodeScriptError, load_script_package, summary as episode_script_summary  # noqa: E402
from scripts.novel_story_review import NovelStoryReviewError, load_report as load_story_review, summary as story_review_summary  # noqa: E402
from scripts.novel_visual_bible import NovelVisualBibleError, load_visual_bible, summary as visual_bible_summary  # noqa: E402
from scripts.novel_character_designs import NovelCharacterDesignError, load_character_designs, summary as character_design_summary  # noqa: E402
from scripts.novel_environment_assets import NovelEnvironmentAssetError, load_environment_assets, summary as environment_asset_summary  # noqa: E402
from scripts.novel_asset_review import NovelAssetReviewError, load_asset_review, summary as asset_review_summary  # noqa: E402
from scripts.novel_shot_breakdown import NovelShotBreakdownError, load_shot_breakdown, summary as shot_breakdown_summary  # noqa: E402
from scripts.novel_storyboard import NovelStoryboardError, load_storyboard, summary as storyboard_summary  # noqa: E402
from scripts.novel_animatic import NovelAnimaticError, load_animatic, summary as animatic_summary  # noqa: E402
from scripts.novel_animatic_review import NovelAnimaticReviewError, load_review as load_animatic_review, summary as animatic_review_summary  # noqa: E402
from scripts.novel_voice_profiles import NovelVoiceProfileError, load_voice_profiles, summary as voice_profile_summary  # noqa: E402
from scripts.novel_audio_assets import NovelAudioAssetError, load_audio_assets, summary as audio_asset_summary  # noqa: E402
from scripts.novel_audio_mix import NovelAudioMixError, load_audio_mix, summary as audio_mix_summary  # noqa: E402
from scripts.novel_dynamic_shots import NovelDynamicShotError, load_dynamic_shots, summary as dynamic_shot_summary  # noqa: E402
from scripts.novel_edit_timelines import NovelEditTimelineError, load_edit_timelines, summary as edit_timeline_summary  # noqa: E402
from scripts.novel_qc import NovelQCError, add_annotation, add_issue, compare as compare_qc, load_qc_report, summary as qc_summary, update_issue  # noqa: E402
from scripts.novel_acceptance import NovelAcceptanceError, load_acceptance, summary as acceptance_summary  # noqa: E402
from support.providers.openai_image_provider import OpenAIImageError, OpenAIImageProvider, character_bible_prompt, keyframe_prompt  # noqa: E402
from support.providers.comfyui_image_provider import ComfyUIImageError, ComfyUIImageProvider  # noqa: E402
from support.providers.image_provider_router import ImageProviderRouteError, ImageProviderRouter  # noqa: E402
from scripts.pipeline_orchestrator import PipelineError, pipeline_preflight, pipeline_status, run_pipeline, update_pipeline_review  # noqa: E402
from scripts.novel_web_import import MAX_WEB_UPLOAD_BYTES, NovelWebImportError, create_project_from_web_upload, promote_character_candidates, recover_project_characters  # noqa: E402
from scripts.comfyui_service_manager import ComfyUIServiceError, service_status as comfyui_service_status, start_service as start_comfyui_service, stop_service as stop_comfyui_service  # noqa: E402
from scripts.comfyui_installer import ComfyUIInstallError, start_background_install as start_comfyui_install, status as comfyui_install_status  # noqa: E402
from scripts.comfyui_model_manager import ComfyUIModelError, start_background_install as start_comfyui_model_install, status as comfyui_model_status  # noqa: E402
from scripts.comfyui_lora_manager import ComfyUILoraError, lora_descriptor as comfyui_lora_descriptor, start_background_install as start_comfyui_lora_install, status as comfyui_lora_status  # noqa: E402
from scripts.graybox_shot_spec import GrayboxShotSpecError, apply_natural_language_adjustment as adjust_graybox_spec, ensure_default_spec as ensure_graybox_spec, load_spec as load_graybox_spec, review_spec as review_graybox_spec  # noqa: E402
from scripts.graybox_manager import GrayboxRenderError, start_render as start_graybox_render, status as graybox_render_status  # noqa: E402


PROVIDER_TYPES = {
    "local_ken_burns": LocalKenBurnsVideo,
    "minimax_h3": MiniMaxH3Video,
    "openai_sora": OpenAISoraVideo,
    "runway": RunwayImageToVideo,
    "wan": WanImageToVideo,
}
KEY_ENV = {
    "minimax_h3": "MINIMAX_API_KEY",
    "openai_sora": "OPENAI_API_KEY",
    "openai_image": "OPENAI_API_KEY",
    "runway": "RUNWAY_API_KEY",
    "wan": "FAL_KEY",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}
# Keys entered in the console live only for this server process.  They are
# intentionally never written to disk, returned by the API, or put in logs.
RUNTIME_KEYS: dict[str, str] = {}
RUNTIME_INTEGRATIONS: dict[str, dict[str, str]] = {}
_NOVEL_PROJECT_CACHE: dict[str, tuple[tuple[tuple[str, int, int], ...], list[dict[str, object]]]] = {}
_NOVEL_PROJECT_CACHE_LOCK = threading.Lock()


def _safe_project(project_id: str) -> Path:
    project_id = unquote(str(project_id or "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}", project_id):
        raise ValueError("invalid project id")
    path = (PROJECTS_ROOT / project_id).resolve()
    if PROJECTS_ROOT.resolve() not in path.parents or not path.is_dir():
        raise ValueError("project not found")
    return path


def _safe_project_file(project_id: str, relative_path: str) -> Path:
    project = _safe_project(project_id)
    candidate = (project / unquote(relative_path)).resolve()
    if project not in candidate.parents and candidate != project:
        raise ValueError("file is outside project")
    if not candidate.is_file():
        raise ValueError("file not found")
    return candidate


def _relative(project: Path, path: Path) -> str:
    return path.resolve().relative_to(project.resolve()).as_posix()


def _media_url(project: Path, relative_path: str) -> str:
    project_part = quote(project.name, safe="")
    path_part = "/".join(quote(part, safe="") for part in str(relative_path).split("/") if part)
    return f"/media/{project_part}/{path_part}"


def _image_file_valid(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(16)
    except OSError:
        return False
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if head.startswith(b"\xff\xd8\xff"):
        return True
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return True
    return False


def _media_files(project: Path) -> list[dict[str, str]]:
    files = []
    for path in sorted(project.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            continue
        kind = "image" if path.suffix.lower() in IMAGE_EXTENSIONS else "video"
        files.append({"path": _relative(project, path), "kind": kind, "name": path.name})
    return files


def _episode_metadata(project: Path) -> list[dict[str, object]]:
    """Expose locally rendered episode manifests without exposing filesystem paths."""
    episodes = []
    episode_root = project / "episodes"
    if episode_root.is_dir():
        for manifest in sorted(episode_root.glob("episode-*/episode.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            output = str(data.get("output") or "")
            output_path = (manifest.parent / output).resolve()
            if project.resolve() not in output_path.parents or not output_path.is_file():
                continue
            relative = _relative(project, output_path)
            episodes.append({
                "episode_id": str(data.get("episode_id") or manifest.parent.name),
                "title": str(data.get("title") or manifest.parent.name),
                "status": str(data.get("status") or "LOCAL_REVIEW"),
                "provider": str(data.get("provider") or "local_ken_burns"),
                "output": relative,
                "media_url": _media_url(project, relative),
            })
    if episodes:
        return episodes
    masters = _episode_master_inventory(project)
    return [
        {
            "episode_id": str(item["episode_id"]),
            "title": f"{item['episode_id']} · 本地动态漫试播",
            "status": str(item.get("human_review", {}).get("status") or item.get("status") or "LOCAL_REVIEW"),
            "provider": "local_episode_assembly",
            "output": str(item["output"]),
            "media_url": str(item["media_url"]),
        }
        for item in masters.get("episodes", [])
        if item.get("media_url")
    ]


def _novel_projects_signature(projects_root: Path) -> tuple[tuple[str, int, int], ...]:
    """Return a cheap content signature for files used by project summaries.

    The Web console asks for the project list, readiness and workspaces at the
    same time.  Each summary validates the upstream chain, so recomputing all
    three requests can take tens of seconds once a real five-episode project
    exists.  JSON and repository database mtimes are enough to invalidate this
    process-local cache while keeping the project files authoritative.
    """

    signature: list[tuple[str, int, int]] = []
    if not projects_root.is_dir():
        return ()
    for path in sorted(projects_root.rglob("*")):
        if not path.is_file() or (path.suffix.lower() not in {".json", ".db", ".sqlite", ".sqlite3"} and path.name != NOVEL_ANIME_MANIFEST):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        signature.append((path.relative_to(projects_root).as_posix(), stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


def _novel_anime_projects(projects_root: Path = PROJECTS_ROOT) -> list[dict[str, object]]:
    projects_root = projects_root.resolve()
    cache_key = str(projects_root)
    signature = _novel_projects_signature(projects_root)
    with _NOVEL_PROJECT_CACHE_LOCK:
        cached = _NOVEL_PROJECT_CACHE.get(cache_key)
        if cached and cached[0] == signature:
            return deepcopy(cached[1])

        projects = _build_novel_anime_projects(projects_root)
        final_signature = _novel_projects_signature(projects_root)
        _NOVEL_PROJECT_CACHE[cache_key] = (final_signature, projects)
        return deepcopy(projects)


def _build_novel_anime_projects(projects_root: Path) -> list[dict[str, object]]:
    projects = []
    if not projects_root.is_dir():
        return projects
    for manifest in sorted(projects_root.glob(f"*/{NOVEL_ANIME_MANIFEST}")):
        try:
            project = load_novel_anime_project(manifest)
        except NovelAnimeProjectError:
            continue
        summary = {
            "directory_id": manifest.parent.name,
            "project_id": project["project_id"],
            "title": project["title"],
            "status": project["status"],
            "created_at": project.get("created_at"),
            "updated_at": project.get("updated_at"),
            "ip_id": project["ip"]["id"],
            "series_id": project["series"]["id"],
            "season_count": len(project["seasons"]),
            "episode_count": len(project["episodes"]),
            "episode_ids": [episode["id"] for episode in project["episodes"]],
            "repository": repository_stats(manifest.parent),
            "runtime": runtime_stats(manifest.parent),
            "source_catalog": _source_catalog_summary(manifest.parent),
            "story_bible": story_bible_summary(manifest.parent),
            "series_plan": series_plan_summary(manifest.parent),
            "episode_planning": episode_planning_summary(manifest.parent),
            "episode_scripts": episode_script_summary(manifest.parent),
            "story_review": story_review_summary(manifest.parent),
            "visual_bible": visual_bible_summary(manifest.parent),
            "character_designs": character_design_summary(manifest.parent),
            "environment_assets": environment_asset_summary(manifest.parent),
            "asset_review": asset_review_summary(manifest.parent),
            "shot_breakdown": shot_breakdown_summary(manifest.parent),
            "storyboard": storyboard_summary(manifest.parent),
            "animatic": animatic_summary(manifest.parent),
            "animatic_review": animatic_review_summary(manifest.parent),
            "voice_profiles": voice_profile_summary(manifest.parent),
            "audio_assets": audio_asset_summary(manifest.parent),
            "audio_mix": audio_mix_summary(manifest.parent),
            "dynamic_shots": dynamic_shot_summary(manifest.parent),
            "edit_timelines": edit_timeline_summary(manifest.parent),
            "qc": qc_summary(manifest.parent),
            "acceptance": acceptance_summary(manifest.parent),
        }
        summary["readiness"] = _readiness_from_summary(summary)
        projects.append(summary)
    projects.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            str(item.get("updated_at") or ""),
            str(item.get("directory_id") or ""),
        ),
        reverse=True,
    )
    return projects


def _readiness_from_summary(summary: dict[str, object]) -> dict[str, object]:
    """Build a review-safe stage-gate view for the Web production desk.

    The readiness view is derived from the same summaries used by the CLI and
    never becomes a second source of project state.  It intentionally exposes
    blockers instead of presenting an empty scaffold as ready.
    """

    def gate(gate_id: str, label: str, ready: bool, detail: str, blockers: list[str] | None = None) -> dict[str, object]:
        return {
            "id": gate_id,
            "label": label,
            "status": "READY" if ready else "BLOCKED",
            "detail": detail,
            "blockers": blockers or ([] if ready else [detail]),
        }

    source = summary.get("source_catalog") or {}
    story = summary.get("story_bible") or {}
    story_review = summary.get("story_review") or {}
    characters = summary.get("character_designs") or {}
    environment = summary.get("environment_assets") or {}
    asset_review = summary.get("asset_review") or {}
    shots = summary.get("shot_breakdown") or {}
    storyboard = summary.get("storyboard") or {}
    voices = summary.get("voice_profiles") or {}
    audio = summary.get("audio_assets") or {}
    mix = summary.get("audio_mix") or {}
    dynamic = summary.get("dynamic_shots") or {}
    edit = summary.get("edit_timelines") or {}
    qc = summary.get("qc") or {}
    acceptance = summary.get("acceptance") or {}

    gates = [
        gate(
            "source", "底本与权利",
            bool(source.get("script_adaptation_allowed")) and bool(source.get("publication_allowed")),
            "底本权利与改编门已通过" if source.get("script_adaptation_allowed") and source.get("publication_allowed") else f"权利状态 {source.get('status', 'MISSING')}，改编/发布门未通过",
        ),
        gate(
            "story", "故事与连续性",
            bool(story.get("ready")) and story_review.get("overall_status") == "PASS" and story_review.get("human_review_status") == "APPROVED",
            "故事圣经和剧情审核已通过" if story.get("ready") and story_review.get("overall_status") == "PASS" and story_review.get("human_review_status") == "APPROVED" else f"故事圣经 {story.get('world_status', 'MISSING')}，剧情审核 {story_review.get('overall_status', 'MISSING')}",
        ),
        gate(
            "visual", "角色与场景资产",
            bool(characters.get("ready")) and bool(environment.get("ready")) and bool(asset_review.get("ready")),
            "角色、环境和参考包已审核" if characters.get("ready") and environment.get("ready") and asset_review.get("ready") else f"角色 {characters.get('ready_character_count', 0)}/{characters.get('character_count', 0)}，场景 {environment.get('ready_location_count', 0)}/{environment.get('location_count', 0)}，参考包 {'READY' if asset_review.get('ready') else 'BLOCKED'}",
        ),
        gate(
            "storyboard", "分镜与 Animatic",
            bool(shots.get("shot_count")) and storyboard.get("approved_shot_count", 0) == shots.get("shot_count", 0) and (summary.get("animatic") or {}).get("ready_episode_count", 0) == (summary.get("animatic") or {}).get("episode_count", 0),
            "分镜、首尾帧和五集 Animatic 已就绪" if shots.get("shot_count") and storyboard.get("approved_shot_count", 0) == shots.get("shot_count", 0) else f"镜头 {shots.get('shot_count', 0)}，首尾帧已审 {storyboard.get('approved_shot_count', 0)}",
        ),
        gate(
            "audio", "配音与混音",
            bool(voices.get("ready_profile_count")) and voices.get("ready_line_count", 0) == voices.get("line_count", 0) and bool(audio.get("ready_track_count")) and mix.get("ready_episode_count", 0) == mix.get("episode_count", 0),
            "配音、音轨和五集混音已就绪" if voices.get("ready_profile_count") and voices.get("ready_line_count", 0) == voices.get("line_count", 0) and audio.get("ready_track_count") and mix.get("ready_episode_count", 0) == mix.get("episode_count", 0) else f"配音 {voices.get('ready_line_count', 0)}/{voices.get('line_count', 0)}，混音 {mix.get('ready_episode_count', 0)}/{mix.get('episode_count', 0)}",
        ),
        gate(
            "render", "本地渲染与剪辑",
            bool(dynamic.get("shot_count")) and dynamic.get("ready_route_count", 0) == dynamic.get("shot_count", 0) and edit.get("ready_episode_count", 0) == edit.get("episode_count", 0),
            "动态镜头和集级剪辑已就绪" if dynamic.get("shot_count") and dynamic.get("ready_route_count", 0) == dynamic.get("shot_count", 0) and edit.get("ready_episode_count", 0) == edit.get("episode_count", 0) else f"动态镜头 {dynamic.get('ready_route_count', 0)}/{dynamic.get('shot_count', 0)}，剪辑 {edit.get('ready_episode_count', 0)}/{edit.get('episode_count', 0)}",
        ),
        gate(
            "qc", "QC 与正式验收",
            qc.get("overall_status") == "PASS" and qc.get("human_review_status") == "APPROVED" and acceptance.get("decision") == "PASS",
            "六类 QC 和正式五集验收已通过" if qc.get("overall_status") == "PASS" and qc.get("human_review_status") == "APPROVED" and acceptance.get("decision") == "PASS" else f"QC {qc.get('overall_status', 'MISSING')}，正式验收 {acceptance.get('decision', 'MISSING')}，开放阻断 {qc.get('open_blocker_count', 0)}",
        ),
    ]
    ready_count = sum(item["status"] == "READY" for item in gates)
    next_actions = [item["detail"] for item in gates if item["status"] == "BLOCKED"][:3]
    return {
        "project_id": summary.get("project_id"),
        "decision": acceptance.get("decision", "HOLD"),
        "ready_count": ready_count,
        "gate_count": len(gates),
        "gates": gates,
        "next_actions": next_actions,
    }


WORKSPACE_DEFINITIONS = (
    ("overview", "项目总览", "项目、季、集和全局状态"),
    ("ip", "IP 与底本", "来源、章节、权利和适用地域"),
    ("story", "故事圣经", "世界观、角色、关系和连续性账本"),
    ("script", "编剧室", "全剧规划、单集卡、场景剧本和故事审核"),
    ("assets", "角色美术", "角色、场景、道具和参考包"),
    ("storyboard", "分镜 Animatic", "Scene/Shot、首尾帧、本地预览和节奏审核"),
    ("audio", "音频制作", "配音、音轨、Cue 和混音"),
    ("render", "渲染队列", "动态镜头、剪辑时间线、任务和成本"),
    ("review", "审片与问题单", "六类 QC、批注、问题单和版本比较"),
    ("publish", "发布包", "人工确认、配置、快照和发布门"),
)


def _novel_anime_workspaces(project_id: str) -> dict[str, object]:
    project = _safe_project(project_id)
    summary = next((item for item in _novel_anime_projects() if item["directory_id"] == project.name), None)
    if summary is None:
        raise ValueError("novel-anime project not found")
    episode_masters = _episode_master_inventory(project)
    episode_master_summary = {
        "status": episode_masters.get("status", "NOT_RUN"),
        "episode_count": episode_masters.get("episode_count", 0),
        "technical_qc_status": episode_masters.get("technical_qc", {}).get("status", "NOT_RUN"),
        "human_review_status": episode_masters.get("human_review", {}).get("status", "PENDING"),
    }
    provider_tests = _provider_motion_test_inventory(project)
    provider_test_summary = {
        "status": provider_tests.get("status", "NOT_PREPARED"),
        "test_count": provider_tests.get("test_count", 0),
        "remote_execution": provider_tests.get("remote_execution", "BLOCKED_PENDING_AUTHORIZATION"),
    }
    resources = {
        "overview": {"project": summary, "repository": summary["repository"], "runtime": summary["runtime"], "readiness": summary.get("readiness")},
        "ip": {"source_catalog": summary["source_catalog"]},
        "story": {"story_bible": summary["story_bible"]},
        "script": {"series_plan": summary["series_plan"], "episode_planning": summary["episode_planning"], "episode_scripts": summary["episode_scripts"], "story_review": summary["story_review"]},
        "assets": {"visual_bible": summary["visual_bible"], "character_designs": summary["character_designs"], "environment_assets": summary["environment_assets"], "asset_review": summary["asset_review"]},
        "storyboard": {"shot_breakdown": summary["shot_breakdown"], "storyboard": summary["storyboard"], "animatic": summary["animatic"], "animatic_review": summary["animatic_review"]},
        "audio": {"voice_profiles": summary["voice_profiles"], "audio_assets": summary["audio_assets"], "audio_mix": summary["audio_mix"]},
        "render": {"dynamic_shots": summary["dynamic_shots"], "edit_timelines": summary["edit_timelines"], "episode_masters": episode_master_summary, "provider_motion_tests": provider_test_summary, "runtime": summary["runtime"]},
        "review": {"qc": summary["qc"], "acceptance": summary["acceptance"]},
        "publish": {"source_catalog": summary["source_catalog"], "qc": summary["qc"], "acceptance": summary["acceptance"], "repository": summary["repository"]},
    }
    workspaces = [{"id": key, "title": title, "description": description, "status": "CONNECTED", "data": resources[key]} for key, title, description in WORKSPACE_DEFINITIONS]
    return {"project_id": summary["project_id"], "directory_id": project.name, "title": summary["title"], "workspace_order": [item["id"] for item in workspaces], "workspaces": workspaces}


def _backup_inventory(project: Path) -> dict[str, object]:
    snapshots = []
    for path in sorted((project / ".videocreator" / "snapshots").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        snapshots.append({"snapshot_id": payload.get("snapshot_id"), "label": payload.get("label"), "created_at": payload.get("created_at"), "path": _relative(project, path)})
    migrations = []
    for path in sorted((project / ".videocreator" / "migrations").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        migrations.append({"migration_key": payload.get("migration_key"), "completed_at": payload.get("completed_at"), "path": _relative(project, path)})
    return {"snapshot_count": len(snapshots), "snapshots": snapshots, "migration_count": len(migrations), "migrations": migrations, "recovery_requires_manual_confirmation": True}


def _source_catalog_summary(project: Path) -> dict[str, object] | None:
    path = project / CATALOG_RELATIVE_PATH
    if not path.is_file():
        return None
    try:
        catalog = load_catalog(path)
    except NovelSourceCatalogError:
        return None
    imports = _source_import_summaries(project)
    return {
        "status": catalog["rights_assessment"]["status"],
        "target_regions": catalog["target_regions"],
        "edition_count": len(catalog["editions"]),
        "chapter_count": len(catalog["chapters"]),
        "locator_count": len(catalog["locators"]),
        "script_adaptation_allowed": catalog["adaptation_policy"]["script_adaptation_allowed"],
        "publication_allowed": catalog["rights_assessment"]["publication_allowed"],
        "import_count": len(imports),
        "test_import_count": sum(1 for item in imports if item["test_only"]),
        "character_candidates": sum(item["character_candidates"] for item in imports),
        "location_candidates": sum(item["location_candidates"] for item in imports),
        "prop_candidates": sum(item["prop_candidates"] for item in imports),
        "event_candidates": sum(item["event_candidates"] for item in imports),
        "full_text_stored": any(item["full_text_stored"] for item in imports),
    }


def _source_import_summaries(project: Path) -> list[dict[str, object]]:
    """Return review-safe import metadata without exposing source text."""
    summaries: list[dict[str, object]] = []
    for path in sorted((project / "sources" / "imports").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            extraction = payload["extraction"]
            if not isinstance(extraction, dict):
                continue
            summary = {
                "import_id": str(payload["import_id"]),
                "edition_id": str(payload["edition_id"]),
                "source_file_name": str(payload["source_file_name"]),
                "source_sha256": str(payload["source_sha256"]),
                "chapter_count": len(payload.get("chapters", [])),
                "character_candidates": len(extraction.get("characters", [])),
                "location_candidates": len(extraction.get("locations", [])),
                "prop_candidates": len(extraction.get("props", [])),
                "event_candidates": len(extraction.get("events", [])),
                "test_only": payload.get("test_only") is True,
                "full_text_stored": payload.get("full_text_stored") is True,
                "human_review_required": payload.get("human_review_required") is True,
                "created_at": str(payload.get("created_at", "")),
            }
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        summaries.append(summary)
    return summaries


IMAGE_PROVIDER_CONFIG_PATH = ROOT / "config" / "providers" / "openai-image-provider.json"
COMFYUI_IMAGE_PROVIDER_CONFIG_PATH = ROOT / "config" / "providers" / "comfyui-image-provider.json"
IMAGE_CHARACTER_CONFIG_PATH = ROOT / "config" / "characters" / "char-child-001.json"
IMAGE_SHOT_CONFIG_PATH = ROOT / "config" / "shots" / "demo-shot-001.json"
VISUAL_GENERATION_ROUTE_CONFIG_PATH = ROOT / "config" / "visual-generation-routes.json"
IMAGE_STYLE_PRESETS_CONFIG_PATH = ROOT / "config" / "providers" / "image-style-presets.json"


def _load_repo_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"configuration file not found: {path.relative_to(ROOT)}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid configuration file: {path.relative_to(ROOT)}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"configuration must be an object: {path.relative_to(ROOT)}")
    return payload


def _image_provider_router() -> ImageProviderRouter:
    return ImageProviderRouter(VISUAL_GENERATION_ROUTE_CONFIG_PATH)


def _image_style_presets() -> dict[str, object]:
    payload = _load_repo_json(IMAGE_STYLE_PRESETS_CONFIG_PATH)
    raw_presets = payload.get("presets")
    if not isinstance(raw_presets, list) or not raw_presets:
        raise ValueError("image style presets are missing")
    presets: list[dict[str, object]] = []
    ids: set[str] = set()
    for raw in raw_presets:
        if not isinstance(raw, dict):
            continue
        preset_id = str(raw.get("id") or "").strip().upper()
        if not preset_id or preset_id in ids:
            continue
        ids.add(preset_id)
        presets.append({
            "id": preset_id,
            "label": str(raw.get("label") or preset_id),
            "description": str(raw.get("description") or ""),
            "positive_prompt_prefix": str(raw.get("positive_prompt_prefix") or ""),
            "negative_prompt": str(raw.get("negative_prompt") or ""),
            "remote_direction": str(raw.get("remote_direction") or ""),
            "lora_id": str(raw.get("lora_id") or "").strip(),
            "lora_strength": float(raw.get("lora_strength") or 0.0),
            "preferred_provider": str(raw.get("preferred_provider") or "").strip().upper(),
            "render_role": str(raw.get("render_role") or "CONCEPT_PREVIEW").strip().upper(),
            "layout_mode": str(raw.get("layout_mode") or "CHARACTER_BOARD").strip().upper(),
            "final_provider_required": raw.get("final_provider_required") is True,
        })
    if not presets:
        raise ValueError("image style presets are invalid")
    default_id = str(payload.get("default_preset") or presets[0]["id"]).strip().upper()
    if default_id not in {str(item["id"]) for item in presets}:
        default_id = str(presets[0]["id"])
    return {"default_preset": default_id, "presets": presets}


def _image_style_preset(preset_id: str = "") -> dict[str, object]:
    payload = _image_style_presets()
    requested = str(preset_id or payload["default_preset"]).strip().upper()
    for preset in payload["presets"]:
        if str(preset["id"]) == requested:
            return dict(preset)
    raise ValueError(f"unsupported image style preset: {requested}")


def _openai_image_status() -> dict[str, object]:
    cfg = _load_repo_json(IMAGE_PROVIDER_CONFIG_PATH)
    env_name = str(cfg.get("key_env") or "OPENAI_API_KEY")
    runtime_key = RUNTIME_KEYS.get("openai_image") or RUNTIME_KEYS.get("openai_sora")
    configured = bool(runtime_key or os.environ.get(env_name))
    return {
        "id": "openai_image",
        "label": str(cfg.get("label") or "OpenAI Image"),
        "model": str(cfg.get("model") or "gpt-image-2"),
        "configured": configured,
        "source": "session" if runtime_key else ("environment" if os.environ.get(env_name) else "none"),
        "remote": True,
        "review_required": True,
        "key_env": env_name,
        "routing_role": "HIGH_QUALITY_FALLBACK",
        "final_visual_route": "IMAGE_PROVIDER_ROUTER",
        "blender_role": "AUXILIARY_3D_CONTROL",
    }


def _comfyui_base_url() -> str:
    cfg = _load_repo_json(COMFYUI_IMAGE_PROVIDER_CONFIG_PATH)
    runtime = RUNTIME_INTEGRATIONS.get("comfyui", {})
    env_name = str(cfg.get("base_url_env") or "COMFYUI_BASE_URL")
    return str(runtime.get("base_url") or os.environ.get(env_name) or cfg.get("default_base_url") or "http://127.0.0.1:8188").rstrip("/")


def _comfyui_image_status() -> dict[str, object]:
    cfg = _load_repo_json(COMFYUI_IMAGE_PROVIDER_CONFIG_PATH)
    base_url = _comfyui_base_url()
    runtime = RUNTIME_INTEGRATIONS.get("comfyui", {})
    env_name = str(cfg.get("base_url_env") or "COMFYUI_BASE_URL")
    result: dict[str, object] = {
        "id": "comfyui_image",
        "provider_id": "COMFYUI_IMAGE",
        "label": str(cfg.get("label") or "ComfyUI Local"),
        "configured": bool(base_url),
        "connected": False,
        "workflow_ready": False,
        "remote": False,
        "review_required": True,
        "base_url": base_url,
        "source": "session" if runtime.get("base_url") else ("environment" if os.environ.get(env_name) else "default"),
        "routing_role": "LOCAL_VISUAL_FACTORY",
        "final_visual_route": "IMAGE_PROVIDER_ROUTER",
        "blender_role": "AUXILIARY_3D_CONTROL",
        "checkpoint_count": 0,
        "checkpoint": "",
    }
    try:
        timeout = float(cfg.get("status_timeout_seconds") or 0.8)
        provider = ComfyUIImageProvider(base_url, config_path=COMFYUI_IMAGE_PROVIDER_CONFIG_PATH, timeout_seconds=timeout)
        health = provider.health(timeout_seconds=timeout)
        checkpoints = provider.available_checkpoints(timeout_seconds=timeout)
        loras = provider.available_loras(timeout_seconds=timeout)
        result.update(
            connected=bool(health.get("connected")),
            workflow_ready=bool(checkpoints),
            checkpoint_count=len(checkpoints),
            checkpoint=provider.choose_checkpoint(checkpoints) if checkpoints else "",
            lora_count=len(loras),
            loras=loras,
            device_count=int(health.get("device_count") or 0),
            detail="本地 ComfyUI 已连接" if checkpoints else "ComfyUI 已连接，但没有可用 checkpoint",
        )
    except (ComfyUIImageError, ValueError) as error:
        result["detail"] = str(error)
    try:
        result["service"] = comfyui_service_status(base_url, connected=bool(result.get("connected")))
    except (ComfyUIServiceError, ValueError, OSError) as error:
        result["service"] = {"state": "ERROR", "detail": str(error), "managed": False, "installed": False}
    try:
        result["installer"] = comfyui_install_status()
    except (ComfyUIInstallError, ValueError, OSError) as error:
        result["installer"] = {"status": "ERROR", "detail": str(error), "installed": False}
    try:
        result["model_installer"] = comfyui_model_status()
    except (ComfyUIModelError, ValueError, OSError) as error:
        result["model_installer"] = {"status": "ERROR", "detail": str(error), "installed": False}
    try:
        result["lora_installer"] = comfyui_lora_status()
    except (ComfyUILoraError, ValueError, OSError) as error:
        result["lora_installer"] = {"status": "ERROR", "detail": str(error), "installed": False}
    return result


def _expected_source_hashes(project: Path) -> set[str]:
    hashes: set[str] = set()
    root = project / "sources" / "imports"
    if not root.is_dir():
        return hashes
    for path in root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        value = str(payload.get("source_sha256") or "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", value):
            hashes.add(value)
    return hashes


def _sync_import_character_extraction(
    project: Path,
    *,
    source_sha256: str,
    provider: str,
    characters: list[dict[str, object]],
) -> int:
    updated = 0
    imports_root = project / "sources" / "imports"
    if not imports_root.is_dir():
        return 0
    for path in imports_root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("source_sha256") or "").strip().lower() != source_sha256:
            continue
        extraction = payload.get("extraction")
        if not isinstance(extraction, dict):
            extraction = {}
            payload["extraction"] = extraction
        extraction["provider"] = provider
        extraction["characters"] = characters
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
        updated += 1
    return updated


def _reanalyze_project_character_candidates(
    project: Path,
    *,
    source_name: str,
    source_text: str,
) -> dict[str, object]:
    manifest = load_novel_anime_project(project / NOVEL_ANIME_MANIFEST)
    ip_code = str(manifest["ip"]["id"]).removeprefix("IP-")
    result = extract_character_candidates_from_text(source_text, ip_code)
    source_sha = str(result["source_sha256"]).lower()
    expected = _expected_source_hashes(project)
    if expected and source_sha not in expected:
        raise ValueError("所选 TXT 与当前项目最初导入的底本 SHA256 不一致")
    characters = result.get("characters") if isinstance(result.get("characters"), list) else []
    if not characters:
        raise ValueError("未从底本识别到稳定角色候选；当前不会回退到演示角色")
    provider = str(result.get("provider") or "local_lexicon")
    payload = build_character_candidates(
        project,
        source_file_name=source_name,
        source_sha256=source_sha,
        provider=provider,
        characters=characters,
    )
    write_character_candidates(project, payload)
    promotion = promote_character_candidates(project, payload)
    import_updates = _sync_import_character_extraction(
        project,
        source_sha256=source_sha,
        provider=provider,
        characters=characters,
    )
    return {
        "status": "PASS",
        "project_id": project.name,
        "chapter_count": int(result.get("chapter_count") or 0),
        "character_count": len(payload["characters"]),
        "characters": [
            {
                "id": item["id"],
                "name": item["name"],
                "total_mentions": item["total_mentions"],
            }
            for item in payload["characters"][:12]
        ],
        "full_text_stored": False,
        "source_sha256": source_sha,
        "import_metadata_updated": import_updates,
        "story_bible_character_count": int(promotion.get("character_count") or 0),
        "story_bible_promoted": bool(promotion.get("promoted")),
    }


def _project_image_character(project: Path) -> tuple[dict[str, object], bool, str]:
    demo = _load_repo_json(IMAGE_CHARACTER_CONFIG_PATH)
    manifest = project / NOVEL_ANIME_MANIFEST
    if not manifest.is_file():
        return demo, True, "global-demo"

    # Old P31 imports may have persisted extraction candidates but left the
    # Story Bible empty.  Repair that chain automatically from project metadata;
    # never fall back to the global demo character for a novel project.
    try:
        recovery = recover_project_characters(project)
        if recovery.get("promoted"):
            _NOVEL_PROJECT_CACHE.clear()
    except (NovelWebImportError, OSError, ValueError):
        recovery = {"status": "BLOCKED"}

    try:
        bible = load_bible(project)
    except (NovelStoryBibleError, OSError, ValueError):
        bible = {}
    characters = bible.get("characters") if isinstance(bible, dict) else None
    candidate_payload = None
    try:
        candidate_payload = load_character_candidates(project)
    except (NovelCharacterCandidateError, OSError, ValueError):
        candidate_payload = None
    candidates = candidate_payload.get("characters") if isinstance(candidate_payload, dict) else None

    if (not isinstance(characters, list) or not characters) and isinstance(candidates, list) and candidates:
        candidate = candidates[0]
        source_character = {
            "id": str(candidate.get("id") or ""),
            "name": str(candidate.get("name") or "未命名角色"),
            "role": "主要角色候选（待人工确认）",
            "description": f"底本中出现 {int(candidate.get('total_mentions') or 0)} 次；角色视觉细节待定妆审核。",
            "traits": [],
        }
        characters = [source_character]
        character_source_override = "local-character-candidate"
    else:
        character_source_override = ""

    if not isinstance(characters, list) or not characters:
        placeholder = deepcopy(demo)
        placeholder.update({
            "character_id": "",
            "name": "项目角色尚未抽取",
            "role": "当前小说项目暂无角色资料",
            "visual_lock": {
                "age_read": "",
                "face": "项目会自动从已保存的导入元数据恢复角色；无需重新上传 TXT",
                "hair": "—",
                "costume": "—",
                "body": "—",
                "mood": "—",
            },
            "consistency_rules": [],
            "status": "BLOCKED",
        })
        return placeholder, False, "project-story-bible-empty"

    def priority(item: dict[str, object]) -> tuple[int, str]:
        role = str(item.get("role") or "").lower()
        score = 0 if any(token in role for token in ("主角", "protagonist", "hero", "lead")) else 1
        return score, str(item.get("id") or "")

    if character_source_override:
        source_character = next(item for item in characters if isinstance(item, dict))
    else:
        source_character = sorted(
            [item for item in characters if isinstance(item, dict)],
            key=priority,
        )[0]

    identity: dict[str, object] = {}
    try:
        designs = load_character_designs(project)
        for design in designs.get("character_designs", []):
            if str(design.get("character_id") or "") == str(source_character.get("id") or ""):
                identity = design.get("identity") if isinstance(design.get("identity"), dict) else {}
                break
    except (NovelCharacterDesignError, OSError, ValueError):
        identity = {}

    render_lock = deepcopy(demo.get("render_lock") or {})
    try:
        visual = load_visual_bible(project)
        style = visual.get("style") if isinstance(visual, dict) else {}
        color_script = visual.get("color_script") if isinstance(visual, dict) else {}
        swatches = color_script.get("swatches") if isinstance(color_script, dict) else []
        if isinstance(style, dict):
            if str(style.get("rendering") or "").strip():
                render_lock["medium"] = str(style["rendering"])
            if str(style.get("art_direction") or "").strip():
                render_lock["shading"] = str(style["art_direction"])
        palette = [
            f"{item.get('name')} {item.get('hex')}"
            for item in swatches
            if isinstance(item, dict) and item.get("name") and item.get("hex")
        ]
        if palette:
            render_lock["palette"] = palette[:8]
    except (NovelVisualBibleError, OSError, ValueError):
        pass

    description = str(source_character.get("description") or "").strip()
    traits = [str(item) for item in source_character.get("traits", []) if str(item).strip()]
    role = str(source_character.get("role") or "story character").strip() or "story character"
    face = str(identity.get("face_shape") or "").strip() or description or "source-consistent facial design"
    hair_parts = [str(identity.get("hair_shape") or "").strip(), str(identity.get("hair_color") or "").strip()]
    hair = ", ".join(part for part in hair_parts if part) or "source-consistent hairstyle"
    body_parts = [str(identity.get("body_type") or "").strip()]
    if identity.get("height_heads") is not None:
        body_parts.append(f"{identity.get('height_heads')} heads tall")
    body = ", ".join(part for part in body_parts if part) or "source-consistent body proportions"
    mood = ", ".join(traits[:6]) or description or "emotionally readable"
    negatives = [str(item) for item in identity.get("negative_constraints", []) if str(item).strip()]
    immutable = [str(item) for item in identity.get("immutable_features", []) if str(item).strip()]

    character = {
        "schema_version": 1,
        "character_id": str(source_character.get("id") or ""),
        "name": str(source_character.get("name") or "未命名角色"),
        "role": role,
        "style_id": "PROJECT_VISUAL_BIBLE",
        "visual_lock": {
            "age_read": description or role,
            "face": face,
            "hair": hair,
            "costume": "ancient Chinese role-appropriate hanfu or period robe, crossed collar, layered silk/linen, wide sleeves or practical bracers as role requires, sash/belt, traditional Chinese hair ornament and restrained jade/metal details; follow reviewed project character design when available; never modern clothing or Japanese school uniform",
            "body": body,
            "mood": mood,
        },
        "render_lock": render_lock,
        "consistency_rules": immutable + negatives,
        "status": "PROJECT",
    }
    return character, True, character_source_override or "project-story-bible"


def _recent_image_studio_elsewhere(current_project: Path, limit: int = 6) -> list[dict[str, object]]:
    recent: list[dict[str, object]] = []
    if not PROJECTS_ROOT.is_dir():
        return recent
    for other in PROJECTS_ROOT.iterdir():
        if not other.is_dir() or other.resolve() == current_project.resolve():
            continue
        root = other / "lookdev" / "image-studio"
        if not root.is_dir():
            continue
        title = other.name
        manifest = other / NOVEL_ANIME_MANIFEST
        if manifest.is_file():
            try:
                title = str(load_novel_anime_project(manifest).get("title") or title)
            except (NovelAnimeProjectError, OSError, ValueError):
                pass
        for meta_path in root.rglob("*.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            output = str(meta.get("output") or "")
            output_path = other / output
            if not output or not output_path.is_file() or not _image_file_valid(output_path):
                continue
            recent.append({
                "project_id": other.name,
                "project_title": title,
                "artifact_type": str(meta.get("artifact_type") or ""),
                "created_at": str(meta.get("created_at") or ""),
                "output": output,
                "media_url": _media_url(other, output),
            })
    recent.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("project_id") or "")), reverse=True)
    return recent[:max(0, int(limit))]


def _image_studio_inventory(project: Path) -> dict[str, object]:
    root = project / "lookdev" / "image-studio"
    items: list[dict[str, object]] = []
    if root.is_dir():
        for meta_path in sorted(root.rglob("*.json"), reverse=True):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            output = str(meta.get("output") or "")
            output_path = project / output
            if not output or not output_path.is_file() or output_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            item = dict(meta)
            item["media_url"] = _media_url(project, output)
            item["media_valid"] = _image_file_valid(output_path)
            try:
                item["media_bytes"] = output_path.stat().st_size
            except OSError:
                item["media_bytes"] = 0
            item["metadata"] = _relative(project, meta_path)
            items.append(item)
    comfyui = _comfyui_image_status()
    openai = _openai_image_status()
    styles = _image_style_presets()
    character, character_ready, character_source = _project_image_character(project)
    return {
        "project_id": project.name,
        "provider": openai,
        "providers": [
            {"id": "AUTO", "label": "Auto Route", "configured": bool(comfyui.get("workflow_ready") or openai.get("configured")), "connected": bool(comfyui.get("workflow_ready")), "remote": False, "mode": "LOCAL_FIRST_FALLBACK_REMOTE"},
            comfyui,
            {**openai, "provider_id": "OPENAI_IMAGE"},
        ],
        "default_provider": "AUTO",
        "default_style_preset": styles["default_preset"],
        "style_presets": styles["presets"],
        "character": character,
        "character_ready": character_ready,
        "character_source": character_source,
        "character_candidates": character_candidate_summary(project),
        "shot": _load_repo_json(IMAGE_SHOT_CONFIG_PATH),
        "routing": _image_provider_router().describe(),
        "items": items[:24],
        "recent_elsewhere": _recent_image_studio_elsewhere(project) if not items else [],
        "review_required": True,
    }


def _generate_image_studio_asset(
    project: Path,
    *,
    artifact_type: str,
    custom_prompt: str = "",
    confirm_billable: bool = False,
    upload_authorized: bool = False,
    preferred_provider: str = "AUTO",
    style_preset: str = "",
    comfyui_client_id: str = "",
) -> dict[str, object]:
    if artifact_type not in {"character_bible", "keyframe"}:
        raise ValueError("unsupported image studio artifact type")

    capability = "character_bible" if artifact_type == "character_bible" else "shot_keyframe"
    preset = _image_style_preset(style_preset)
    comfyui_status = _comfyui_image_status()
    openai_status = _openai_image_status()
    available: set[str] = set()
    if comfyui_status.get("connected") and comfyui_status.get("workflow_ready"):
        available.add("COMFYUI_IMAGE")
    if openai_status.get("configured"):
        available.add("OPENAI_IMAGE")
    if not available:
        raise ValueError("没有可用的 Image Provider：请启动本地 ComfyUI 或配置 OpenAI Image")

    requested = str(preferred_provider or "AUTO").strip().upper()
    if requested not in {"AUTO", "COMFYUI_IMAGE", "OPENAI_IMAGE"}:
        raise ValueError("unsupported image provider preference")
    style_preferred = str(preset.get("preferred_provider") or "").strip().upper()
    final_provider_required = bool(preset.get("final_provider_required"))
    if final_provider_required:
        required_provider = style_preferred or "OPENAI_IMAGE"
        if requested not in {"AUTO", required_provider}:
            raise ValueError(
                "当前“参考视频·电影级 3D 国漫”是最终视觉路线，不能使用 Animagine 本地预览生成；"
                "请将生图路线设为 AUTO 或 OpenAI Image。"
            )
        if required_provider not in available:
            raise ValueError(
                "当前“参考视频·电影级 3D 国漫”需要最终视觉 Provider，但 OpenAI Image 尚未配置。"
                "Animagine 只用于本地概念预览，不会再冒充最终 3D LookDev。"
            )

    effective_preferred = None
    if requested != "AUTO":
        effective_preferred = requested
    elif style_preferred in available:
        effective_preferred = style_preferred
    route = _image_provider_router().route(
        capability,
        preferred_provider=effective_preferred,
        available_provider_ids=available,
        confirm_billable=confirm_billable,
        reference_image=False,
        upload_authorized=upload_authorized,
    )

    character, character_ready, character_source = _project_image_character(project)
    if not character_ready:
        raise ValueError(
            "当前小说项目尚未抽取角色资料，已阻止使用全局演示角色生成定妆板；"
            "请先完成项目角色抽取/故事圣经。"
        )
    local_route = route["adapter"] == "comfyui_image"
    style_direction = str(preset.get("remote_direction") or "")
    forbidden_direction = "" if local_route else str(preset.get("negative_prompt") or "")
    if str(preset.get("render_role") or "").upper() == "FINAL_VISUAL":
        character = deepcopy(character)
        existing_render = character.get("render_lock") if isinstance(character.get("render_lock"), dict) else {}
        character["render_lock"] = {
            "medium": "premium cinematic 3D Chinese donghua, high-end stylized NPR production render",
            "shading": "fully modeled volumetric 3D forms, sculpted facial planes, dimensional hair geometry, layered cloth with visible thickness, stylized toon/NPR shading with believable PBR material response, soft subsurface skin, contact shadows, never flat illustration",
            "lighting": "film-quality key/fill/rim lighting with controlled volumetric atmosphere, perspective and real depth of field",
            "palette": list(existing_render.get("palette") or []),
        }
    shot = _load_repo_json(IMAGE_SHOT_CONFIG_PATH)
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 100000:05d}"
    if artifact_type == "character_bible":
        prompt = character_bible_prompt(
            character,
            custom_prompt,
            style_direction=style_direction,
            forbidden_direction=forbidden_direction,
            layout_mode=str(preset.get("layout_mode") or "CHARACTER_BOARD"),
        )
        output_dir = project / "lookdev" / "image-studio" / "character-bible"
        output = output_dir / f"{stamp}-char-child-001.png"
        artifact_id = f"CHAR-BIBLE-{stamp}"
    else:
        prompt = keyframe_prompt(
            character,
            shot,
            custom_prompt,
            style_direction=style_direction,
            forbidden_direction=forbidden_direction,
        )
        output_dir = project / "lookdev" / "image-studio" / "keyframes"
        output = output_dir / f"{stamp}-shot-demo-001.png"
        artifact_id = f"KEYFRAME-{stamp}"

    if route["adapter"] == "comfyui_image":
        cfg = _load_repo_json(COMFYUI_IMAGE_PROVIDER_CONFIG_PATH)
        size = str(cfg.get("character_bible_size") if artifact_type == "character_bible" else cfg.get("keyframe_size") or "1024x1536")
        if artifact_type == "character_bible" and not cfg.get("character_bible_size"):
            size = "1536x1024"
        provider = ComfyUIImageProvider(_comfyui_base_url(), config_path=COMFYUI_IMAGE_PROVIDER_CONFIG_PATH)
        lora_id = str(preset.get("lora_id") or "").strip()
        lora_name = ""
        lora_strength = float(preset.get("lora_strength") or 0.0)
        if lora_id:
            try:
                descriptor = comfyui_lora_descriptor(lora_id)
                candidate_name = str(descriptor.get("filename") or "")
                install_state = comfyui_lora_status(lora_id)
                if install_state.get("installed") and candidate_name in set(comfyui_status.get("loras") or []):
                    lora_name = candidate_name
            except (ComfyUILoraError, ValueError, OSError):
                lora_name = ""
        result = provider.generate(
            prompt,
            output,
            size=size,
            positive_prompt_prefix=str(preset.get("positive_prompt_prefix") or ""),
            negative_prompt=str(preset.get("negative_prompt") or ""),
            lora_name=lora_name or None,
            lora_strength=lora_strength,
            client_id=comfyui_client_id or None,
        )
    elif route["adapter"] == "openai_image":
        cfg = _load_repo_json(IMAGE_PROVIDER_CONFIG_PATH)
        env_name = str(cfg.get("key_env") or "OPENAI_API_KEY")
        api_key = RUNTIME_KEYS.get("openai_image") or RUNTIME_KEYS.get("openai_sora") or os.environ.get(env_name)
        if not api_key:
            raise ValueError("请先在 AI 生图页面配置 OpenAI API Key")
        size = str(cfg.get("character_bible_size") if artifact_type == "character_bible" else cfg.get("keyframe_size") or "1024x1536")
        if artifact_type == "character_bible" and not cfg.get("character_bible_size"):
            size = "1536x1024"
        provider = OpenAIImageProvider(str(api_key), model=str(cfg.get("model") or "gpt-image-2"), base_url=str(cfg.get("base_url") or "https://api.openai.com/v1"))
        result = provider.generate(prompt, output, size=size, quality=str(cfg.get("quality") or "high"))
    else:
        raise ValueError("selected Image Provider adapter is not implemented")
    relative = _relative(project, output)
    metadata = {
        "schema_version": 1,
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "provider": result["provider"],
        "model": result["model"],
        "size": result["size"],
        "quality": result["quality"],
        "style_preset": str(preset.get("id") or ""),
        "style_label": str(preset.get("label") or ""),
        "layout_mode": str(preset.get("layout_mode") or "CHARACTER_BOARD"),
        "style_preferred_provider": str(preset.get("preferred_provider") or ""),
        "requested_render_role": str(preset.get("render_role") or "CONCEPT_PREVIEW"),
        "render_role": (
            "FINAL_VISUAL"
            if str(preset.get("render_role") or "").upper() == "FINAL_VISUAL" and route["adapter"] == "openai_image"
            else "LOCAL_PREVIEW"
            if str(preset.get("render_role") or "").upper() == "FINAL_VISUAL" and route["adapter"] == "comfyui_image"
            else str(preset.get("render_role") or "CONCEPT_PREVIEW")
        ),
        "lora_requested": str(preset.get("lora_id") or ""),
        "lora_applied": bool(result.get("lora_name")),
        "lora_name": str(result.get("lora_name") or ""),
        "lora_strength": float(result.get("lora_strength") or 0.0),
        "project_id": project.name,
        "character_id": str(character.get("character_id") or ""),
        "character_source": character_source,
        "shot_id": str(shot.get("shot_id") or "SHOT-DEMO-001") if artifact_type == "keyframe" else None,
        "style_id": str(character.get("style_id") or "STYLE-REF-GUOFENG-DIALOGUE-001"),
        "output": relative,
        "review_status": "PENDING",
        "human_review_required": bool(route["human_review_required"]),
        "route_id": route["route_id"],
        "provider_id": route["provider_id"],
        "provider_role": route["role"],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prompt": prompt,
        "remote": bool(route["remote"]),
        "fallback_chain": route.get("fallback_chain", []),
        "provider_task_id": str(result.get("prompt_id") or ""),
    }
    if not _image_file_valid(output):
        raise ValueError("Image Provider returned a file that is not a valid PNG/JPEG/WebP image")
    metadata_path = output.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        **metadata,
        "media_url": _media_url(project, relative),
        "media_valid": True,
        "media_bytes": output.stat().st_size,
        "metadata": _relative(project, metadata_path),
    }


def _update_image_studio_review(project: Path, payload: dict[str, object]) -> dict[str, object]:
    metadata_rel = str(payload.get("metadata") or "").strip()
    if not metadata_rel:
        raise ValueError("metadata path is required")
    metadata_path = _safe_project_file(project.name, metadata_rel)
    if metadata_path.suffix.lower() != ".json" or "lookdev/image-studio/" not in metadata_path.as_posix():
        raise ValueError("metadata is not an image-studio artifact")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("image-studio metadata is invalid") from error
    if not isinstance(metadata, dict):
        raise ValueError("image-studio metadata must be an object")

    status = str(payload.get("status") or "").strip().upper()
    if status not in {"APPROVED", "CHANGES_REQUESTED", "PENDING"}:
        raise ValueError("status must be APPROVED, CHANGES_REQUESTED or PENDING")
    metadata["review_status"] = status
    metadata["review_note"] = str(payload.get("note") or "").strip()
    metadata["reviewed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    metadata["reviewed_by"] = "human-web"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output = str(metadata.get("output") or "")
    return {
        **metadata,
        "media_url": _media_url(project, output) if output else "",
        "metadata": _relative(project, metadata_path),
    }


def _provider_status() -> list[dict[str, object]]:
    status = [{"id": "local_ken_burns", "label": "本地动态分镜", "remote": False, "configured": True}]
    for provider_id, label in (("minimax_h3", "MiniMax H3 · 白模转成片"), ("openai_sora", "OpenAI Sora"), ("runway", "Runway"), ("wan", "Wan 2.1")):
        env_name = KEY_ENV[provider_id]
        status.append({
            "id": provider_id,
            "label": label,
            "remote": True,
            "configured": bool(RUNTIME_KEYS.get(provider_id) or os.environ.get(env_name)),
            "env": env_name,
            "source": "session" if RUNTIME_KEYS.get(provider_id) else ("environment" if os.environ.get(env_name) else "none"),
        })
    return status


def _graybox_web_status(project: Path) -> dict[str, object]:
    project = Path(project).resolve()
    render = graybox_render_status(project)
    spec = render.get("spec") if isinstance(render.get("spec"), dict) else None
    output = str(render.get("output_path") or "")
    provider = next((item for item in _provider_status() if item.get("id") == "minimax_h3"), {
        "id": "minimax_h3",
        "label": "MiniMax H3 · 白模转成片",
        "remote": True,
        "configured": False,
        "source": "none",
    })
    final_dir = project / "graybox" / "final"
    final_items: list[dict[str, object]] = []
    if final_dir.is_dir():
        for metadata_path in sorted(final_dir.glob("*.json"), reverse=True):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(metadata, dict):
                continue
            relative = str(metadata.get("output") or "")
            media = project / relative if relative else None
            if not media or not media.is_file():
                continue
            final_items.append({
                **metadata,
                "media_url": _media_url(project, relative),
                "metadata": _relative(project, metadata_path),
            })
    return {
        "project_id": project.name,
        "blender_installed": bool(render.get("blender_installed")),
        "blender_path": str(render.get("blender_path") or ""),
        "spec_ready": bool(render.get("spec_ready")),
        "spec": spec,
        "render": {
            "status": str(render.get("status") or ("READY" if render.get("output_ready") else "NOT_STARTED")),
            "step": str(render.get("step") or ""),
            "detail": str(render.get("detail") or ""),
            "output_ready": bool(render.get("output_ready")),
            "render_stale": bool(render.get("render_stale")),
            "spec_sha256": str(render.get("spec_sha256") or ""),
            "output_path": output,
            "output_bytes": int(render.get("output_bytes") or 0),
            "media_url": _media_url(project, output) if output and render.get("output_ready") else "",
            "log_path": str(render.get("log_path") or ""),
        },
        "minimax": provider,
        "default_prompt": str(((spec or {}).get("ai_video") or {}).get("prompt") or ""),
        "final_items": final_items[:8],
    }


def _generate_graybox_final(project: Path, payload: dict[str, object]) -> dict[str, object]:
    if payload.get("confirm_billable") is not True:
        raise ValueError("MiniMax H3 远程生成需要 confirm_billable=true")
    if payload.get("upload_authorized") is not True:
        raise ValueError("上传白模参考视频前需要 upload_authorized=true")
    state = graybox_render_status(project)
    if not state.get("output_ready"):
        raise ValueError("Blender 白模尚未生成完成")
    relative = str(state.get("output_path") or "")
    reference_video = project / relative
    if not reference_video.is_file():
        raise ValueError("白模参考视频不存在")

    spec = load_graybox_spec(project)
    review = spec.get("review") if isinstance(spec.get("review"), dict) else {}
    if str(review.get("status") or "").upper() != "APPROVED":
        raise ValueError("Blender 白模必须先人工审核通过，才能进入 MiniMax H3 最终生成")
    prompt = str(payload.get("prompt") or ((spec.get("ai_video") or {}).get("prompt") or "")).strip()
    if not prompt:
        raise ValueError("MiniMax H3 prompt 不能为空")
    model = str(payload.get("model") or "MiniMax-H3").strip()
    resolution = str(payload.get("resolution") or "768P").strip().upper()
    if resolution not in {"768P", "2K"}:
        raise ValueError("MiniMax H3 resolution must be 768P or 2K")
    api_key = RUNTIME_KEYS.get("minimax_h3") or os.environ.get(KEY_ENV["minimax_h3"])
    if not api_key:
        raise ValueError("请先在白模工作流中配置 MiniMax API Key")

    final_dir = project / "graybox" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 100000:05d}"
    output = final_dir / f"{stamp}-minimax-h3.mp4"
    request = VideoGenerationRequest(
        image_paths=(),
        reference_video_paths=(reference_video.resolve(),),
        output_path=output,
        shot_duration_seconds=float(spec.get("duration_seconds") or 8),
        fps=int(spec.get("fps") or 24),
        width=int(spec.get("width") or 720),
        height=int(spec.get("height") or 1280),
        prompt_text=prompt,
        model=model,
    )
    result = MiniMaxH3Video(api_key=str(api_key), resolution=resolution).generate(request)
    output_relative = _relative(project, result.output_path)
    metadata = {
        "schema_version": 1,
        "provider": result.provider,
        "model": model,
        "resolution": resolution,
        "task_id": result.task_id,
        "duration_seconds": result.duration_seconds,
        "shot_spec_id": str(spec.get("id") or ""),
        "reference_video": relative,
        "prompt": prompt,
        "confirm_billable": True,
        "upload_authorized": True,
        "output": output_relative,
        "review_status": "PENDING",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    metadata_path = output.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        **metadata,
        "media_url": _media_url(project, output_relative),
        "metadata": _relative(project, metadata_path),
    }


def _integration_status() -> list[dict[str, object]]:
    runtime = RUNTIME_INTEGRATIONS.get("arcreel", {})
    local_sidecar = ROOT / "integrations" / "arcreel" / "compose.yml"
    paused_marker = ROOT / "integrations" / "arcreel" / "PAUSED"
    base_url = runtime.get("base_url") or os.environ.get("ARCREEL_BASE_URL", "") or ("http://127.0.0.1:1241" if local_sidecar.is_file() else "")
    api_key = runtime.get("api_key") or os.environ.get("ARCREEL_API_KEY")
    status: dict[str, object] = {
        "id": "arcreel",
        "label": "ArcReel 工作台",
        "configured": bool(base_url),
        "connected": False,
        "base_url": base_url,
        "source": "session" if runtime.get("base_url") else ("environment" if os.environ.get("ARCREEL_BASE_URL") else ("local_sidecar" if base_url else "none")),
        "license": "AGPL-3.0",
        "attribution": "Powered by ArcReel — https://github.com/ArcReel/ArcReel",
    }
    if paused_marker.is_file() and not runtime.get("base_url") and not os.environ.get("ARCREEL_BASE_URL"):
        status.update(paused=True, detail="已按当前项目策略暂停；运行数据仍保留")
        return [status]
    if not base_url:
        status["detail"] = "尚未配置独立 ArcReel 服务地址"
        return [status]
    try:
        client = ArcReelWorkspace(base_url, api_key=api_key, timeout_seconds=0.8)
        health = client.health()
        auth = client.auth_status()
        project_names = client.project_names()
        status.update(connected=True, health=str(health.get("status") or "ok"), auth_enabled=bool(auth.get("enabled")), project_count=len(project_names), projects=project_names, detail=f"独立服务连接正常 · {len(project_names)} 个镜像项目")
    except ArcReelError as error:
        status["detail"] = str(error)
    return [status]


def _character_asset_inventory(project: Path) -> list[dict[str, object]]:
    root = project / "assets" / "characters"
    if not root.is_dir():
        return []
    manifest_path = project / "lookdev" / "generation-manifest.json"
    asset_ids: dict[str, str] = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            asset_ids = {str(item.get("path")): str(item.get("asset_id")) for item in manifest.get("assets", []) if isinstance(item, dict)}
        except (OSError, json.JSONDecodeError):
            asset_ids = {}
    result = []
    for path in sorted(root.rglob("*.png")):
        relative = _relative(project, path)
        asset_id = asset_ids.get(relative, "")
        if not asset_id:
            continue
        stem = path.stem.lower()
        view = next((name.upper() for name in ("front", "side", "back", "anchor", "closeup") if name in stem), "REFERENCE")
        result.append({
            "asset_id": asset_id,
            "path": relative,
            "name": path.name,
            "character_id": path.parent.name,
            "view": view,
            "media_url": f"/media/{project.name}/{relative}",
        })
    return result


def _character_rig_inventory(project: Path) -> dict[str, object]:
    """Return the local, review-gated character rigs exposed by the project."""
    manifest_path = project / "visual-bible" / "character-rigs.json"
    if not manifest_path.is_file():
        return {"project_id": project.name, "rigs": [], "count": 0}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"project_id": project.name, "rigs": [], "count": 0}
    rigs = payload.get("rigs", []) if isinstance(payload, dict) else []
    if not isinstance(rigs, list):
        rigs = []
    enriched = []
    for rig in rigs:
        if isinstance(rig, dict):
            item = dict(rig)
            item["validation"] = validate_rig(project, item)
            enriched.append(item)
    return {"project_id": project.name, "schema_version": payload.get("schema_version", 1), "rigs": enriched, "count": len(enriched)}


def _rig_v2_workspace(project: Path, character_id: str) -> dict[str, object]:
    rigs = _character_rig_inventory(project).get("rigs", [])
    rig = next((item for item in rigs if str(item.get("character_id")) == character_id), None)
    if not rig:
        raise ValueError("character V1 Rig is not registered")
    source_path = str(rig.get("source_path") or "")
    source_asset_id = str(rig.get("source_asset_id") or "")
    if not source_path or not source_asset_id:
        raise ValueError("character Rig has no source reference")
    source = project / source_path
    if not source.is_file():
        raise ValueError("character source image is missing")
    canvas = rig.get("canvas") if isinstance(rig.get("canvas"), dict) else {}
    profile = "GODOT_UPPER_BODY_IK"
    required_layers = [
        "head", "torso",
        "upper_arm_l", "forearm_l", "hand_l",
        "upper_arm_r", "forearm_r", "hand_r",
    ]
    work_dir = project / "visual-bible" / "rig-v2-work"
    work_path = work_dir / f"{character_id.lower()}-{profile.lower()}.json"
    existing = None
    if work_path.is_file():
        try:
            existing = json.loads(work_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
    readiness = godot_rig_readiness_summary(project)
    character_readiness = next(
        (item for item in readiness.get("rigs", []) if item.get("character_id") == character_id),
        None,
    )
    return {
        "project_id": project.name,
        "character_id": character_id,
        "character_name": str(rig.get("character_name") or character_id),
        "source_asset_id": source_asset_id,
        "source_path": source_path,
        "source_url": f"/media/{project.name}/{source_path}",
        "canvas": {
            "width": int(canvas.get("width", 0)),
            "height": int(canvas.get("height", 0)),
        },
        "profile": profile,
        "rig_id": f"RIG2-{character_id}-UPPER-V1",
        "required_layers": required_layers,
        "existing": existing,
        "readiness": character_readiness,
    }


EPISODE_REVIEW_CHECKS = ("story", "picture", "audio", "subtitles")
REVIEW_CHECK_STATUSES = {"PENDING", "PASS", "CHANGES_REQUESTED"}


def _episode_master_inventory(project: Path) -> dict[str, object]:
    """Expose local episode masters with browser-safe media links and review defaults."""
    path = project / "renders" / "episodes" / "episode-masters.json"
    if not path.is_file():
        return {"schema_version": 1, "project_id": project.name, "status": "NOT_RUN", "episode_count": 0, "episodes": [], "human_review": {"required": True, "status": "PENDING"}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("episodes"), list):
        raise ValueError("episode master manifest is invalid")
    result = deepcopy(payload)
    enriched = []
    for episode in result["episodes"]:
        if not isinstance(episode, dict):
            continue
        item = dict(episode)
        review = item.get("human_review") if isinstance(item.get("human_review"), dict) else {}
        checks = review.get("checks") if isinstance(review.get("checks"), dict) else {}
        item["human_review"] = {
            "required": True,
            "status": str(review.get("status") or "PENDING"),
            "checks": {key: str(checks.get(key) or "PENDING") for key in EPISODE_REVIEW_CHECKS},
            "reviewed_at": review.get("reviewed_at"),
            "reviewed_by": review.get("reviewed_by"),
            "note": str(review.get("note") or ""),
        }
        output = str(item.get("output") or "")
        if output and (project / output).is_file():
            item["media_url"] = f"/media/{project.name}/{output}"
        subtitle = str(item.get("subtitle") or "")
        if subtitle and (project / subtitle).is_file():
            item["subtitle_url"] = f"/media/{project.name}/{subtitle}"
        episode_id = str(item.get("episode_id") or "").lower()
        qc_frame = f"renders/episodes/qc-frames/{episode_id}-speech-check.png"
        if episode_id and (project / qc_frame).is_file():
            item["qc_frame_url"] = f"/media/{project.name}/{qc_frame}"
        enriched.append(item)
    result["episodes"] = enriched
    result["episode_count"] = len(enriched)
    qc_path = project / "renders" / "episodes" / "episode-technical-qc.json"
    if qc_path.is_file():
        qc = json.loads(qc_path.read_text(encoding="utf-8"))
        result["technical_qc"] = {
            "status": qc.get("status", "NOT_RUN"),
            "passed_episode_count": qc.get("passed_episode_count", 0),
            "episode_count": qc.get("episode_count", 0),
            "generated_at": qc.get("generated_at"),
        }
    return result


def _update_episode_master_review(project: Path, payload: dict[str, object]) -> dict[str, object]:
    path = project / "renders" / "episodes" / "episode-masters.json"
    if not path.is_file():
        raise ValueError("episode masters have not been rendered")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    episode_id = str(payload.get("episode_id") or "").strip()
    episode = next((item for item in manifest.get("episodes", []) if str(item.get("episode_id")) == episode_id), None)
    if not episode:
        raise ValueError("episode_id does not exist in episode masters")
    checks = payload.get("checks")
    if not isinstance(checks, dict) or any(checks.get(key) not in REVIEW_CHECK_STATUSES for key in EPISODE_REVIEW_CHECKS):
        raise ValueError("checks must contain story, picture, audio and subtitles with valid statuses")
    reviewer = str(payload.get("reviewer") or "").strip()
    if any(checks[key] != "PENDING" for key in EPISODE_REVIEW_CHECKS) and not reviewer:
        raise ValueError("reviewer is required when recording review results")
    if all(checks[key] == "PASS" for key in EPISODE_REVIEW_CHECKS):
        status = "APPROVED"
    elif any(checks[key] == "CHANGES_REQUESTED" for key in EPISODE_REVIEW_CHECKS):
        status = "CHANGES_REQUESTED"
    else:
        status = "PENDING"
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    episode["human_review"] = {
        "required": True,
        "status": status,
        "checks": {key: checks[key] for key in EPISODE_REVIEW_CHECKS},
        "reviewed_at": timestamp,
        "reviewed_by": reviewer,
        "note": str(payload.get("note") or "").strip(),
    }
    statuses = [str(item.get("human_review", {}).get("status") or "PENDING") for item in manifest.get("episodes", [])]
    aggregate_status = "APPROVED" if statuses and all(value == "APPROVED" for value in statuses) else "CHANGES_REQUESTED" if any(value == "CHANGES_REQUESTED" for value in statuses) else "PENDING"
    manifest["human_review"] = {"required": True, "status": aggregate_status, "reviewed_at": timestamp, "reviewed_by": reviewer if aggregate_status == "APPROVED" else None}
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return next(item for item in _episode_master_inventory(project)["episodes"] if item["episode_id"] == episode_id)


def _provider_motion_test_inventory(project: Path) -> dict[str, object]:
    path = project / "provider-tests" / "s01e001" / "motion-provider-tests.json"
    if not path.is_file():
        return {"schema_version": 1, "project_id": project.name, "status": "NOT_PREPARED", "remote_execution": "BLOCKED_PENDING_AUTHORIZATION", "tests": [], "test_count": 0}
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = deepcopy(payload)
    tests = []
    for raw in result.get("tests", []):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        frame = str(item.get("start_frame") or "")
        if frame and (project / frame).is_file():
            item["start_frame_url"] = f"/media/{project.name}/{frame}"
        output = str(item.get("output_path") or "")
        if output and (project / output).is_file():
            item["media_url"] = f"/media/{project.name}/{output}"
        tests.append(item)
    result["tests"] = tests
    result["test_count"] = len(tests)
    return result


def _final_shot_review(project: Path) -> dict[str, object]:
    path = project / "dynamic" / "final-shot-review.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    renders = sorted((project / "renders").glob("*-final-*.mp4")) if (project / "renders").is_dir() else []
    latest = renders[-1] if renders else None
    return {"schema_version": 1, "project_id": project.name, "shot_id": "SHOT-S01E002-SC002-001", "rig_id": "RIG-CHR-JHY-BAIHUA-FRONT-V1", "character_id": "CHR-JHY-BAIHUA", "video_path": _relative(project, latest) if latest else None, "checks": {"sound": "PENDING", "subtitles": "PENDING", "mouth": "PENDING"}, "status": "PENDING", "reviewer": None, "note": "", "updated_at": None}


def _rig_coverage(project: Path) -> dict[str, object]:
    timeline_path = project / "dynamic" / "mouth-cues.json"
    timeline = json.loads(timeline_path.read_text(encoding="utf-8")).get("timeline", []) if timeline_path.is_file() else []
    rigs = _character_rig_inventory(project).get("rigs", [])
    covered_characters = {str(item.get("character_id")) for item in rigs}
    roles: dict[str, dict[str, object]] = {}
    for cue in timeline:
        if not cue.get("speaker_character_id"):
            continue
        character_id = str(cue["speaker_character_id"])
        role = roles.setdefault(character_id, {"character_id": character_id, "shot_ids": [], "shot_count": 0, "rig_ready": character_id in covered_characters})
        role["shot_ids"].append(str(cue.get("shot_id"))); role["shot_count"] = int(role["shot_count"]) + 1
    covered = sum(int(item["shot_count"]) for item in roles.values() if item["rig_ready"])
    total = sum(int(item["shot_count"]) for item in roles.values())
    ordered = sorted(roles.values(), key=lambda item: (-int(item["shot_count"]), str(item["character_id"])))
    return {"project_id": project.name, "covered_shot_count": covered, "total_shot_count": total, "coverage_percent": round(covered / total * 100, 1) if total else 0.0, "roles": ordered, "missing_character_ids": [str(item["character_id"]) for item in ordered if not item["rig_ready"]]}


def _delete_novel_project(project_id: str, *, confirmed: bool) -> dict[str, object]:
    if confirmed is not True:
        raise ValueError("project deletion requires confirm_delete=true")
    project = _safe_project(project_id)
    manifest_path = project / NOVEL_ANIME_MANIFEST
    if not manifest_path.is_file():
        raise ValueError("only novel-anime projects can be deleted from this endpoint")
    manifest = load_novel_anime_project(manifest_path)
    title = str(manifest.get("title") or project.name)

    shutil.rmtree(project)
    if project.exists():
        raise OSError(f"project directory still exists after deletion: {project.name}")
    _NOVEL_PROJECT_CACHE.clear()
    remaining = _novel_anime_projects()
    default_project_id = str(remaining[0].get("directory_id") or "") if remaining else ""
    return {
        "status": "DELETED",
        "project_id": project_id,
        "title": title,
        "default_project_id": default_project_id,
        "remaining_project_count": len(remaining),
        "remaining_project_ids": [str(item.get("directory_id") or "") for item in remaining],
        "deleted_verified": not project.exists(),
    }


class VideoCreatorHandler(BaseHTTPRequestHandler):
    server_version = "VideoCreatorWeb/1.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            return self._serve_file(WEB_ROOT / "index.html", "text/html; charset=utf-8")
        if parsed.path == "/app.js":
            return self._serve_file(WEB_ROOT / "app.js", "text/javascript; charset=utf-8")
        if parsed.path == "/styles.css":
            return self._serve_file(WEB_ROOT / "styles.css", "text/css; charset=utf-8")
        if parsed.path == "/api/health":
            return self._json({"status": "ok", "providers": _provider_status(), "integrations": _integration_status()})
        if parsed.path == "/api/image-studio/status":
            query = {}
            if parsed.query:
                from urllib.parse import parse_qs
                query = parse_qs(parsed.query)
            project_id = str((query.get("project_id") or [""])[0]).strip()
            try:
                project = _safe_project(project_id)
                return self._json(_image_studio_inventory(project))
            except (ValueError, OSError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if parsed.path == "/api/pipeline/preflight":
            query = {}
            if parsed.query:
                from urllib.parse import parse_qs
                query = parse_qs(parsed.query)
            project_id = str((query.get("project_id") or [""])[0]).strip()
            try:
                _safe_project(project_id)
                return self._json(pipeline_preflight(project_id))
            except (ValueError, OSError, PipelineError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if parsed.path == "/api/pipeline/status":
            query = {}
            if parsed.query:
                from urllib.parse import parse_qs
                query = parse_qs(parsed.query)
            project_id = str((query.get("project_id") or [""])[0]).strip()
            try:
                _safe_project(project_id)
                return self._json(pipeline_status(project_id))
            except (ValueError, OSError, PipelineError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if parsed.path == "/api/integrations/arcreel/status":
            return self._json(_integration_status()[0])
        if parsed.path == "/api/integrations/comfyui/status":
            return self._json(_comfyui_image_status())
        if parsed.path == "/api/comfyui/service/status":
            try:
                return self._json(comfyui_service_status(_comfyui_base_url()))
            except (ComfyUIServiceError, ValueError, OSError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if parsed.path == "/api/comfyui/install/status":
            try:
                return self._json(comfyui_install_status())
            except (ComfyUIInstallError, ValueError, OSError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if parsed.path == "/api/comfyui/models/status":
            try:
                return self._json(comfyui_model_status())
            except (ComfyUIModelError, ValueError, OSError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if parsed.path == "/api/comfyui/loras/status":
            try:
                return self._json(comfyui_lora_status())
            except (ComfyUILoraError, ValueError, OSError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if parsed.path == "/api/projects":
            return self._json({"projects": self._projects()})
        if parsed.path == "/api/novel-anime/projects":
            return self._json({"projects": _novel_anime_projects()})
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/readiness", parsed.path)
        if match:
            try:
                project_id = match.group(1)
                _safe_project(project_id)
                summary = next((item for item in _novel_anime_projects() if item["directory_id"] == project_id), None)
                if summary is None:
                    raise ValueError("novel-anime project not found")
            except ValueError as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(_readiness_from_summary(summary))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/workspaces", parsed.path)
        if match:
            try:
                result = _novel_anime_workspaces(match.group(1))
            except ValueError as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/backups", parsed.path)
        if match:
            try:
                result = _backup_inventory(_safe_project(match.group(1)))
            except ValueError as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/sources", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                path = project / CATALOG_RELATIVE_PATH
                if not path.is_file():
                    raise ValueError("novel source catalog not found")
                catalog = load_catalog(path)
            except (ValueError, NovelSourceCatalogError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(catalog)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/source-imports", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
            except ValueError as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json({"project_id": project.name, "imports": _source_import_summaries(project)})
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/story-bible", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                bible = load_bible(project)
            except (ValueError, NovelStoryBibleError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(bible)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/continuity-input/(S\d{2}E\d{3})", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = continuity_input(project, match.group(2))
            except (ValueError, NovelStoryBibleError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/series-plan", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_series_plan(project)
            except (ValueError, NovelSeriesPlanError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/episode-planning", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_episode_planning(project)
            except (ValueError, NovelEpisodePlanningError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/episode-scripts", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_script_package(project)
            except (ValueError, NovelEpisodeScriptError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/story-review", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_story_review(project)
            except (ValueError, NovelStoryReviewError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/visual-bible", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_visual_bible(project)
            except (ValueError, NovelVisualBibleError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/character-designs", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_character_designs(project)
            except (ValueError, NovelCharacterDesignError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/character-assets", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
            except ValueError as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            assets = _character_asset_inventory(project)
            return self._json({"project_id": project.name, "assets": assets, "count": len(assets)})
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/character-rigs", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
            except ValueError as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(_character_rig_inventory(project))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/rig-v2-workspace/([^/]+)", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                return self._json(_rig_v2_workspace(project, unquote(match.group(2))))
            except (ValueError, GodotRigReadinessError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/godot-rig-readiness", parsed.path)
        if match:
            try:
                return self._json(godot_rig_readiness_summary(_safe_project(match.group(1))))
            except (ValueError, GodotRigReadinessError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/timeline-cues", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1)); path = project / "dynamic" / "mouth-cues.json"
                if not path.is_file():
                    return self._json({"project_id": project.name, "timeline": [], "count": 0})
                payload = json.loads(path.read_text(encoding="utf-8"))
                timeline = payload.get("timeline", []) if isinstance(payload, dict) else []
                return self._json({"project_id": project.name, "timeline": timeline, "count": len(timeline), "human_review": payload.get("human_review")})
            except (ValueError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/final-shot-review", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1)); return self._json(_final_shot_review(project))
            except ValueError as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/rig-coverage", parsed.path)
        if match:
            try:
                return self._json(_rig_coverage(_safe_project(match.group(1))))
            except (ValueError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/final-batch", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1)); path = project / "dynamic" / "final-batch.json"
                return self._json(json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"project_id": project.name, "status": "NOT_RUN", "count": 0, "results": []})
            except (ValueError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/episode-masters", parsed.path)
        if match:
            try:
                return self._json(_episode_master_inventory(_safe_project(match.group(1))))
            except (ValueError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/episode-masters/qc", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1)); path = project / "renders" / "episodes" / "episode-technical-qc.json"
                if not path.is_file():
                    return self._json({"project_id": project.name, "status": "NOT_RUN", "episode_count": 0, "episodes": []})
                return self._json(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/provider-motion-tests", parsed.path)
        if match:
            try:
                return self._json(_provider_motion_test_inventory(_safe_project(match.group(1))))
            except (ValueError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/environment-assets", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_environment_assets(project)
            except (ValueError, NovelEnvironmentAssetError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/asset-review", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_asset_review(project)
            except (ValueError, NovelAssetReviewError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/shot-breakdown", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_shot_breakdown(project)
            except (ValueError, NovelShotBreakdownError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/storyboard", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_storyboard(project)
            except (ValueError, NovelStoryboardError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/animatic", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_animatic(project)
            except (ValueError, NovelAnimaticError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/animatic-review", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_animatic_review(project)
            except (ValueError, NovelAnimaticReviewError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/voice-profiles", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_voice_profiles(project)
            except (ValueError, NovelVoiceProfileError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/audio-assets", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_audio_assets(project)
            except (ValueError, NovelAudioAssetError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/audio-mix", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_audio_mix(project)
            except (ValueError, NovelAudioMixError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/dynamic-shots", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_dynamic_shots(project)
            except (ValueError, NovelDynamicShotError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/edit-timelines", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = load_edit_timelines(project)
            except (ValueError, NovelEditTimelineError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/qc", parsed.path)
        if match:
            try:
                result = load_qc_report(_safe_project(match.group(1)))
            except (ValueError, NovelQCError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/qc/compare", parsed.path)
        if match:
            try:
                result = compare_qc(_safe_project(match.group(1)))
            except (ValueError, NovelQCError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/acceptance", parsed.path)
        if match:
            try:
                result = load_acceptance(_safe_project(match.group(1)))
            except (ValueError, NovelAcceptanceError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(result)
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/repository", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                stats = repository_stats(project)
                if stats is None:
                    raise ValueError("novel-anime repository is not initialized")
            except ValueError as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json({"project_id": project.name, "stats": stats})
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/runtime", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                stats = runtime_stats(project)
                if stats is None:
                    raise ValueError("novel-anime runtime is not initialized")
            except ValueError as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json({"project_id": project.name, "stats": stats})
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/jobs", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                jobs = NovelAnimeRuntime(project).list_jobs()
            except (ValueError, NovelAnimeRuntimeError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json({"project_id": project.name, "jobs": jobs})
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/impact/([A-Za-z0-9-]+)", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                impact = NovelAnimeRepository(project).impact([match.group(2)])
            except (ValueError, NovelAnimeRepositoryError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json({"project_id": project.name, "root": match.group(2), "impact": impact})
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/graybox", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                return self._json(_graybox_web_status(project))
            except (ValueError, GrayboxShotSpecError, GrayboxRenderError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
                manifest = project / NOVEL_ANIME_MANIFEST
                if not manifest.is_file():
                    raise ValueError("novel-anime project manifest not found")
                payload = load_novel_anime_project(manifest)
            except (ValueError, NovelAnimeProjectError) as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json(payload)
        match = re.fullmatch(r"/api/projects/([^/]+)", parsed.path)
        if match:
            try:
                project = _safe_project(match.group(1))
            except ValueError as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._json({"id": project.name, "files": _media_files(project), "episodes": _episode_metadata(project), "providers": _provider_status()})
        match = re.fullmatch(r"/media/([^/]+)/(.+)", parsed.path)
        if match:
            try:
                path = _safe_project_file(match.group(1), match.group(2))
            except ValueError as error:
                return self._error(HTTPStatus.NOT_FOUND, str(error))
            return self._serve_file(path, mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        return self._error(HTTPStatus.NOT_FOUND, "route not found")

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/novel-anime/import":
            try:
                payload = self._read_json(max_bytes=MAX_WEB_UPLOAD_BYTES)
                result = create_project_from_web_upload(
                    PROJECTS_ROOT,
                    title=str(payload.get("title") or ""),
                    author=str(payload.get("author") or ""),
                    episode_count=int(payload.get("episode_count") or 5),
                    rights_mode=str(payload.get("rights_mode") or "TECHNICAL_TEST"),
                    rights_confirmed=payload.get("rights_confirmed") is True,
                    source_name=str(payload.get("source_name") or "novel.txt"),
                    source_text=str(payload.get("source_text") or ""),
                )
                _NOVEL_PROJECT_CACHE.clear()
                return self._json(result, HTTPStatus.CREATED)
            except (NovelWebImportError, ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
            except Exception as error:
                return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"novel import failed: {error}")
        if route == "/api/novel-anime/delete":
            try:
                payload = self._read_json()
                result = _delete_novel_project(
                    str(payload.get("project_id") or ""),
                    confirmed=payload.get("confirm_delete") is True,
                )
                return self._json(result)
            except (ValueError, NovelAnimeProjectError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route == "/api/image-studio/character-bootstrap":
            try:
                payload = self._read_json()
                project = _safe_project(str(payload.get("project_id") or ""))
                result = recover_project_characters(project)
                _NOVEL_PROJECT_CACHE.clear()
                status = HTTPStatus.OK if result.get("status") == "READY" else HTTPStatus.CONFLICT
                return self._json({
                    **result,
                    "project_id": project.name,
                    "full_text_stored": False,
                }, status)
            except (NovelWebImportError, ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route == "/api/comfyui/install/start":
            try:
                return self._json(start_comfyui_install(), HTTPStatus.ACCEPTED)
            except (ComfyUIInstallError, ValueError, OSError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route == "/api/comfyui/models/install/start":
            try:
                return self._json(start_comfyui_model_install(), HTTPStatus.ACCEPTED)
            except (ComfyUIModelError, ValueError, OSError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route == "/api/comfyui/loras/install/start":
            try:
                payload = self._read_json()
                lora_id = str(payload.get("lora_id") or "").strip() or "sdxl-chinese-style-illustration"
                return self._json(start_comfyui_lora_install(lora_id), HTTPStatus.ACCEPTED)
            except (ComfyUILoraError, ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route in {"/api/comfyui/service/start", "/api/comfyui/service/stop"}:
            try:
                if route.endswith("/start"):
                    result = start_comfyui_service(_comfyui_base_url())
                else:
                    result = stop_comfyui_service(_comfyui_base_url())
                return self._json(result)
            except (ComfyUIServiceError, ValueError, OSError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route == "/api/settings/keys":
            try:
                return self._save_key()
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route == "/api/settings/integrations":
            try:
                return self._save_integration()
            except (ValueError, KeyError, TypeError, json.JSONDecodeError, ArcReelError, ComfyUIImageError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route == "/api/pipeline/run":
            try:
                payload = self._read_json()
                project_id = str(payload.get("project_id") or "").strip()
                _safe_project(project_id)
                result = run_pipeline(
                    project_id,
                    dry_run=payload.get("dry_run") is not False,
                    confirm_billable=payload.get("confirm_billable") is True,
                    preferred_image_provider=str(payload.get("image_provider") or "AUTO"),
                )
                return self._json(result, HTTPStatus.CREATED)
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError, PipelineError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route == "/api/pipeline/review":
            try:
                payload = self._read_json()
                project_id = str(payload.get("project_id") or "").strip()
                _safe_project(project_id)
                result = update_pipeline_review(
                    project_id,
                    str(payload.get("status") or ""),
                    note=str(payload.get("note") or ""),
                    reviewer="human-web",
                )
                return self._json(result)
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError, PipelineError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route == "/api/image-studio/review":
            try:
                payload = self._read_json()
                project = _safe_project(str(payload.get("project_id") or ""))
                result = _update_image_studio_review(project, payload)
                return self._json(result)
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route == "/api/image-studio/character-candidates":
            try:
                payload = self._read_json(max_bytes=MAX_WEB_UPLOAD_BYTES)
                project = _safe_project(str(payload.get("project_id") or ""))
                result = _reanalyze_project_character_candidates(
                    project,
                    source_name=str(payload.get("source_name") or "novel.txt"),
                    source_text=str(payload.get("source_text") or ""),
                )
                _NOVEL_PROJECT_CACHE.clear()
                return self._json(result, HTTPStatus.CREATED)
            except (
                ValueError,
                OSError,
                KeyError,
                TypeError,
                json.JSONDecodeError,
                NovelAnimeProjectError,
                NovelSourceIngestError,
                NovelCharacterCandidateError,
            ) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/graybox/spec", route)
        if match:
            try:
                project = _safe_project(match.group(1))
                ensure_graybox_spec(project)
                return self._json(_graybox_web_status(project), HTTPStatus.CREATED)
            except (ValueError, GrayboxShotSpecError, GrayboxRenderError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/graybox/adjust", route)
        if match:
            try:
                payload = self._read_json(max_bytes=64 * 1024)
                project = _safe_project(match.group(1))
                result = adjust_graybox_spec(project, str(payload.get("instruction") or ""))
                return self._json({**result, **_graybox_web_status(project)}, HTTPStatus.CREATED)
            except (ValueError, GrayboxShotSpecError, GrayboxRenderError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/graybox/review", route)
        if match:
            try:
                payload = self._read_json(max_bytes=64 * 1024)
                project = _safe_project(match.group(1))
                review_status = str(payload.get("status") or "").strip().upper()
                if review_status == "APPROVED":
                    current_render = graybox_render_status(project)
                    if not current_render.get("output_ready"):
                        raise ValueError("必须先生成与当前 Shot Spec 匹配的 Blender 白模，才能标记为通过")
                result = review_graybox_spec(
                    project,
                    review_status,
                    str(payload.get("note") or ""),
                )
                return self._json({**result, **_graybox_web_status(project)}, HTTPStatus.CREATED)
            except (ValueError, GrayboxShotSpecError, GrayboxRenderError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/graybox/render", route)
        if match:
            try:
                project = _safe_project(match.group(1))
                ensure_graybox_spec(project)
                result = start_graybox_render(project)
                return self._json({**result, "project_id": project.name}, HTTPStatus.ACCEPTED)
            except (ValueError, GrayboxShotSpecError, GrayboxRenderError, OSError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/graybox/final", route)
        if match:
            try:
                project = _safe_project(match.group(1))
                payload = self._read_json(max_bytes=256 * 1024)
                return self._json(_generate_graybox_final(project, payload), HTTPStatus.CREATED)
            except (ValueError, GrayboxShotSpecError, GrayboxRenderError, VideoGenerationError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
            except Exception as error:
                return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"graybox final generation failed: {error}")
        if route in {"/api/image-studio/character-bible", "/api/image-studio/keyframe"}:
            try:
                payload = self._read_json()
                project = _safe_project(str(payload.get("project_id") or ""))
                artifact_type = "character_bible" if route.endswith("/character-bible") else "keyframe"
                result = _generate_image_studio_asset(
                    project,
                    artifact_type=artifact_type,
                    custom_prompt=str(payload.get("custom_prompt") or ""),
                    confirm_billable=payload.get("confirm_billable") is True,
                    upload_authorized=payload.get("upload_authorized") is True,
                    preferred_provider=str(payload.get("provider_preference") or "AUTO"),
                    style_preset=str(payload.get("style_preset") or ""),
                    comfyui_client_id=str(payload.get("comfyui_client_id") or "").strip(),
                )
                return self._json(result, HTTPStatus.CREATED)
            except (ValueError, OpenAIImageError, ComfyUIImageError, ImageProviderRouteError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
            except Exception as error:
                return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"image generation failed: {error}")
        if route == "/api/storyboard/local":
            try:
                payload = self._read_json()
                response = self._generate_local_storyboard(payload)
                self._json(response, HTTPStatus.CREATED)
            except (LocalStoryboardError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
            except Exception as error:
                return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"storyboard failed: {error}")
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/godot-25d-preview", route)
        if match:
            try:
                payload = self._read_json()
                project = _safe_project(match.group(1))
                character_id = str(payload.get("character_id") or "").strip()
                seconds = float(payload.get("seconds") or 4.0)
                result = render_godot_25d_preview(project, character_id, duration_seconds=seconds, fps=24)
                output_path = Path(result["output"])
                relative = _relative(project, output_path)
                return self._json(
                    {
                        "status": "created",
                        "provider": result["provider"],
                        "character_id": character_id,
                        "rig_id": result["rig_id"],
                        "duration_seconds": result["duration_seconds"],
                        "fps": result["fps"],
                        "features": result["features"],
                        "human_review": result["human_review"],
                        "output": relative,
                        "media_url": f"/media/{project.name}/{relative}",
                    },
                    HTTPStatus.CREATED,
                )
            except (ValueError, Godot25DPreviewError, OSError, RuntimeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))

        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/rig-v2-auto-draft", route)
        if match:
            try:
                payload = self._read_json()
                project = _safe_project(match.group(1))
                character_id = str(payload.get("character_id") or "").strip()
                workspace = _rig_v2_workspace(project, character_id)
                draft = propose_rig_v2_upper_body(project, str(workspace["source_path"]))
                return self._json(
                    {
                        "status": "drafted",
                        "character_id": character_id,
                        "rig_id": workspace["rig_id"],
                        "profile": workspace["profile"],
                        "draft": draft,
                    },
                    HTTPStatus.CREATED,
                )
            except (ValueError, RigV2AutoDraftError, OSError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))

        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/rig-v2-auto-generate", route)
        if match:
            try:
                payload = self._read_json()
                project = _safe_project(match.group(1))
                character_id = str(payload.get("character_id") or "").strip()
                workspace = _rig_v2_workspace(project, character_id)
                draft = propose_rig_v2_upper_body(project, str(workspace["source_path"]))
                result = segment_rig_v2_layers(
                    project,
                    str(workspace["source_path"]),
                    character_id,
                    str(workspace["character_name"]),
                    str(workspace["source_asset_id"]),
                    str(workspace["rig_id"]),
                    str(workspace["profile"]),
                    draft["layers"],
                    finalize=True,
                )
                readiness = godot_rig_readiness_summary(project)
                return self._json(
                    {
                        "status": "created",
                        "provider": draft["provider"],
                        "automatic": True,
                        "human_review": "PENDING",
                        "result": result,
                        "readiness": readiness,
                    },
                    HTTPStatus.CREATED,
                )
            except (
                ValueError,
                RigV2AutoDraftError,
                RigV2SegmentError,
                GodotRigReadinessError,
                OSError,
                RuntimeError,
            ) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))

        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/rig-v2-segment", route)
        if match:
            try:
                payload = self._read_json()
                project = _safe_project(match.group(1))
                character_id = str(payload.get("character_id") or "").strip()
                workspace = _rig_v2_workspace(project, character_id)
                layers = payload.get("layers")
                if not isinstance(layers, dict):
                    raise ValueError("layers must be an object")
                result = segment_rig_v2_layers(
                    project,
                    str(workspace["source_path"]),
                    character_id,
                    str(workspace["character_name"]),
                    str(workspace["source_asset_id"]),
                    str(workspace["rig_id"]),
                    str(workspace["profile"]),
                    layers,
                    finalize=True,
                )
                readiness = godot_rig_readiness_summary(project)
                return self._json(
                    {
                        "status": "created",
                        "result": result,
                        "readiness": readiness,
                    },
                    HTTPStatus.CREATED,
                )
            except (ValueError, RigV2SegmentError, GodotRigReadinessError, OSError, RuntimeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/character-motion-test", route)
        if match:
            try:
                payload = self._read_json()
                project = _safe_project(match.group(1))
                asset_path = str(payload.get("asset_path") or "")
                inventory = _character_asset_inventory(project)
                allowed = {str(item["path"]) for item in inventory}
                if asset_path not in allowed:
                    raise ValueError("character asset is not registered in the local inventory")
                seconds = float(payload.get("seconds") or 4.0)
                if seconds < 2 or seconds > 8:
                    raise ValueError("preview duration must be between 2 and 8 seconds")
                background, background_asset_id = _background_for_shot(project, shot_id)
                stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 100000:05d}"
                output = project / "lookdev" / f"{Path(asset_path).stem}-motion-preview-{stamp}.mp4"
                video, keyframe = render_local_motion_test(project, background, project / asset_path, output, seconds, 24)
                character_asset_id = next((str(item["asset_id"]) for item in inventory if item["path"] == asset_path), "")
                if not character_asset_id:
                    raise ValueError("character asset must have a registered asset ID before preview rendering")
                repository = NovelAnimeRepository(project)
                source_assets = (character_asset_id, "AST-LOC-JHY-KUNLUN-NIGHT")
                video_asset = repository.register_asset(f"AST-VIDEO-JHY-BAIHUA-PREVIEW-{stamp.replace('-', '')}", "video", video, metadata={"title": "百花仙子本地动作预览", "provider": "local_motion", "duration_seconds": seconds, "fps": 24}, source_entity_ids=source_assets)
                keyframe_asset = repository.register_asset(f"AST-KEYFRAME-JHY-BAIHUA-PREVIEW-{stamp.replace('-', '')}", "keyframe", keyframe, metadata={"title": "百花仙子本地动作预览首帧", "provider": "local_motion"}, source_entity_ids=source_assets)
                relative_video = _relative(project, video)
                return self._json({"status": "created", "provider": "local_motion", "output": relative_video, "keyframe": _relative(project, keyframe), "video_asset": video_asset, "keyframe_asset": keyframe_asset, "media_url": f"/media/{project.name}/{relative_video}", "duration_seconds": seconds}, HTTPStatus.CREATED)
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/character-rig-motion-test", route)
        if match:
            try:
                payload = self._read_json(); project = _safe_project(match.group(1))
                rig_id = str(payload.get("rig_id") or "RIG-CHR-JHY-BAIHUA-FRONT-V1")
                rigs = _character_rig_inventory(project)["rigs"]
                rig = next((item for item in rigs if item.get("id") == rig_id), None)
                if not rig:
                    raise ValueError("character Rig is not registered")
                seconds = float(payload.get("seconds") or 4.0)
                if seconds < 2 or seconds > 8:
                    raise ValueError("preview duration must be between 2 and 8 seconds")
                layer_paths = [project / str(layer["path"]) for layer in rig.get("layers", []) if layer.get("name") in {"head", "torso", "lower"}]
                if len(layer_paths) != 3:
                    raise ValueError("Rig must contain head, torso, and lower layers")
                background = project / "assets" / "locations" / "LOCN-JHY-KUNLUN" / "kunlun-yaochi-night-v1.png"
                stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 100000:05d}"
                output = project / "lookdev" / f"baihua-rig-motion-preview-{stamp}.mp4"
                expression = str(payload.get("expression") or "neutral")
                mouth_cues = payload.get("mouth_cues") if isinstance(payload.get("mouth_cues"), list) else []
                video, keyframe = render_character_rig_preview(project, background, layer_paths, output, seconds, 24, expression, mouth_cues)
                repository = NovelAnimeRepository(project)
                source_assets = tuple([str(layer["asset_id"]) for layer in rig["layers"]] + ["AST-LOC-JHY-KUNLUN-NIGHT"])
                video_asset = repository.register_asset(f"AST-VIDEO-JHY-BAIHUA-RIG-{stamp.replace('-', '')}", "video", video, metadata={"title": "百花仙子 Rig 分层动作预览", "provider": "local_rig_motion", "duration_seconds": seconds, "fps": 24, "rig_id": rig_id}, source_entity_ids=source_assets)
                keyframe_asset = repository.register_asset(f"AST-KEYFRAME-JHY-BAIHUA-RIG-{stamp.replace('-', '')}", "keyframe", keyframe, metadata={"title": "百花仙子 Rig 分层预览首帧", "provider": "local_rig_motion", "rig_id": rig_id}, source_entity_ids=source_assets)
                relative_video = _relative(project, video)
                return self._json({"status": "created", "provider": "local_rig_motion", "output": relative_video, "keyframe": _relative(project, keyframe), "video_asset": video_asset, "keyframe_asset": keyframe_asset, "media_url": f"/media/{project.name}/{relative_video}", "duration_seconds": seconds, "rig_id": rig_id}, HTTPStatus.CREATED)
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError, NovelAnimeRepositoryError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/storyboard-rig-preview", route)
        if match:
            try:
                payload = self._read_json(); project = _safe_project(match.group(1)); shot_id = str(payload.get("shot_id") or "")
                storyboard_path = project / "storyboard" / "storyboard.json"
                storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
                shot = next((item for item in storyboard.get("frames", []) if item.get("shot_id") == shot_id), None)
                if not shot:
                    raise ValueError("shot_id is not present in storyboard")
                seconds = min(8.0, max(2.0, float(payload.get("seconds") or shot.get("duration_seconds") or 4.0)))
                rig_payload = _character_rig_inventory(project); rigs = rig_payload.get("rigs", [])
                rig_id = str(payload.get("rig_id") or (rigs[0].get("id") if rigs else ""))
                rig = next((item for item in rigs if item.get("id") == rig_id), None)
                if not rig:
                    raise ValueError("no local Rig is available for this storyboard preview")
                layer_paths = [project / str(layer["path"]) for layer in rig.get("layers", []) if layer.get("name") in {"head", "torso", "lower"}]
                stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 100000:05d}"
                output = project / "lookdev" / f"{shot_id.lower()}-rig-preview-{stamp}.mp4"
                background = project / "assets" / "locations" / "LOCN-JHY-KUNLUN" / "kunlun-yaochi-night-v1.png"
                cue_payload = payload.get("mouth_cues") if isinstance(payload.get("mouth_cues"), list) else None
                if cue_payload is None:
                    cue_path = project / "dynamic" / "mouth-cues.json"
                    if cue_path.is_file():
                        compiled = json.loads(cue_path.read_text(encoding="utf-8"))
                        lines = compiled.get("shots", {}).get(shot_id, [])
                        cue_payload = lines[0].get("mouth_cues", []) if lines else []
                video, keyframe = render_character_rig_preview(project, background, layer_paths, output, seconds, 24, str(payload.get("expression") or "neutral"), cue_payload or [], _particle_effect(background_asset_id))
                timeline_cue = next((item for item in (compiled.get("timeline", []) if 'compiled' in locals() else []) if item.get("shot_id") == shot_id), None)
                return self._json({"status": "created", "provider": "local_rig_motion", "shot_id": shot_id, "rig_id": rig_id, "output": _relative(project, video), "keyframe": _relative(project, keyframe), "media_url": f"/media/{project.name}/{_relative(project, video)}", "duration_seconds": seconds, "timeline_cue": timeline_cue}, HTTPStatus.CREATED)
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/storyboard-final-preview", route)
        if match:
            try:
                payload = self._read_json(); project = _safe_project(match.group(1)); shot_id = str(payload.get("shot_id") or "")
                timeline_path = project / "dynamic" / "mouth-cues.json"; timeline_payload = json.loads(timeline_path.read_text(encoding="utf-8"))
                cue = next((item for item in timeline_payload.get("timeline", []) if item.get("shot_id") == shot_id), None)
                if not cue or not cue.get("audio", {}).get("mix_asset_id"):
                    raise ValueError("shot has no registered timeline mix")
                rigs = _character_rig_inventory(project).get("rigs", []); rig_id = str(payload.get("rig_id") or (rigs[0].get("id") if rigs else "")); rig = next((item for item in rigs if item.get("id") == rig_id), None)
                if not rig:
                    raise ValueError("no local Rig is available")
                seconds = min(8.0, max(2.0, float(payload.get("seconds") or cue.get("end_seconds") or 4.0)))
                layers = [project / str(layer["path"]) for layer in rig.get("layers", []) if layer.get("name") in {"head", "torso", "lower"}]
                background, background_asset_id = _background_for_shot(project, shot_id); stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 100000:05d}"
                draft = project / "lookdev" / f"{shot_id.lower()}-draft-{stamp}.mp4"; final = project / "renders" / f"{shot_id.lower()}-final-{stamp}.mp4"
                video, _ = render_character_rig_preview(project, background, layers, draft, seconds, 24, str(payload.get("expression") or "neutral"), cue.get("mouth_cues", []), _particle_effect(background_asset_id))
                audio_path = project / str(cue["audio"]["path"])
                mux_timeline_shot(video, audio_path, final)
                repository = NovelAnimeRepository(project); scene_id = shot_id.removeprefix("SHOT-").rsplit("-", 1)[0]
                source_ids = [str(layer["asset_id"]) for layer in rig.get("layers", [])] + [str(cue["audio"]["asset_id"]), str(cue["audio"]["mix_asset_id"]), str(cue["subtitle_asset_id"]), background_asset_id, scene_id]
                asset = repository.register_asset(f"AST-VIDEO-JHY-FINAL-{shot_id.replace('-', '')}-{stamp.replace('-', '')}", "video", final, metadata={"title": f"最终镜头预览 · {shot_id}", "provider": "local_timeline_final", "rig_id": rig_id, "audio_asset_id": cue["audio"]["asset_id"], "subtitle_asset_id": cue["subtitle_asset_id"]}, source_entity_ids=source_ids)
                return self._json({"status": "created", "provider": "local_timeline_final", "shot_id": shot_id, "rig_id": rig_id, "output": _relative(project, final), "media_url": f"/media/{project.name}/{_relative(project, final)}", "subtitle": cue["subtitle_asset_id"], "audio": cue["audio"]["mix_asset_id"], "video_asset": asset}, HTTPStatus.CREATED)
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError, NovelAnimeRepositoryError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/final-shot-review", route)
        if match:
            try:
                project = _safe_project(match.group(1)); payload = self._read_json(); review = _final_shot_review(project)
                checks = payload.get("checks")
                if not isinstance(checks, dict) or any(checks.get(key) not in {"PENDING", "PASS", "CHANGES_REQUESTED"} for key in ("sound", "subtitles", "mouth")):
                    raise ValueError("checks must contain sound, subtitles and mouth with valid statuses")
                status = str(payload.get("status") or "PENDING")
                if status not in {"PENDING", "APPROVED", "CHANGES_REQUESTED"}:
                    raise ValueError("invalid review status")
                if status == "APPROVED" and any(checks[key] != "PASS" for key in ("sound", "subtitles", "mouth")):
                    raise ValueError("all three checks must be PASS before approval")
                review.update({"checks": checks, "status": status, "reviewer": str(payload.get("reviewer") or ""), "note": str(payload.get("note") or ""), "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                (project / "dynamic").mkdir(parents=True, exist_ok=True); (project / "dynamic" / "final-shot-review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                return self._json(review)
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/storyboard-final-batch-preview", route)
        if match:
            try:
                project = _safe_project(match.group(1)); review = _final_shot_review(project)
                if review.get("status") != "APPROVED":
                    return self._json({"status": "blocked", "reason": "final shot review must be APPROVED before batch rendering", "review": review}, HTTPStatus.CONFLICT)
                timeline = json.loads((project / "dynamic" / "mouth-cues.json").read_text(encoding="utf-8")).get("timeline", [])
                character_id = str(review.get("character_id") or "CHR-JHY-BAIHUA")
                eligible = sorted({str(item.get("shot_id")) for item in timeline if item.get("audio", {}).get("mix_asset_id") and item.get("speaker_character_id") == character_id})
                missing = sorted({str(item.get("speaker_character_id")) for item in timeline if item.get("audio", {}).get("mix_asset_id") and item.get("speaker_character_id") != character_id})
                result = render_final_shot_batch(project, eligible, str(review.get("rig_id") or "RIG-CHR-JHY-BAIHUA-FRONT-V1"))
                return self._json({**result, "shot_count": len(eligible), "shot_ids": eligible, "blocked_character_ids": missing, "provider": "local_timeline_final", "rig_id": review.get("rig_id"), "human_review": review})
            except (ValueError, OSError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/episode-masters/review", route)
        if match:
            try:
                project = _safe_project(match.group(1))
                result = _update_episode_master_review(project, self._read_json())
                return self._json(result)
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/backups", route)
        if match:
            try:
                project = _safe_project(match.group(1)); payload = self._read_json(); label = str(payload.get("label") or "").strip()
                if not label:
                    raise ValueError("backup label is required")
                result = NovelAnimeRepository(project).create_snapshot(label)
                self._json({"status": "created", **result}, HTTPStatus.CREATED)
            except (ValueError, NovelAnimeRepositoryError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
            return
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/qc/(annotations|issues)", route)
        if match:
            try:
                project = _safe_project(match.group(1))
                payload = self._read_json()
                if match.group(2) == "annotations":
                    report = add_annotation(project, str(payload.get("target_id") or ""), str(payload.get("note") or ""), str(payload.get("author") or ""), payload.get("finding_id"))
                else:
                    refs = payload.get("target_refs")
                    if not isinstance(refs, list) or any(not isinstance(item, str) for item in refs):
                        raise ValueError("target_refs must be a string list")
                    report = add_issue(project, str(payload.get("title") or ""), refs, payload.get("finding_id"))
                self._json(report, HTTPStatus.CREATED)
            except (ValueError, NovelQCError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
            return
        match = re.fullmatch(r"/api/novel-anime/projects/([^/]+)/qc/issues/([A-Z0-9-]+)", route)
        if match:
            try:
                project = _safe_project(match.group(1)); payload = self._read_json()
                rerender = payload.get("rerender_job_ids")
                if rerender is not None and (not isinstance(rerender, list) or any(not isinstance(item, str) for item in rerender)):
                    raise ValueError("rerender_job_ids must be a string list")
                report = update_issue(project, match.group(2), str(payload.get("status") or ""), note=payload.get("note"), rerender_job_ids=rerender)
                self._json(report, HTTPStatus.OK)
            except (ValueError, NovelQCError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
            return
        if route != "/api/generate":
            return self._error(HTTPStatus.NOT_FOUND, "route not found")
        try:
            payload = self._read_json()
            response = self._generate(payload)
            self._json(response, HTTPStatus.CREATED)
        except VideoGenerationError as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))
        except Exception as error:  # keep server alive after provider failures
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"generation failed: {error}")

    def _projects(self) -> list[dict[str, object]]:
        projects = []
        if not PROJECTS_ROOT.is_dir():
            return projects
        for project in sorted(PROJECTS_ROOT.iterdir()):
            if project.is_dir() and not project.name.startswith("."):
                media = _media_files(project)
                projects.append({"id": project.name, "name": project.name, "media_count": len(media)})
        return projects

    def _generate(self, payload: dict[str, object]) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        project_id = str(payload.get("project_id") or "")
        provider_id = str(payload.get("provider") or "local_ken_burns")
        image_path = str(payload.get("image_path") or "")
        if provider_id not in PROVIDER_TYPES:
            raise ValueError("unsupported provider")
        if provider_id != "local_ken_burns" and payload.get("confirm_billable") is not True:
            raise ValueError("remote generation requires confirm_billable=true")
        project = _safe_project(project_id)
        image = _safe_project_file(project_id, image_path)
        if image.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError("image_path must point to an image")
        output_dir = project / "generated"
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output = output_dir / f"{stamp}-{provider_id}.mp4"
        request = VideoGenerationRequest(
            image_paths=normalize_image_paths((image,)),
            output_path=output,
            shot_duration_seconds=float(payload.get("shot_duration") or 4),
            width=int(payload.get("width") or 1080),
            height=int(payload.get("height") or 1920),
            prompt_text=str(payload.get("prompt") or ""),
            model=str(payload.get("model") or ("sora-2" if provider_id == "openai_sora" else "gen4.5")),
        )
        provider_kwargs = {}
        if provider_id in KEY_ENV and RUNTIME_KEYS.get(provider_id):
            provider_kwargs["api_key"] = RUNTIME_KEYS[provider_id]
        result = PROVIDER_TYPES[provider_id](**provider_kwargs).generate(request)
        return {"provider": result.provider, "task_id": result.task_id, "duration_seconds": result.duration_seconds, "output_path": _relative(project, result.output_path), "media_url": f"/media/{project.name}/{_relative(project, result.output_path)}"}

    def _save_key(self) -> None:
        payload = self._read_json()
        provider_id = str(payload.get("provider") or "")
        key = str(payload.get("key") or "").strip()
        if provider_id not in KEY_ENV:
            raise ValueError("only remote providers accept a key")
        if key and (len(key) < 8 or len(key) > 512):
            raise ValueError("key length must be between 8 and 512 characters")
        if key:
            RUNTIME_KEYS[provider_id] = key
        else:
            RUNTIME_KEYS.pop(provider_id, None)
        self._json({"provider": provider_id, "configured": bool(key or os.environ.get(KEY_ENV[provider_id])), "source": "session" if key else ("environment" if os.environ.get(KEY_ENV[provider_id]) else "none")})

    def _save_integration(self) -> None:
        payload = self._read_json()
        integration_id = str(payload.get("integration") or "")
        base_url = str(payload.get("base_url") or "").strip()
        if integration_id == "comfyui":
            if not base_url:
                RUNTIME_INTEGRATIONS.pop("comfyui", None)
                return self._json(_comfyui_image_status())
            provider = ComfyUIImageProvider(base_url, config_path=COMFYUI_IMAGE_PROVIDER_CONFIG_PATH, timeout_seconds=0.8)
            RUNTIME_INTEGRATIONS["comfyui"] = {"base_url": provider.base_url}
            return self._json(_comfyui_image_status())
        if integration_id != "arcreel":
            raise ValueError("unsupported integration")
        api_key = str(payload.get("api_key") or "").strip()
        if not base_url:
            RUNTIME_INTEGRATIONS.pop("arcreel", None)
            return self._json(_integration_status()[0])
        client = ArcReelWorkspace(base_url, api_key=api_key or None, timeout_seconds=0.8)
        existing = RUNTIME_INTEGRATIONS.get("arcreel", {})
        RUNTIME_INTEGRATIONS["arcreel"] = {"base_url": client.base_url}
        if api_key:
            RUNTIME_INTEGRATIONS["arcreel"]["api_key"] = api_key
        elif existing.get("api_key"):
            RUNTIME_INTEGRATIONS["arcreel"]["api_key"] = existing["api_key"]
        self._json(_integration_status()[0])

    def _generate_local_storyboard(self, payload: dict[str, object]) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        project_id = str(payload.get("project_id") or "")
        project = _safe_project(project_id)
        output = project / "generated" / f"web-local-storyboard-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 100000:05d}.mp4"
        result = run_local_storyboard(project, output)
        relative = _relative(project, Path(result["output"]))
        return {**result, "output": relative, "media_url": f"/media/{project.name}/{relative}"}

    def _read_json(self, *, max_bytes: int = 64 * 1024) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("invalid content length") from error
        if length <= 0 or length > max_bytes:
            raise ValueError(f"request body must be between 1 byte and {max_bytes} bytes")
        parsed = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("request body must be an object")
        return parsed

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            return self._error(HTTPStatus.NOT_FOUND, "file not found")
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), VideoCreatorHandler)
    print(f"VideoCreator web console: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
