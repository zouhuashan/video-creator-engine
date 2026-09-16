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
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
PROJECTS_ROOT = ROOT / "projects"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.video_generation import (  # noqa: E402
    LocalKenBurnsVideo,
    OpenAISoraVideo,
    RunwayImageToVideo,
    VideoGenerationError,
    VideoGenerationRequest,
    WanImageToVideo,
    normalize_image_paths,
)
from scripts.local_storyboard_pipeline import LocalStoryboardError, run_local_storyboard  # noqa: E402
from scripts.novel_anime_project import MANIFEST_NAME as NOVEL_ANIME_MANIFEST, NovelAnimeProjectError, load_project as load_novel_anime_project  # noqa: E402
from scripts.novel_anime_repository import NovelAnimeRepository, NovelAnimeRepositoryError, repository_stats  # noqa: E402
from scripts.novel_anime_runtime import NovelAnimeRuntime, NovelAnimeRuntimeError, runtime_stats  # noqa: E402
from scripts.novel_source_catalog import CATALOG_RELATIVE_PATH, NovelSourceCatalogError, load_catalog  # noqa: E402
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


PROVIDER_TYPES = {
    "local_ken_burns": LocalKenBurnsVideo,
    "openai_sora": OpenAISoraVideo,
    "runway": RunwayImageToVideo,
    "wan": WanImageToVideo,
}
KEY_ENV = {
    "openai_sora": "OPENAI_API_KEY",
    "runway": "RUNWAY_API_KEY",
    "wan": "FAL_KEY",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}
# Keys entered in the console live only for this server process.  They are
# intentionally never written to disk, returned by the API, or put in logs.
RUNTIME_KEYS: dict[str, str] = {}


def _safe_project(project_id: str) -> Path:
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
    if not episode_root.is_dir():
        return episodes
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
            "media_url": f"/media/{project.name}/{relative}",
        })
    return episodes


def _novel_anime_projects(projects_root: Path = PROJECTS_ROOT) -> list[dict[str, object]]:
    projects = []
    if not projects_root.is_dir():
        return projects
    for manifest in sorted(projects_root.glob(f"*/{NOVEL_ANIME_MANIFEST}")):
        try:
            project = load_novel_anime_project(manifest)
        except NovelAnimeProjectError:
            continue
        projects.append({
            "directory_id": manifest.parent.name,
            "project_id": project["project_id"],
            "title": project["title"],
            "status": project["status"],
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
        })
    return projects


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


def _provider_status() -> list[dict[str, object]]:
    status = [{"id": "local_ken_burns", "label": "本地动态分镜", "remote": False, "configured": True}]
    for provider_id, label in (("openai_sora", "OpenAI Sora"), ("runway", "Runway"), ("wan", "Wan 2.1")):
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
            return self._json({"status": "ok", "providers": _provider_status()})
        if parsed.path == "/api/projects":
            return self._json({"projects": self._projects()})
        if parsed.path == "/api/novel-anime/projects":
            return self._json({"projects": _novel_anime_projects()})
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
        if route == "/api/settings/keys":
            try:
                return self._save_key()
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
        if route == "/api/storyboard/local":
            try:
                payload = self._read_json()
                response = self._generate_local_storyboard(payload)
                self._json(response, HTTPStatus.CREATED)
            except (LocalStoryboardError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
            except Exception as error:
                return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"storyboard failed: {error}")
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

    def _generate_local_storyboard(self, payload: dict[str, object]) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        project_id = str(payload.get("project_id") or "")
        project = _safe_project(project_id)
        output = project / "generated" / f"web-local-storyboard-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 100000:05d}.mp4"
        result = run_local_storyboard(project, output)
        relative = _relative(project, Path(result["output"]))
        return {**result, "output": relative, "media_url": f"/media/{project.name}/{relative}"}

    def _read_json(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("invalid content length") from error
        if length <= 0 or length > 64 * 1024:
            raise ValueError("request body must be between 1 byte and 64 KB")
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
    parser.add_argument("--port", type=int, default=8765)
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
