#!/usr/bin/env python3
"""Evaluate the P14-03 twenty-video, repair, rerun, and throughput gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.package_project import REQUIRED_FILES
from scripts.project_state import DEFAULT_PROJECTS_DIR, load_run_state

AVERAGE_PRODUCTION_LIMIT_SECONDS = 30.0


class P14MilestoneError(ValueError):
    """Raised when P14-03 evidence is missing or does not meet its gates."""


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise P14MilestoneError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise P14MilestoneError(f"{label} must be a JSON object")
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_p14_03(
    twenty_report: dict[str, Any], repair_review: dict[str, Any], projects_dir: Path,
    average_limit_seconds: float = AVERAGE_PRODUCTION_LIMIT_SECONDS,
) -> dict[str, Any]:
    projects = twenty_report.get("projects")
    if (twenty_report.get("status") != "PASS" or twenty_report.get("verified_projects") != 20
            or not isinstance(projects, list) or len(projects) != 20):
        raise P14MilestoneError("a PASS report for twenty verified projects is required")
    ids = [item.get("project_id") for item in projects if isinstance(item, dict)]
    if len(ids) != 20 or len(set(ids)) != 20 or any(not isinstance(value, str) for value in ids):
        raise P14MilestoneError("the twenty-video report must contain unique project IDs")
    elapsed = [item.get("production_elapsed_seconds") for item in projects]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0 for value in elapsed):
        raise P14MilestoneError("all twenty projects need positive production-time evidence")
    average = sum(elapsed) / len(elapsed)
    production_time_pass = average <= average_limit_seconds

    reviewed = repair_review.get("projects")
    if not isinstance(reviewed, list) or len(reviewed) != 20:
        raise P14MilestoneError("repair assessment must contain exactly twenty projects")
    repair_ids = [item.get("project_id") for item in reviewed if isinstance(item, dict)]
    if len(repair_ids) != 20 or len(set(repair_ids)) != 20 or set(repair_ids) != set(ids):
        raise P14MilestoneError("repair assessment must cover each verified project exactly once")
    for item in reviewed:
        if (not isinstance(item.get("engineering_repair_required"), bool)
                or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()):
            raise P14MilestoneError("each repair assessment requires a boolean result and evidence")
    repaired = sum(item["engineering_repair_required"] for item in reviewed)
    no_repair_ratio = (20 - repaired) / 20
    repair_pass = no_repair_ratio >= 0.90

    rerun_candidates = [project_id for project_id in ids if (Path(projects_dir) / project_id / "cover-rerun.json").is_file()]
    if len(rerun_candidates) != 1:
        raise P14MilestoneError("exactly one executed cover-only rerun ledger is required")
    rerun_project_id = rerun_candidates[0]
    directory = Path(projects_dir) / rerun_project_id
    state = load_run_state(directory, rerun_project_id)
    if state["status"] != "READY_FOR_REVIEW":
        raise P14MilestoneError("the rerun project must remain READY_FOR_REVIEW")
    ledger = _load(directory / "cover-rerun.json", "cover rerun ledger")
    runs = ledger.get("runs")
    if ledger.get("project_id") != rerun_project_id or not isinstance(runs, list) or not runs:
        raise P14MilestoneError("cover rerun ledger is incomplete")
    latest = runs[-1]
    if (latest.get("old_sha256") == latest.get("new_sha256") or latest.get("video_regenerated") is not False
            or latest.get("project_state_changed") is not False):
        raise P14MilestoneError("cover-only rerun did not change only the intended artifact")
    expected_preserved = REQUIRED_FILES - {"cover.png"}
    if set(latest.get("preserved_package_files", [])) != expected_preserved:
        raise P14MilestoneError("cover rerun did not record every preserved package file")
    by_id = {item["project_id"]: item for item in projects}
    if _sha(directory / "final.mp4") != by_id[rerun_project_id].get("final_sha256"):
        raise P14MilestoneError("the video changed during the cover-only rerun")
    root_cover = directory / "cover.png"
    package_dir = directory / "publish-package"
    package_cover = package_dir / "cover.png"
    cover_sha = _sha(root_cover)
    if cover_sha != latest["new_sha256"] or _sha(package_cover) != cover_sha:
        raise P14MilestoneError("selected cover and package copy do not match the rerun result")
    cover_manifest = _load(directory / "cover-candidates.json", "cover candidate manifest")
    if cover_manifest.get("selected_sha256") != cover_sha or cover_manifest.get("selected") != latest.get("to_candidate"):
        raise P14MilestoneError("cover candidate selection does not match the rerun result")
    package = _load(directory / "package.json", "publish package manifest")
    if package.get("auto_publish") is not False:
        raise P14MilestoneError("the rerun package must retain human-only publishing")
    package_entries = {item.get("name"): item for item in package.get("files", []) if isinstance(item, dict)}
    if set(package_entries) != REQUIRED_FILES:
        raise P14MilestoneError("the rerun package manifest is incomplete")
    for name in REQUIRED_FILES:
        path = package_dir / name
        if not path.is_file() or _sha(path) != package_entries[name].get("sha256"):
            raise P14MilestoneError(f"rerun package checksum does not match: {name}")
    rerun_pass = True

    return {
        "schema_version": 1,
        "status": "PASS" if production_time_pass and repair_pass and rerun_pass else "FAIL",
        "verified_projects": 20,
        "production_time": {"average_seconds": round(average, 3), "maximum_seconds": round(max(elapsed), 3),
                            "limit_seconds": average_limit_seconds, "status": "PASS" if production_time_pass else "FAIL",
                            "measurement": "run.json created_at through READY_FOR_REVIEW"},
        "engineering_repairs": {"projects_requiring_repair": repaired, "projects_without_repair": 20 - repaired,
                                 "no_repair_ratio": no_repair_ratio, "minimum_ratio": 0.90,
                                 "status": "PASS" if repair_pass else "FAIL"},
        "partial_rerun": {"status": "PASS", "project_id": rerun_project_id,
                          "rerun_type": "cover-only", "video_regenerated": False,
                          "preserved_package_files": sorted(expected_preserved)},
        "gates_passed": 3 if production_time_pass and repair_pass and rerun_pass else sum((production_time_pass, repair_pass, rerun_pass)),
        "required_gates": 3,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "validation" / "p14-twenty-report.json")
    parser.add_argument("--repair-review", type=Path, default=ROOT / "validation" / "p14-repair-assessment.json")
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    parser.add_argument("--output", type=Path, default=ROOT / "validation" / "p14-milestone-report.json")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise P14MilestoneError(f"refusing to overwrite milestone report: {args.output}")
        result = evaluate_p14_03(_load(args.report, "twenty-video report"),
                                 _load(args.repair_review, "repair assessment"), args.projects_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"p14_milestone: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
