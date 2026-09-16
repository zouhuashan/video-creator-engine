#!/usr/bin/env python3
"""Create and update the P14 post-publication metric observation ledger."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.project_state import DEFAULT_PROJECTS_DIR, load_run_state

DEFAULT_TRACKER = ROOT / "validation" / "p14-metrics.json"
RATE_FIELDS = {"completion_rate", "retention_3s", "retention_5s"}
COUNT_FIELDS = {"likes", "comments", "favorites", "shares", "follows"}
METRIC_FIELDS = RATE_FIELDS | COUNT_FIELDS | {"views"}


class PilotMetricsError(ValueError):
    """Raised when metric observations lack valid publication evidence."""


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PilotMetricsError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise PilotMetricsError(f"{label} must be a JSON object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def create_tracker(validation_report: dict[str, Any], projects_dir: Path) -> dict[str, Any]:
    projects = validation_report.get("projects")
    if validation_report.get("status") != "PASS" or validation_report.get("verified_projects") != 10:
        raise PilotMetricsError("P14 metrics require a PASS validation report for ten projects")
    if not isinstance(projects, list) or len(projects) != 10:
        raise PilotMetricsError("P14 metrics require exactly ten validated projects")
    ids = [item.get("project_id") for item in projects if isinstance(item, dict)]
    if len(ids) != 10 or len(set(ids)) != 10 or any(not isinstance(item, str) for item in ids):
        raise PilotMetricsError("P14 metrics require ten unique project IDs")
    records = []
    for project_id in ids:
        state = load_run_state(Path(projects_dir) / project_id, project_id)
        if state["status"] not in {"READY_FOR_REVIEW", "PUBLISHED_MANUALLY"}:
            raise PilotMetricsError(f"{project_id} is not ready for publication")
        records.append({"project_id": project_id,
                        "collection_status": "awaiting_manual_publish" if state["status"] == "READY_FOR_REVIEW" else "awaiting_metrics",
                        "observations": []})
    return {"schema_version": 1, "cohort_id": "p14-first-ten", "status": "tracking",
            "metric_definitions": {"rates": "percentage from 0 to 100", "counts": "non-negative integer platform totals",
                                   "views": "positive integer denominator shown by the platform"},
            "publication_policy": "Only record observations after run.json reaches PUBLISHED_MANUALLY.",
            "projects": records}


def extend_tracker(tracker_path: Path, validation_report: dict[str, Any], projects_dir: Path) -> dict[str, Any]:
    """Add newly validated projects while preserving all prior observations."""
    if validation_report.get("status") != "PASS" or validation_report.get("verified_projects") != 20:
        raise PilotMetricsError("P14 metrics can only extend from a PASS twenty-project report")
    validated = validation_report.get("projects")
    if not isinstance(validated, list) or len(validated) != 20:
        raise PilotMetricsError("P14 metrics extension requires twenty validated projects")
    ids = [item.get("project_id") for item in validated if isinstance(item, dict)]
    if len(ids) != 20 or len(set(ids)) != 20 or any(not isinstance(value, str) for value in ids):
        raise PilotMetricsError("P14 metrics extension requires twenty unique project IDs")
    tracker = _load(tracker_path, "metrics tracker")
    if tracker.get("schema_version") != 1 or not isinstance(tracker.get("projects"), list):
        raise PilotMetricsError("metrics tracker schema is invalid")
    records = tracker["projects"]
    existing_ids = [item.get("project_id") for item in records if isinstance(item, dict)]
    if len(existing_ids) != len(records) or len(existing_ids) != len(set(existing_ids)) or not set(existing_ids).issubset(ids):
        raise PilotMetricsError("existing metrics entries must be unique members of the twenty-project report")
    known = set(existing_ids)
    for project_id in ids:
        if project_id in known:
            continue
        state = load_run_state(Path(projects_dir) / project_id, project_id)
        if state["status"] not in {"READY_FOR_REVIEW", "PUBLISHED_MANUALLY"}:
            raise PilotMetricsError(f"{project_id} is not ready for publication")
        records.append({"project_id": project_id,
                        "collection_status": "awaiting_manual_publish" if state["status"] == "READY_FOR_REVIEW" else "awaiting_metrics",
                        "observations": []})
    tracker["cohort_id"] = "p14-first-twenty"
    tracker["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    _write(tracker_path, tracker)
    return tracker


def validate_metrics(metrics: dict[str, Any]) -> dict[str, int | float]:
    if set(metrics) != METRIC_FIELDS:
        missing, extra = METRIC_FIELDS - set(metrics), set(metrics) - METRIC_FIELDS
        raise PilotMetricsError(f"metric fields mismatch (missing={sorted(missing)}, extra={sorted(extra)})")
    cleaned: dict[str, int | float] = {}
    for name in RATE_FIELDS:
        value = metrics[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
            raise PilotMetricsError(f"{name} must be a percentage from 0 to 100")
        cleaned[name] = value
    for name in COUNT_FIELDS | {"views"}:
        value = metrics[name]
        minimum = 1 if name == "views" else 0
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise PilotMetricsError(f"{name} must be an integer >= {minimum}")
        cleaned[name] = value
    return {name: cleaned[name] for name in sorted(cleaned)}


def record_metrics(
    tracker_path: Path,
    project_id: str,
    projects_dir: Path,
    metrics: dict[str, Any],
    observed_at: str,
    platform: str,
    source: str,
) -> dict[str, Any]:
    state = load_run_state(Path(projects_dir) / project_id, project_id)
    if state["status"] != "PUBLISHED_MANUALLY":
        raise PilotMetricsError(f"{project_id} must be manually published before metrics can be recorded")
    try:
        parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise PilotMetricsError("observed_at must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise PilotMetricsError("observed_at must include a timezone")
    if not platform.strip() or not source.strip():
        raise PilotMetricsError("platform and source reference are required")
    sample = validate_metrics(metrics)
    tracker = _load(tracker_path, "metrics tracker")
    matches = [item for item in tracker.get("projects", []) if isinstance(item, dict) and item.get("project_id") == project_id]
    if len(matches) != 1:
        raise PilotMetricsError(f"{project_id} must appear exactly once in the P14 metrics tracker")
    record = matches[0]
    observations = record.get("observations")
    if not isinstance(observations, list):
        raise PilotMetricsError(f"{project_id} observation list is invalid")
    if any(item.get("observed_at") == observed_at for item in observations if isinstance(item, dict)):
        raise PilotMetricsError(f"an observation already exists for {project_id} at {observed_at}")
    observations.append({"observed_at": observed_at, "platform": platform.strip(), "source": source.strip(), "metrics": sample})
    observations.sort(key=lambda item: item["observed_at"])
    record["collection_status"] = "recorded"
    record["observations"] = observations
    tracker["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    _write(tracker_path, tracker)
    return tracker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap = subparsers.add_parser("bootstrap", help="initialize ten empty observations")
    bootstrap.add_argument("--validation-report", type=Path, default=ROOT / "validation" / "p14-ten-report.json")
    bootstrap.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    bootstrap.add_argument("--output", type=Path, default=DEFAULT_TRACKER)
    record = subparsers.add_parser("record", help="append a post-publication observation")
    record.add_argument("--tracker", type=Path, default=DEFAULT_TRACKER)
    record.add_argument("--project-id", required=True)
    record.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    record.add_argument("--metrics-file", type=Path, required=True)
    record.add_argument("--observed-at", required=True)
    record.add_argument("--platform", required=True)
    record.add_argument("--source", required=True, help="reference to the platform export, screenshot, or manual report")
    extend = subparsers.add_parser("extend", help="extend the tracker from ten to twenty validated projects")
    extend.add_argument("--validation-report", type=Path, default=ROOT / "validation" / "p14-twenty-report.json")
    extend.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    extend.add_argument("--tracker", type=Path, default=DEFAULT_TRACKER)
    args = parser.parse_args()
    try:
        if args.command == "bootstrap":
            if args.output.exists():
                raise PilotMetricsError(f"refusing to overwrite existing metrics tracker: {args.output}")
            result = create_tracker(_load(args.validation_report, "ten-project validation report"), args.projects_dir)
            _write(args.output, result)
        elif args.command == "extend":
            result = extend_tracker(args.tracker, _load(args.validation_report, "twenty-project validation report"), args.projects_dir)
        else:
            result = record_metrics(args.tracker, args.project_id, args.projects_dir,
                                    _load(args.metrics_file, "metrics sample"), args.observed_at,
                                    args.platform, args.source)
    except (PilotMetricsError, OSError, ValueError) as error:
        print(f"pilot_metrics: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "projects": len(result["projects"]), "tracker": str(args.output if args.command == "bootstrap" else args.tracker)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
