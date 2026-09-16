#!/usr/bin/env python3
"""Assemble episode timelines and support shot-level lossless rerender plans."""
from __future__ import annotations
import argparse, json, os, sys, tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp
from scripts.novel_audio_assets import load_audio_assets
from scripts.novel_audio_mix import load_audio_mix
from scripts.novel_dynamic_shots import load_dynamic_shots
from scripts.novel_voice_profiles import load_voice_profiles
SCHEMA_PATH = ROOT / "schemas" / "novel-edit-timelines.schema.json"
OUTPUT = Path("edit/edit-timelines.json")
class NovelEditTimelineError(ValueError): pass
def _review(): return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}
def build_edit_timelines(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); dynamic = load_dynamic_shots(project_dir); audio = load_audio_mix(project_dir); now = utc_timestamp(); episodes = [{"episode_id": item["episode_id"], "clips": [], "dialogue_line_ids": list(item["dialogue_line_ids"]), "cue_ids": list(item["cue_ids"]), "subtitle_status": "PLANNED", "audio_buses": [], "output_path": None, "status": "DRAFT", "human_review": _review()} for item in audio["episodes"]]
    return validate_edit_timelines(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "dynamic_revision": dynamic["revision"], "audio_mix_revision": audio["revision"], "revision": 1, "created_at": now, "updated_at": now, "episodes": episodes, "rerender_jobs": []})
def _schema(payload):
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors: raise NovelEditTimelineError(f"edit timeline schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")
def validate_edit_timelines(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelEditTimelineError("edit timelines must be an object")
    package = deepcopy(payload); _schema(package); project = load_project(Path(project_dir) / MANIFEST_NAME); dynamic = load_dynamic_shots(project_dir); audio = load_audio_mix(project_dir); voices = load_voice_profiles(project_dir); audio_assets = load_audio_assets(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]: raise NovelEditTimelineError("edit timelines do not match project")
    if (package["dynamic_revision"], package["audio_mix_revision"]) != (dynamic["revision"], audio["revision"]): raise NovelEditTimelineError("edit timelines upstream revisions are stale")
    episode_ids = {item["episode_id"] for item in audio["episodes"]}; shot_ids = {item["shot_id"] for item in dynamic["shot_routes"]}; line_ids = {item["unit_id"] for item in voices["line_assignments"]}; cue_ids = {item["id"] for item in audio_assets["cues"]}
    if {item["episode_id"] for item in package["episodes"]} != episode_ids: raise NovelEditTimelineError("edit timelines must cover every episode")
    for episode in package["episodes"]:
        previous = 0.0; local_shots = set()
        for clip in episode["clips"]:
            if clip["shot_id"] not in shot_ids: raise NovelEditTimelineError(f"clip {clip['id']} references unknown shot")
            if clip["shot_id"] in local_shots or clip["start_seconds"] < previous or clip["end_seconds"] <= clip["start_seconds"]: raise NovelEditTimelineError(f"clip order or timing is invalid for {episode['episode_id']}")
            local_shots.add(clip["shot_id"]); previous = clip["end_seconds"]
        if set(episode["dialogue_line_ids"]) - line_ids or set(episode["cue_ids"]) - cue_ids: raise NovelEditTimelineError(f"{episode['episode_id']} references unknown audio input")
        if episode["status"] == "READY" and (not episode["clips"] or episode["subtitle_status"] != "READY" or not episode["output_path"] or episode["human_review"]["status"] != "APPROVED"): raise NovelEditTimelineError(f"READY {episode['episode_id']} is incomplete")
    for job in package["rerender_jobs"]:
        if job["episode_id"] not in episode_ids or set(job["shot_ids"]) - shot_ids: raise NovelEditTimelineError(f"rerender job {job['id']} has invalid references")
        if job["input_revision"] != package["revision"]: raise NovelEditTimelineError(f"rerender job {job['id']} input revision is stale")
    return package
def write_edit_timelines(project_dir: Path, package: dict[str, Any], overwrite=False) -> Path:
    project_dir = Path(project_dir).resolve(); package = validate_edit_timelines(project_dir, package); path = project_dir / OUTPUT
    if path.exists() and not overwrite: raise NovelEditTimelineError(f"refusing to overwrite edit timelines: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".edit-timelines.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream: json.dump(package, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return path
def load_edit_timelines(project_dir: Path) -> dict[str, Any]:
    try: payload = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e: raise NovelEditTimelineError(f"cannot read edit timelines: {e}") from e
    return validate_edit_timelines(project_dir, payload)
def summary(project_dir: Path) -> dict[str, Any] | None:
    try: package = load_edit_timelines(project_dir)
    except (NovelEditTimelineError, ValueError): return None
    return {"revision": package["revision"], "episode_count": len(package["episodes"]), "ready_episode_count": sum(1 for item in package["episodes"] if item["status"] == "READY"), "clip_count": sum(len(item["clips"]) for item in package["episodes"]), "rerender_job_count": len(package["rerender_jobs"])}
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try: result = {"output": write_edit_timelines(args.project_dir, build_edit_timelines(args.project_dir)).relative_to(args.project_dir.resolve()).as_posix()} if args.command == "create" else summary(args.project_dir)
    except (NovelEditTimelineError, OSError, ValueError) as error: print(f"novel_edit_timelines: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
