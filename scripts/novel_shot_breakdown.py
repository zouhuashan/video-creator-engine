#!/usr/bin/env python3
"""Break script scenes into stable shots with camera grammar and continuity states."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp
from scripts.novel_asset_review import load_asset_review
from scripts.novel_episode_script import load_script_package
SCHEMA_PATH = ROOT / "schemas" / "novel-shot-breakdown.schema.json"
OUTPUT = Path("storyboard/shot-breakdown.json")
class NovelShotBreakdownError(ValueError): pass
def signature(payload: dict[str, Any]) -> str: return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def _review(): return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}
def _state(scene: dict[str, Any]) -> dict[str, Any]:
    payload = {"location_id": scene["location_id"], "character_ids": scene["character_ids"], "prop_state_ids": [], "emotion": ""}
    return {**payload, "continuity_signature": signature(payload)}
def build_shot_breakdown(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); scripts = load_script_package(project_dir); asset_review = load_asset_review(project_dir); now = utc_timestamp(); scenes = []
    for script in scripts["episode_scripts"]:
        for scene in script["scenes"]:
            shot_id = f"SHOT-{scene['id']}-001"; state = _state(scene); shot_payload = {"id": shot_id, "sequence": 1, "shot_type": "WIDE", "framing": "竖屏全景", "angle": "平视", "movement": "静态", "lens": "35mm", "duration_seconds": max(1.0, sum(float(unit["estimated_duration_seconds"]) for unit in scene["units"])), "start_state": state, "end_state": state, "reference_ids": [], "human_review": _review()}; shot = {**shot_payload, "continuity_signature": signature({key: shot_payload[key] for key in ("id", "sequence", "shot_type", "framing", "angle", "movement", "lens", "duration_seconds", "start_state", "end_state", "reference_ids")})}; scenes.append({"scene_id": scene["id"], "episode_id": script["episode_id"], "location_id": scene["location_id"], "shot_ids": [shot_id], "shots": [shot], "human_review": _review()})
    return validate_shot_breakdown(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "script_revision": scripts["revision"], "asset_review_revision": asset_review["revision"], "revision": 1, "created_at": now, "updated_at": now, "scene_breakdowns": scenes})
def _schema(payload):
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors: raise NovelShotBreakdownError(f"shot schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")
def validate_shot_breakdown(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelShotBreakdownError("shot breakdown must be an object")
    package = deepcopy(payload); _schema(package); project = load_project(Path(project_dir) / MANIFEST_NAME); scripts = load_script_package(project_dir); asset_review = load_asset_review(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]: raise NovelShotBreakdownError("shot breakdown does not match project")
    if package["script_revision"] != scripts["revision"] or package["asset_review_revision"] != asset_review["revision"]: raise NovelShotBreakdownError("shot breakdown upstream revisions are stale")
    expected = {scene["id"]: (script["episode_id"], scene["location_id"]) for script in scripts["episode_scripts"] for scene in script["scenes"]}
    if {item["scene_id"] for item in package["scene_breakdowns"]} != set(expected): raise NovelShotBreakdownError("shot breakdown must cover every script scene")
    refs = {ref["id"] for item in asset_review["reference_packages"] for ref in item["references"]}
    shot_ids = set()
    for scene in package["scene_breakdowns"]:
        if scene["episode_id"] != expected[scene["scene_id"]][0] or scene["location_id"] != expected[scene["scene_id"]][1] or scene["shot_ids"] != [shot["id"] for shot in scene["shots"]]: raise NovelShotBreakdownError(f"scene breakdown mismatch for {scene['scene_id']}")
        for shot in scene["shots"]:
            if shot["id"] in shot_ids or shot["continuity_signature"] != signature({key: shot[key] for key in ("id", "sequence", "shot_type", "framing", "angle", "movement", "lens", "duration_seconds", "start_state", "end_state", "reference_ids")}): raise NovelShotBreakdownError(f"shot continuity signature drift for {shot['id']}")
            shot_ids.add(shot["id"])
            if set(shot["reference_ids"]) - refs: raise NovelShotBreakdownError(f"shot {shot['id']} references unknown visual asset")
            for state in (shot["start_state"], shot["end_state"]):
                if state["continuity_signature"] != signature({key: state[key] for key in ("location_id", "character_ids", "prop_state_ids", "emotion")}): raise NovelShotBreakdownError(f"shot {shot['id']} state signature drift")
    return package
def write_shot_breakdown(project_dir: Path, package: dict[str, Any], overwrite=False) -> Path:
    project_dir = Path(project_dir).resolve(); package = validate_shot_breakdown(project_dir, package); path = project_dir / OUTPUT
    if path.exists() and not overwrite: raise NovelShotBreakdownError(f"refusing to overwrite shot breakdown: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".shot-breakdown.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream: json.dump(package, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return path
def load_shot_breakdown(project_dir: Path) -> dict[str, Any]:
    try: payload = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e: raise NovelShotBreakdownError(f"cannot read shot breakdown: {e}") from e
    return validate_shot_breakdown(project_dir, payload)
def summary(project_dir: Path) -> dict[str, Any] | None:
    try: package = load_shot_breakdown(project_dir)
    except (NovelShotBreakdownError, ValueError): return None
    shots = [shot for scene in package["scene_breakdowns"] for shot in scene["shots"]]
    return {"revision": package["revision"], "scene_count": len(package["scene_breakdowns"]), "shot_count": len(shots), "reviewed_scene_count": sum(1 for scene in package["scene_breakdowns"] if scene["human_review"]["status"] == "APPROVED"), "reviewed_shot_count": sum(1 for shot in shots if shot["human_review"]["status"] == "APPROVED")}
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try: result = {"output": write_shot_breakdown(args.project_dir, build_shot_breakdown(args.project_dir)).relative_to(args.project_dir.resolve()).as_posix()} if args.command == "create" else summary(args.project_dir)
    except (NovelShotBreakdownError, OSError, ValueError) as error: print(f"novel_shot_breakdown: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
