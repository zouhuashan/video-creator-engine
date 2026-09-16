#!/usr/bin/env python3
"""Audit local animatic rhythm, readability, and continuity gates."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.novel_anime_project import MANIFEST_NAME, load_project, utc_timestamp
from scripts.novel_animatic import load_animatic
from scripts.novel_shot_breakdown import load_shot_breakdown
from scripts.novel_storyboard import load_storyboard
SCHEMA_PATH = ROOT / "schemas" / "novel-animatic-review.schema.json"
OUTPUT = Path("animatic/review.json")
class NovelAnimaticReviewError(ValueError): pass
def _review(): return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}
def _finding(category, severity, entity, message):
    raw = f"{category}|{severity}|{entity}|{message}"; return {"id": f"ANIMF-{hashlib.sha256(raw.encode()).hexdigest()[:16].upper()}", "category": category, "severity": severity, "entity_id": entity, "message": message, "status": "OPEN"}
def build_review(project_dir: Path) -> dict[str, Any]:
    project = load_project(Path(project_dir) / MANIFEST_NAME); animatic = load_animatic(project_dir); shots = load_shot_breakdown(project_dir); storyboard = load_storyboard(project_dir); findings = []
    if not any(item["shot_ids"] for item in animatic["episodes"]): findings.append(_finding("RHYTHM", "BLOCKER", project["project_id"], "Animatic 没有可审核镜头"))
    for episode in animatic["episodes"]:
        if episode["temporary_audio"]["status"] != "READY": findings.append(_finding("ACTION_READABILITY", "BLOCKER", episode["episode_id"], "缺少临时音频，无法审核动作节奏"))
        if episode["subtitle_track"]["status"] != "READY": findings.append(_finding("RHYTHM", "BLOCKER", episode["episode_id"], "缺少字幕轨，无法审核集级预览"))
    return validate_review(project_dir, {"schema_version": 1, "project_id": project["project_id"], "ip_id": project["ip"]["id"], "animatic_revision": animatic["revision"], "shot_breakdown_revision": shots["revision"], "storyboard_revision": storyboard["revision"], "revision": 1, "created_at": utc_timestamp(), "updated_at": utc_timestamp(), "overall_status": "PASS" if not findings else "BLOCKED", "findings": findings, "human_review": _review()})
def _schema(payload):
    try: import jsonschema
    except ImportError: return
    errors = sorted(jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text()), format_checker=jsonschema.FormatChecker()).iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors: raise NovelAnimaticReviewError(f"animatic review schema violation at {'.'.join(map(str, errors[0].absolute_path))}: {errors[0].message}")
def validate_review(project_dir: Path, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict): raise NovelAnimaticReviewError("animatic review must be an object")
    report = deepcopy(payload); _schema(report); project = load_project(Path(project_dir) / MANIFEST_NAME); animatic = load_animatic(project_dir); shots = load_shot_breakdown(project_dir); storyboard = load_storyboard(project_dir)
    if report["project_id"] != project["project_id"] or report["ip_id"] != project["ip"]["id"]: raise NovelAnimaticReviewError("animatic review does not match project")
    if (report["animatic_revision"], report["shot_breakdown_revision"], report["storyboard_revision"]) != (animatic["revision"], shots["revision"], storyboard["revision"]): raise NovelAnimaticReviewError("animatic review upstream revisions are stale")
    ids = set()
    for item in report["findings"]:
        if item["id"] in ids: raise NovelAnimaticReviewError("duplicate animatic finding")
        ids.add(item["id"])
    expected = "PASS" if not any(item["severity"] == "BLOCKER" and item["status"] == "OPEN" for item in report["findings"]) else "BLOCKED"
    if report["overall_status"] != expected: raise NovelAnimaticReviewError("animatic review status does not match findings")
    return report
def write_review(project_dir: Path, report: dict[str, Any], overwrite=False) -> Path:
    project_dir = Path(project_dir).resolve(); report = validate_review(project_dir, report); path = project_dir / OUTPUT
    if path.exists() and not overwrite: raise NovelAnimaticReviewError(f"refusing to overwrite animatic review: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".animatic-review.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream: json.dump(report, stream, ensure_ascii=False, indent=2); stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return path
def load_review(project_dir: Path) -> dict[str, Any]:
    try: report = json.loads((Path(project_dir).resolve() / OUTPUT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e: raise NovelAnimaticReviewError(f"cannot read animatic review: {e}") from e
    return validate_review(project_dir, report)
def summary(project_dir: Path) -> dict[str, Any] | None:
    try: report = load_review(project_dir)
    except (NovelAnimaticReviewError, ValueError): return None
    return {"revision": report["revision"], "overall_status": report["overall_status"], "finding_count": len(report["findings"]), "blocker_count": sum(1 for item in report["findings"] if item["severity"] == "BLOCKER" and item["status"] == "OPEN"), "human_review_status": report["human_review"]["status"]}
def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("audit", "validate")); parser.add_argument("project_dir", type=Path); args = parser.parse_args()
    try: result = {"output": write_review(args.project_dir, build_review(args.project_dir)).relative_to(args.project_dir.resolve()).as_posix()} if args.command == "audit" else summary(args.project_dir)
    except (NovelAnimaticReviewError, OSError, ValueError) as error: print(f"novel_animatic_review: {error}", file=sys.stderr); return 1
    print(json.dumps({"status": "PASS", "result": result}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
