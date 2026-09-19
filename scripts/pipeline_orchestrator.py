#!/usr/bin/env python3
"""Software-first pipeline orchestrator for VideoCreator Engine.

The orchestrator is provider-neutral. It plans and persists one project-level
run manifest, builds prompts from locked character/shot data, and keeps final
publication behind a human review gate.

P30-01 is a dry-run capable skeleton: it never triggers billable remote media
generation by itself.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
PIPELINE_CONFIG = ROOT / "config" / "pipeline-orchestrator.json"

from support.providers.image_provider_router import ImageProviderRouter
from support.providers.openai_image_provider import keyframe_prompt
from support.providers.video_provider_router import VideoProviderRouter

STAGE_ORDER = (
    "story",
    "character",
    "shot",
    "scene_control",
    "prompt",
    "image",
    "video",
    "tts",
    "subtitles",
    "assembly",
    "qc",
    "review",
)


class PipelineError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PipelineError(f"invalid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise PipelineError(f"JSON root must be an object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _relative(project: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(project.resolve()))
    except ValueError:
        return str(path)


def _config() -> dict[str, Any]:
    return _load_json(PIPELINE_CONFIG)


def _project_path(project_id: str, projects_root: Path = PROJECTS_ROOT) -> Path:
    project_id = str(project_id or "").strip()
    if not project_id or "/" in project_id or "\\" in project_id or project_id in {".", ".."}:
        raise PipelineError("invalid project id")
    project = (projects_root / project_id).resolve()
    root = projects_root.resolve()
    if root not in project.parents:
        raise PipelineError("project path escapes projects root")
    if not project.is_dir():
        raise PipelineError(f"project not found: {project_id}")
    return project


def _latest_approved_image(project: Path, artifact_type: str) -> dict[str, Any] | None:
    root = project / "lookdev" / "image-studio"
    if not root.is_dir():
        return None
    candidates: list[tuple[float, dict[str, Any], Path]] = []
    for meta_path in root.rglob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(meta, dict):
            continue
        if meta.get("artifact_type") != artifact_type or meta.get("review_status") != "APPROVED":
            continue
        output = str(meta.get("output") or "")
        output_path = project / output
        if output and output_path.is_file():
            candidates.append((meta_path.stat().st_mtime, meta, meta_path))
    if not candidates:
        return None
    _, meta, meta_path = max(candidates, key=lambda item: item[0])
    return {**meta, "metadata": _relative(project, meta_path)}


def _first_existing(project: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        matches = sorted(project.glob(pattern))
        if matches:
            return matches[-1]
    return None


def _stage(
    stage_id: str,
    status: str,
    detail: str,
    *,
    owner: str = "software",
    human_action: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": stage_id,
        "status": status,
        "detail": detail,
        "owner": owner,
        "human_action": human_action,
        **extra,
    }


def _scene_control_payload(character: dict[str, Any], shot: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "role": "AUXILIARY_3D_CONTROL",
        "character_id": character.get("character_id"),
        "shot_id": shot.get("shot_id"),
        "camera": shot.get("camera", {}),
        "action": shot.get("action", ""),
        "environment": shot.get("environment", ""),
        "lighting": shot.get("lighting", ""),
        "outputs": ["blocking", "pose", "depth", "normal", "mask", "composition"],
        "final_visual_allowed": False,
    }


def _auto_qc(video_path: Path | None) -> dict[str, Any]:
    if video_path is None or not video_path.is_file():
        return {"status": "PENDING", "checks": {"media_exists": False}, "auto_retry": False}
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {
            "status": "PENDING",
            "checks": {"media_exists": True, "ffprobe_available": False},
            "auto_retry": False,
        }
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height",
        "-of",
        "json",
        str(video_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return {
            "status": "FAIL",
            "checks": {"media_exists": True, "ffprobe": False},
            "auto_retry": True,
            "error": (completed.stderr or "ffprobe failed")[-1200:],
        }
    try:
        probe = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"status": "FAIL", "checks": {"ffprobe_json": False}, "auto_retry": True}
    streams = probe.get("streams") or []
    has_video = any(item.get("codec_type") == "video" for item in streams if isinstance(item, dict))
    has_audio = any(item.get("codec_type") == "audio" for item in streams if isinstance(item, dict))
    duration = float((probe.get("format") or {}).get("duration") or 0.0)

    anomaly = {
        "scanner_available": False,
        "black_frame_detected": False,
        "freeze_detected": False,
    }
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and has_video:
        scan = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "info",
                "-i",
                str(video_path),
                "-vf",
                "blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-50dB:d=2",
                "-an",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        scan_log = scan.stderr or ""
        if scan.returncode == 0:
            anomaly["scanner_available"] = True
            anomaly["black_frame_detected"] = "black_start:" in scan_log
            anomaly["freeze_detected"] = "freeze_start:" in scan_log
        else:
            anomaly["scanner_error"] = scan_log[-800:] or "ffmpeg anomaly scan failed"

    anomaly_failed = bool(anomaly["black_frame_detected"] or anomaly["freeze_detected"])
    status = "PASS" if has_video and duration > 0 and not anomaly_failed else "FAIL"
    return {
        "status": status,
        "checks": {
            "media_exists": True,
            "ffprobe": True,
            "video_stream": has_video,
            "audio_stream": has_audio,
            "duration_positive": duration > 0,
            "anomaly_scan": anomaly,
        },
        "duration_seconds": round(duration, 3),
        "auto_retry": status == "FAIL",
    }


def pipeline_status(project_id: str, projects_root: Path = PROJECTS_ROOT) -> dict[str, Any]:
    project = _project_path(project_id, projects_root)
    run_path = project / "pipeline" / "run.json"
    if not run_path.is_file():
        return {
            "project_id": project.name,
            "status": "NOT_STARTED",
            "execution_mode": None,
            "stages": [],
            "progress": 0,
            "review": {"required": True, "status": "PENDING", "ready": False},
            "preview": "",
            "next": "RUN_PIPELINE",
        }
    payload = _load_json(run_path)
    payload["run_manifest"] = _relative(project, run_path)
    return payload


def run_pipeline(
    project_id: str,
    *,
    dry_run: bool = True,
    projects_root: Path = PROJECTS_ROOT,
) -> dict[str, Any]:
    project = _project_path(project_id, projects_root)
    cfg = _config()
    character_path = ROOT / str(cfg["character_config"])
    shot_path = ROOT / str(cfg["shot_config"])
    character = _load_json(character_path)
    shot = _load_json(shot_path)

    pipeline_root = project / "pipeline"
    prompt_dir = pipeline_root / "prompts"
    control_dir = pipeline_root / "scene-control"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    stages: list[dict[str, Any]] = []

    manifest = project / "novel-anime-project.json"
    story_source = manifest if manifest.is_file() else _first_existing(
        project, ("**/story-bible*.json", "**/script*.json", "**/storyboard*.json")
    )
    if story_source:
        stages.append(_stage("story", "PASS", "story/project source resolved", source=_relative(project, story_source)))
    else:
        stages.append(_stage("story", "BLOCKED", "no project story source found"))

    approved_character = _latest_approved_image(project, "character_bible")
    if approved_character:
        stages.append(_stage("character", "PASS", "approved character bible resolved", asset=approved_character.get("output")))
    else:
        stages.append(_stage(
            "character",
            "WAITING_REVIEW",
            "character lock exists but no approved Image Studio character bible",
            config=str(cfg["character_config"]),
        ))

    stages.append(_stage("shot", "PASS", "shot contract resolved", config=str(cfg["shot_config"])))

    control = _scene_control_payload(character, shot)
    control_path = control_dir / f"{shot.get('shot_id', 'shot')}.json"
    _write_json(control_path, control)
    stages.append(_stage(
        "scene_control",
        "PASS",
        "Blender auxiliary scene-control contract prepared",
        role="AUXILIARY_3D_CONTROL",
        final_visual_allowed=False,
        artifact=_relative(project, control_path),
    ))

    prompt = keyframe_prompt(character, shot)
    prompt_path = prompt_dir / f"{shot.get('shot_id', 'shot')}.txt"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    stages.append(_stage(
        "prompt",
        "PASS",
        "prompt built automatically from Character Bible + Shot",
        artifact=_relative(project, prompt_path),
    ))

    image_router = ImageProviderRouter()
    image_route = image_router.describe()
    approved_keyframe = _latest_approved_image(project, "keyframe")
    if approved_keyframe:
        stages.append(_stage("image", "PASS", "approved keyframe resolved", asset=approved_keyframe.get("output"), route=image_route))
    else:
        stages.append(_stage(
            "image",
            "PLANNED" if dry_run else "BLOCKED",
            "keyframe will be generated by ImageProvider Router",
            route=image_route,
        ))

    video_router = VideoProviderRouter()
    video_route = video_router.route(
        "image_to_video",
        preferred_provider=str(cfg.get("default_video_provider") or "LOCAL_KEN_BURNS"),
    )
    existing_video = _first_existing(project, ("final.mp4", "generated/*.mp4", "renders/**/*.mp4"))
    if existing_video:
        stages.append(_stage("video", "PASS", "existing project video resolved", asset=_relative(project, existing_video), route=video_route))
    else:
        stages.append(_stage("video", "PLANNED", "VideoProvider route resolved", route=video_route))

    voice = _first_existing(project, ("voice/*.wav", "audio/**/*.wav", "audio/**/*.mp3"))
    stages.append(_stage(
        "tts",
        "PASS" if voice else "PLANNED",
        "TTS/audio asset resolved" if voice else "TTS Provider will synthesize script lines",
        asset=_relative(project, voice),
    ))

    subtitles = _first_existing(project, ("*.srt", "*.ass", "subtitles/**/*.srt", "subtitles/**/*.ass"))
    stages.append(_stage(
        "subtitles",
        "PASS" if subtitles else "PLANNED",
        "subtitle asset resolved" if subtitles else "subtitles will be built from script/TTS timing; Whisper round-trip is disabled",
        asset=_relative(project, subtitles),
        subtitle_source="SCRIPT_TTS_TIMING",
        asr_round_trip=False,
    ))

    final_video = project / "final.mp4"
    if final_video.is_file():
        stages.append(_stage("assembly", "PASS", "FFmpeg final output exists", asset="final.mp4"))
        qc = _auto_qc(final_video)
    else:
        stages.append(_stage("assembly", "PLANNED", "FFmpeg finalizer will assemble video/audio/subtitles"))
        qc = _auto_qc(existing_video)
    stages.append(_stage("qc", qc["status"], "automatic media QC", report=qc, auto_retry=bool(qc.get("auto_retry"))))

    review_ready = final_video.is_file() and qc.get("status") == "PASS"
    review_path = pipeline_root / "review.json"
    review = _load_json(review_path) if review_path.is_file() else {"required": True, "status": "PENDING"}
    if not review_ready:
        review["status"] = "PENDING"
    stages.append(_stage(
        "review",
        "READY" if review_ready else "BLOCKED",
        "human final review required before publication" if review_ready else "final review waits for assembled media and PASS QC",
        owner="human",
        human_action=True,
        human_required=True,
        review_status=review.get("status", "PENDING"),
    ))

    pass_like = {"PASS", "READY", "PLANNED"}
    completed = sum(1 for item in stages if item["status"] in pass_like)
    hard_blocked = any(item["status"] == "BLOCKED" and item["id"] not in {"review"} for item in stages)
    status = "DRY_RUN_PASS" if dry_run and not hard_blocked else ("READY_FOR_REVIEW" if review_ready else "IN_PROGRESS")
    result = {
        "schema_version": 1,
        "project_id": project.name,
        "status": status,
        "execution_mode": "DRY_RUN" if dry_run else "EXECUTE",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stage_order": list(STAGE_ORDER),
        "stages": stages,
        "progress": round(completed / len(stages) * 100),
        "routing": {
            "image": image_route,
            "video": video_route,
            "blender_role": "AUXILIARY_3D_CONTROL",
        },
        "automation_policy": {
            **dict(cfg.get("execution_policy") or {}),
            "software_owned_stages": [item["id"] for item in stages if item.get("owner") == "software"],
            "human_owned_stages": [item["id"] for item in stages if item.get("owner") == "human"],
        },
        "review": {
            "required": True,
            "status": review.get("status", "PENDING"),
            "ready": review_ready,
        },
        "preview": _relative(project, final_video if final_video.is_file() else existing_video),
        "next": "HUMAN_REVIEW" if review_ready else "RESOLVE_PENDING_STAGES",
    }
    run_path = pipeline_root / "run.json"
    _write_json(run_path, result)
    result["run_manifest"] = _relative(project, run_path)
    return result


def update_pipeline_review(
    project_id: str,
    status: str,
    *,
    note: str = "",
    reviewer: str = "human-web",
    projects_root: Path = PROJECTS_ROOT,
) -> dict[str, Any]:
    project = _project_path(project_id, projects_root)
    run = pipeline_status(project_id, projects_root)
    status = str(status or "").strip().upper()
    if status not in {"APPROVED", "CHANGES_REQUESTED", "PENDING"}:
        raise PipelineError("review status must be APPROVED, CHANGES_REQUESTED or PENDING")
    if status == "APPROVED" and not bool((run.get("review") or {}).get("ready")):
        raise PipelineError("pipeline is not ready for final approval")
    payload = {
        "required": True,
        "status": status,
        "reviewer": reviewer,
        "note": str(note or "").strip(),
        "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_json(project / "pipeline" / "review.json", payload)
    run["review"] = {**payload, "ready": bool((run.get("review") or {}).get("ready"))}
    for stage in run.get("stages", []):
        if stage.get("id") == "review":
            stage["review_status"] = status
    _write_json(project / "pipeline" / "run.json", {k: v for k, v in run.items() if k != "run_manifest"})
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_id")
    parser.add_argument("--execute", action="store_true", help="reserve execute mode; P30-01 remains provider-gated")
    args = parser.parse_args()
    try:
        result = run_pipeline(args.project_id, dry_run=not args.execute)
    except PipelineError as error:
        print(f"FAIL {error}")
        print("NEXT fix project/config prerequisites")
        return 1
    print(f"PASS pipeline={result['status']} progress={result['progress']}%")
    print(f"RESULT {result['run_manifest']}")
    print(f"NEXT {result['next']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
