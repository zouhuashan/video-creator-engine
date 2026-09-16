#!/usr/bin/env python3
"""Create static storyboard frame slots and validate shot timing/continuity."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp
from scripts.novel_asset_review import load_asset_review
from scripts.novel_shot_breakdown import load_shot_breakdown
SCHEMA_PATH = ROOT / "schemas" / "novel-storyboard.schema.json"
OUTPUT = Path("storyboard/storyboard.json")
class NovelStoryboardError(ValueError): pass
def signature(payload): return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def _review(): return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}
def build_storyboard(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); shots = load_shot_breakdown(project_dir); assets = load_asset_review(project_dir); now = utc_timestamp(); frames = []
    for scene in shots["scene_breakdowns"]:
        for shot in scene["shots"]:
            start_state = shot["start_state"]["continuity_signature"]; end_state = shot["end_state"]["continuity_signature"]
            start = {"id": f"FRAME-{shot['id']}-START", "status": "PLANNED", "asset_id": None, "reference_ids": [], "state_signature": start_state, "note": "首帧待绘制"}
            end = {"id": f"FRAME-{shot['id']}-END", "status": "PLANNED", "asset_id": None, "reference_ids": [], "state_signature": end_state, "note": "尾帧待绘制"}
            payload = {"shot_id": shot["id"], "duration_seconds": shot["duration_seconds"], "start": start, "end": end, "human_review": _review()}
            frames.append({**payload, "continuity_signature": signature(payload)})
    return validate_storyboard(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "shot_breakdown_revision": shots["revision"], "asset_review_revision": assets["revision"], "revision": 1, "created_at": now, "updated_at": now, "frames": frames})
def _schema(payload):
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors: raise NovelStoryboardError(f"storyboard schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")
def validate_storyboard(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelStoryboardError("storyboard must be an object")
    package = deepcopy(payload); _schema(package); project = load_project(Path(project_dir) / MANIFEST_NAME); shots = load_shot_breakdown(project_dir); assets = load_asset_review(project_dir)
    if package["project_id"] != project["project_id"] or package["ip_id"] != project["ip"]["id"]: raise NovelStoryboardError("storyboard does not match project")
    if package["shot_breakdown_revision"] != shots["revision"] or package["asset_review_revision"] != assets["revision"]: raise NovelStoryboardError("storyboard upstream revisions are stale")
    shot_map = {shot["id"]: shot for scene in shots["scene_breakdowns"] for shot in scene["shots"]}; frame_ids = set(); reference_ids = {ref["id"] for item in assets["reference_packages"] for ref in item["references"]}
    if {item["shot_id"] for item in package["frames"]} != set(shot_map): raise NovelStoryboardError("storyboard must cover every shot")
    for item in package["frames"]:
        shot = shot_map[item["shot_id"]]
        if abs(item["duration_seconds"] - shot["duration_seconds"]) > 0.001: raise NovelStoryboardError(f"storyboard duration mismatch for {item['shot_id']}")
        expected = {"shot_id": item["shot_id"], "duration_seconds": item["duration_seconds"], "start": item["start"], "end": item["end"], "human_review": item["human_review"]}
        if item["continuity_signature"] != signature(expected): raise NovelStoryboardError(f"storyboard continuity signature drift for {item['shot_id']}")
        for frame in (item["start"], item["end"]):
            if frame["id"] in frame_ids: raise NovelStoryboardError("duplicate storyboard frame ID")
            frame_ids.add(frame["id"])
            if set(frame["reference_ids"]) - reference_ids: raise NovelStoryboardError(f"frame {frame['id']} references unknown reference")
            if frame["status"] == "SELECTED" and not frame["asset_id"]: raise NovelStoryboardError(f"selected frame {frame['id']} requires an asset")
    return package
def write_storyboard(project_dir: Path, package: dict[str, Any], overwrite=False) -> Path:
    project_dir = Path(project_dir).resolve(); package = validate_storyboard(project_dir, package); path = project_dir / OUTPUT
    if path.exists() and not overwrite: raise NovelStoryboardError(f"refusing to overwrite storyboard: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".storyboard.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream: json.dump(package, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return path
def load_storyboard(project_dir: Path) -> dict[str, Any]:
    try: payload = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e: raise NovelStoryboardError(f"cannot read storyboard: {e}") from e
    return validate_storyboard(project_dir, payload)
def summary(project_dir: Path) -> dict[str, Any] | None:
    try: package = load_storyboard(project_dir)
    except (NovelStoryboardError, ValueError): return None
    return {"revision": package["revision"], "frame_count": len(package["frames"]), "selected_frame_count": sum(1 for item in package["frames"] for frame in (item["start"], item["end"]) if frame["status"] == "SELECTED"), "approved_shot_count": sum(1 for item in package["frames"] if item["human_review"]["status"] == "APPROVED")}
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("create", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try: result = {"output": write_storyboard(args.project_dir, build_storyboard(args.project_dir)).relative_to(args.project_dir.resolve()).as_posix()} if args.command == "create" else summary(args.project_dir)
    except (NovelStoryboardError, OSError, ValueError) as error: print(f"novel_storyboard: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
