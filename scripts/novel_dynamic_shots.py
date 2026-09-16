#!/usr/bin/env python3
"""Route dynamic shots, queue billable work safely, and track shot review."""
from __future__ import annotations
import argparse, json, os, sys, tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp
from scripts.novel_animatic import load_animatic
from scripts.novel_storyboard import load_storyboard
SCHEMA_PATH = ROOT / "schemas" / "novel-dynamic-shots.schema.json"
OUTPUT = Path("dynamic/dynamic-shots.json")
class NovelDynamicShotError(ValueError): pass
def build_dynamic_shots(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); storyboard = load_storyboard(project_dir); animatic = load_animatic(project_dir); now = utc_timestamp(); shots = [frame["shot_id"] for frame in storyboard["frames"]]
    routes = [{"shot_id": shot, "mode": "LOCAL_KEN_BURNS", "provider": "local_ken_burns", "input_reference_ids": [], "fallback_mode": "MANUAL_IMPORT", "prompt": "", "status": "DRAFT"} for shot in shots]
    reviews = [{"shot_id": shot, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": "", "identity_pass": False, "motion_pass": False} for shot in shots]
    return validate_dynamic_shots(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "storyboard_revision": storyboard["revision"], "animatic_revision": animatic["revision"], "revision": 1, "created_at": now, "updated_at": now, "shot_routes": routes, "jobs": [], "budget": {"currency": "USD", "limit": 0, "reserved": 0, "spent": 0}, "reviews": reviews})
def _schema(payload):
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors: raise NovelDynamicShotError(f"dynamic shot schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")
def validate_dynamic_shots(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelDynamicShotError("dynamic shots must be an object")
    package = deepcopy(payload); _schema(package); project = load_project(Path(project_dir) / MANIFEST_NAME); storyboard = load_storyboard(project_dir); animatic = load_animatic(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]: raise NovelDynamicShotError("dynamic shots do not match project")
    if (package["storyboard_revision"], package["animatic_revision"]) != (storyboard["revision"], animatic["revision"]): raise NovelDynamicShotError("dynamic shots upstream revisions are stale")
    shot_ids = {frame["shot_id"] for frame in storyboard["frames"]}
    if {item["shot_id"] for item in package["shot_routes"]} != shot_ids or {item["shot_id"] for item in package["reviews"]} != shot_ids: raise NovelDynamicShotError("dynamic routes and reviews must cover every shot")
    if package["budget"]["reserved"] + package["budget"]["spent"] > package["budget"]["limit"]: raise NovelDynamicShotError("dynamic budget exceeded")
    for job in package["jobs"]:
        if job["shot_id"] not in shot_ids: raise NovelDynamicShotError(f"job {job['id']} references unknown shot")
        if job["billable"] and (not job["confirm_billable"] or not job["upload_authorized"]): raise NovelDynamicShotError(f"billable job {job['id']} requires confirmation and upload authorization")
        if job["retry_count"] > job["max_retries"]: raise NovelDynamicShotError(f"job {job['id']} exceeded retry limit")
    return package
def write_dynamic_shots(project_dir: Path, package: dict[str, Any], overwrite=False) -> Path:
    project_dir = Path(project_dir).resolve(); package = validate_dynamic_shots(project_dir, package); path = project_dir / OUTPUT
    if path.exists() and not overwrite: raise NovelDynamicShotError(f"refusing to overwrite dynamic shots: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".dynamic-shots.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream: json.dump(package, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return path
def load_dynamic_shots(project_dir: Path) -> dict[str, Any]:
    try: payload = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e: raise NovelDynamicShotError(f"cannot read dynamic shots: {e}") from e
    return validate_dynamic_shots(project_dir, payload)
def summary(project_dir: Path) -> dict[str, Any] | None:
    try: package = load_dynamic_shots(project_dir)
    except (NovelDynamicShotError, ValueError): return None
    return {"revision": package["revision"], "shot_count": len(package["shot_routes"]), "ready_route_count": sum(1 for item in package["shot_routes"] if item["status"] == "READY"), "job_count": len(package["jobs"]), "queued_job_count": sum(1 for item in package["jobs"] if item["status"] == "QUEUED"), "approved_review_count": sum(1 for item in package["reviews"] if item["status"] == "APPROVED"), "budget_limit": package["budget"]["limit"], "budget_spent": package["budget"]["spent"]}
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try: result = {"output": write_dynamic_shots(args.project_dir, build_dynamic_shots(args.project_dir)).relative_to(args.project_dir.resolve()).as_posix()} if args.command == "create" else summary(args.project_dir)
    except (NovelDynamicShotError, OSError, ValueError) as error: print(f"novel_dynamic_shots: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
