#!/usr/bin/env python3
"""Build local animatic plans that join shots, temporary audio, subtitles, and previews."""
from __future__ import annotations
import argparse, json, os, sys, tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp
from scripts.novel_episode_script import load_script_package
from scripts.novel_storyboard import load_storyboard
SCHEMA_PATH = ROOT / "schemas" / "novel-animatic.schema.json"
OUTPUT = Path("animatic/animatic-plan.json")
class NovelAnimaticError(ValueError): pass
def _review(): return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}
def build_animatic(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); scripts = load_script_package(project_dir); storyboard = load_storyboard(project_dir); now = utc_timestamp(); shot_map = {shot["shot_id"]: shot for shot in storyboard["frames"]}; episodes = []
    for episode in project["episodes"]:
        shot_ids = [shot["shot_id"] for scene in storyboard["frames"] for shot in [scene] if False]
        script = next((item for item in scripts["episode_scripts"] if item["episode_id"] == episode["id"]), None)
        if script:
            scene_ids = {scene["id"] for scene in script["scenes"]}; shot_ids = [shot_id for shot_id, frame in shot_map.items() if any(shot_id.startswith(f"SHOT-{scene_id}-") for scene_id in scene_ids)]
        episodes.append({"episode_id": episode["id"], "shot_ids": shot_ids, "temporary_audio": {"status": "PLANNED", "path": None, "duration_seconds": 0}, "subtitle_track": {"status": "PLANNED", "path": None, "cue_count": 0}, "output_path": None, "status": "DRAFT", "human_review": _review()})
    return validate_animatic(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "storyboard_revision": storyboard["revision"], "script_revision": scripts["revision"], "revision": 1, "created_at": now, "updated_at": now, "episodes": episodes})
def _schema(payload):
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors: raise NovelAnimaticError(f"animatic schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")
def validate_animatic(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelAnimaticError("animatic must be an object")
    package = deepcopy(payload); _schema(package); project = load_project(Path(project_dir) / MANIFEST_NAME); scripts = load_script_package(project_dir); storyboard = load_storyboard(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]: raise NovelAnimaticError("animatic does not match project")
    if package["storyboard_revision"] != storyboard["revision"] or package["script_revision"] != scripts["revision"]: raise NovelAnimaticError("animatic upstream revisions are stale")
    episode_ids = {episode["id"] for episode in project["episodes"]}
    if {item["episode_id"] for item in package["episodes"]} != episode_ids: raise NovelAnimaticError("animatic must cover every project episode")
    shot_ids = {frame["shot_id"] for frame in storyboard["frames"]}
    for episode in package["episodes"]:
        if set(episode["shot_ids"]) - shot_ids: raise NovelAnimaticError(f"{episode['episode_id']} references unknown shot")
        if episode["status"] == "READY" and (not episode["shot_ids"] or episode["temporary_audio"]["status"] != "READY" or episode["subtitle_track"]["status"] != "READY" or not episode["output_path"] or episode["human_review"]["status"] != "APPROVED"): raise NovelAnimaticError(f"READY {episode['episode_id']} is incomplete")
    return package
def write_animatic(project_dir: Path, package: dict[str, Any], overwrite=False) -> Path:
    project_dir = Path(project_dir).resolve(); package = validate_animatic(project_dir, package); path = project_dir / OUTPUT
    if path.exists() and not overwrite: raise NovelAnimaticError(f"refusing to overwrite animatic: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".animatic.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream: json.dump(package, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return path
def load_animatic(project_dir: Path) -> dict[str, Any]:
    try: payload = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e: raise NovelAnimaticError(f"cannot read animatic: {e}") from e
    return validate_animatic(project_dir, payload)
def summary(project_dir: Path) -> dict[str, Any] | None:
    try: package = load_animatic(project_dir)
    except (NovelAnimaticError, ValueError): return None
    return {"revision": package["revision"], "episode_count": len(package["episodes"]), "ready_episode_count": sum(1 for item in package["episodes"] if item["status"] == "READY"), "shot_count": sum(len(item["shot_ids"]) for item in package["episodes"]), "audio_ready_count": sum(1 for item in package["episodes"] if item["temporary_audio"]["status"] == "READY"), "subtitle_ready_count": sum(1 for item in package["episodes"] if item["subtitle_track"]["status"] == "READY")}
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try: result = {"output": write_animatic(args.project_dir, build_animatic(args.project_dir)).relative_to(args.project_dir.resolve()).as_posix()} if args.command == "create" else summary(args.project_dir)
    except (NovelAnimaticError, OSError, ValueError) as error: print(f"novel_animatic: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
