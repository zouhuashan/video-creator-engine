#!/usr/bin/env python3
"""Independently verify P14 pilot batches and the ten-video milestone."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters.video import inspect_final_output  # noqa: E402
from scripts.package_project import REQUIRED_FILES  # noqa: E402
from scripts.project_state import load_run_state  # noqa: E402

REPORT_PATH = ROOT / "validation" / "p14-first-five-report.json"
REQUIRED_CHECKS = {"stable_generation", "style", "duration", "subtitles", "voice", "hook"}


class PilotValidationError(ValueError):
    """Raised when the five-video milestone lacks real evidence."""


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PilotValidationError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise PilotValidationError(f"{label} must be a JSON object")
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_first_five(
    report: dict[str, Any], projects_dir: Path,
    inspector: Callable[[Path], dict[str, Any]] = inspect_final_output,
) -> dict[str, Any]:
    projects = report.get("projects")
    if report.get("schema_version") != 1 or not isinstance(projects, list) or len(projects) != 5:
        raise PilotValidationError("P14-01 requires exactly five recorded projects")
    ids = [item.get("project_id") for item in projects if isinstance(item, dict)]
    if len(ids) != 5 or len(set(ids)) != 5 or any(not isinstance(value, str) for value in ids):
        raise PilotValidationError("pilot project IDs must be five unique strings")
    verified = []
    for recorded in projects:
        project_id = recorded["project_id"]
        directory = Path(projects_dir) / project_id
        evaluation = _load(directory / "pilot-evaluation.json", f"{project_id} pilot evaluation")
        checks = evaluation.get("checks")
        if (
            recorded.get("status") != "PASS" or evaluation.get("status") != "PASS"
            or not isinstance(checks, dict) or set(checks) != REQUIRED_CHECKS
            or any(value is not True for value in checks.values())
        ):
            raise PilotValidationError(f"{project_id} has incomplete pilot checks")
        state = load_run_state(directory, project_id)
        if state["status"] != "READY_FOR_REVIEW":
            raise PilotValidationError(f"{project_id} has not reached READY_FOR_REVIEW")
        try:
            created_at = datetime.fromisoformat(state["created_at"].replace("Z", "+00:00"))
            ready_at = datetime.fromisoformat(state["history"][-1]["at"].replace("Z", "+00:00"))
            production_elapsed = (ready_at - created_at).total_seconds()
        except (KeyError, TypeError, ValueError) as error:
            raise PilotValidationError(f"{project_id} lacks valid production timing evidence") from error
        if production_elapsed <= 0:
            raise PilotValidationError(f"{project_id} production timing evidence is not positive")
        qc = _load(directory / "qc.json", f"{project_id} QC")
        if qc.get("status") != "PASS" or qc.get("failed_reports"):
            raise PilotValidationError(f"{project_id} QC is not PASS")
        package = _load(directory / "package.json", f"{project_id} package")
        if {item.get("name") for item in package.get("files", []) if isinstance(item, dict)} != REQUIRED_FILES:
            raise PilotValidationError(f"{project_id} package is incomplete")
        video = directory / "final.mp4"
        if not video.is_file() or _sha(video) != evaluation.get("final_sha256"):
            raise PilotValidationError(f"{project_id} final video is missing or changed")
        media = inspector(video)
        if (
            media.get("width") != 1080 or media.get("height") != 1920
            or abs(float(media.get("fps", 0)) - 30) > 0.001
            or media.get("video_codec") != "h264" or media.get("audio_codec") != "aac"
            or not 45 <= float(media.get("duration_seconds", 0)) <= 90
        ):
            raise PilotValidationError(f"{project_id} final media does not meet delivery standard")
        verified.append({"project_id": project_id, "duration_seconds": media["duration_seconds"],
                         "production_elapsed_seconds": round(production_elapsed, 3),
                         "final_sha256": evaluation["final_sha256"], "checks": checks})
    return {"schema_version": 1, "status": "PASS", "verified_projects": 5,
            "required_projects": 5, "projects": verified}


def validate_first_ten(
    first_report: dict[str, Any], second_report: dict[str, Any], projects_dir: Path,
    inspector: Callable[[Path], dict[str, Any]] = inspect_final_output,
) -> dict[str, Any]:
    """Independently verify both five-project batches as one ten-video cohort."""
    if first_report.get("status") != "PASS" or second_report.get("status") != "PASS":
        raise PilotValidationError("both P14 batches must report PASS")
    first = validate_first_five(first_report, projects_dir, inspector)
    second = validate_first_five(second_report, projects_dir, inspector)
    projects = first["projects"] + second["projects"]
    ids = [item["project_id"] for item in projects]
    if len(ids) != 10 or len(set(ids)) != 10:
        raise PilotValidationError("P14-02 requires ten unique projects across both batches")
    return {"schema_version": 1, "status": "PASS", "verified_projects": 10,
            "required_projects": 10, "batches": [first_report.get("batch_id"), second_report.get("batch_id")],
            "projects": projects}


def validate_first_twenty(
    reports: list[dict[str, Any]], projects_dir: Path,
    inspector: Callable[[Path], dict[str, Any]] = inspect_final_output,
) -> dict[str, Any]:
    """Independently verify four five-project batches as one twenty-video cohort."""
    if len(reports) != 4:
        raise PilotValidationError("P14-03 requires four five-project reports")
    if any(report.get("status") != "PASS" for report in reports):
        raise PilotValidationError("all four P14 batches must report PASS")
    verified_batches = [validate_first_five(report, projects_dir, inspector) for report in reports]
    projects = [project for batch in verified_batches for project in batch["projects"]]
    ids = [item["project_id"] for item in projects]
    if len(ids) != 20 or len(set(ids)) != 20:
        raise PilotValidationError("P14-03 requires twenty unique projects across four batches")
    return {"schema_version": 1, "status": "PASS", "verified_projects": 20,
            "required_projects": 20, "batches": [report.get("batch_id") for report in reports],
            "projects": projects}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--second-report", type=Path)
    parser.add_argument("--additional-report", action="append", type=Path, default=[])
    parser.add_argument("--required-projects", type=int, choices={5, 10, 20}, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--projects-dir", type=Path, default=ROOT / "projects")
    args = parser.parse_args()
    try:
        report = _load(args.report, "P14 report")
        if args.second_report and args.additional_report:
            raise PilotValidationError("use --second-report or --additional-report, not both")
        others = ([ _load(args.second_report, "P14 second report") ] if args.second_report
                  else [_load(path, "additional P14 report") for path in args.additional_report])
        reports = [report, *others]
        if args.required_projects == 20:
            result = validate_first_twenty(reports, args.projects_dir)
        elif args.required_projects == 10:
            if len(reports) != 2:
                raise PilotValidationError("ten-project validation requires two five-project reports")
            result = validate_first_ten(reports[0], reports[1], args.projects_dir)
        else:
            if len(reports) != 1:
                raise PilotValidationError("five-project validation accepts one report")
            result = validate_first_five(report, args.projects_dir)
        if args.output:
            if args.output.exists():
                raise PilotValidationError(f"refusing to overwrite validation result: {args.output}")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except PilotValidationError as error:
        print(f"pilot_validation: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
