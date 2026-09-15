#!/usr/bin/env python3
"""Enforce auto-fix policy and aggregate final QC evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

try:
    from .project_state import StateError, load_run_state, transition_project
except ImportError:
    from project_state import StateError, load_run_state, transition_project

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "auto-fix.json"
ISSUE_ID = re.compile(r"FIX\d{3,}\Z")
REPORT_FILES = ("technical-qc.json", "content-qc.json", "visual-qc.json")
EXPECTED_CHECKS = {
    "technical-qc.json": {
        "resolution", "aspect_ratio", "fps", "codec", "duration", "black_frames",
        "frozen_frames", "silence", "clipping", "audio_video_sync", "subtitle_bounds",
        "subtitle_occlusion", "encoding_success", "file_integrity",
    },
    "content-qc.json": {
        "typos", "factual_accuracy", "numeric_accuracy", "brand_names",
        "platform_sensitive_language", "duplicate_content", "unsupported_absolute_claims",
        "first_three_seconds_hook", "conclusion_clarity", "call_to_action",
    },
    "visual-qc.json": {
        "shot_too_long", "repeated_visuals", "subtitle_density", "abnormal_empty_space",
        "incorrect_crop", "key_information_ui_occlusion", "text_background_contrast",
    },
}


class AutoFixError(ValueError):
    """Raised when an auto-fix request or QC aggregate is invalid."""


class FixExecutor(Protocol):
    """Replaceable edit/render boundary used for approved low-risk fixes."""

    def apply(self, issue: dict[str, Any]) -> dict[str, Any]: ...


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AutoFixError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise AutoFixError(f"{label} must be a JSON object")
    return value


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = _load_json(path, "auto-fix config")
    if config.get("schema_version") != 1 or len(config.get("allowed", [])) != 6 or len(config.get("forbidden", [])) != 4:
        raise AutoFixError("unsupported or incomplete auto-fix config")
    if set(config["allowed"]) & set(config["forbidden"]):
        raise AutoFixError("auto-fix allowed and forbidden categories overlap")
    return config


def plan_auto_fixes(request: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    active = config or load_config()
    issues = request.get("issues")
    if request.get("schema_version") != 1 or not isinstance(issues, list):
        raise AutoFixError("auto-fix request must contain schema_version 1 and issues")
    known = set(active["allowed"]) | set(active["forbidden"])
    normalized, seen = [], set()
    for issue in issues:
        if not isinstance(issue, dict) or set(issue) != {"issue_id", "category", "target", "reason", "parameters"}:
            raise AutoFixError("each fix issue must contain exactly the required fields")
        issue_id, category = issue["issue_id"], issue["category"]
        if not isinstance(issue_id, str) or not ISSUE_ID.fullmatch(issue_id) or issue_id in seen:
            raise AutoFixError("fix issue IDs must be unique and match FIX001")
        if category not in known:
            raise AutoFixError(f"unknown fix category: {category}")
        if not isinstance(issue["target"], str) or not issue["target"].strip() or not isinstance(issue["reason"], str) or not issue["reason"].strip():
            raise AutoFixError(f"fix issue {issue_id} requires target and reason")
        if not isinstance(issue["parameters"], dict):
            raise AutoFixError(f"fix issue {issue_id} parameters must be an object")
        normalized.append({**issue, "target": issue["target"].strip(), "reason": issue["reason"].strip()})
        seen.add(issue_id)
    forbidden = [issue for issue in normalized if issue["category"] in active["forbidden"]]
    allowed = [issue for issue in normalized if issue["category"] in active["allowed"]]
    return {
        "schema_version": 1,
        "status": "SCRIPT_REVIEW_REQUIRED" if forbidden else "READY",
        "auto_fix_issues": allowed,
        "script_review_issues": forbidden,
        "route": active["forbidden_route"] if forbidden else "AUTO_FIX_EXECUTOR",
        "post_fix_requirement": active["post_fix_requirement"] if allowed and not forbidden else None,
    }


def execute_auto_fixes(plan: dict[str, Any], executor: FixExecutor) -> dict[str, Any]:
    if plan.get("status") != "READY":
        raise AutoFixError("auto-fix execution is blocked until script review resolves forbidden changes")
    results = []
    for issue in plan.get("auto_fix_issues", []):
        result = executor.apply(issue)
        if not isinstance(result, dict) or result.get("status") != "APPLIED":
            raise AutoFixError(f"executor did not apply {issue['issue_id']}")
        results.append({"issue_id": issue["issue_id"], **result})
    completed_at = timestamp()
    return {
        "schema_version": 1,
        "status": "RERUN_QC_REQUIRED" if results else "NO_FIXES",
        "completed_at": completed_at,
        "results": results,
    }


def write_auto_fix_plan(project_dir: Path, request_file: Path) -> dict[str, Any]:
    directory = Path(project_dir).resolve()
    plan = plan_auto_fixes(_load_json(request_file, "auto-fix request"))
    output = directory / "qc" / "auto-fix-plan.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**plan, "output": str(output)}


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(content)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _markdown(report: dict[str, Any]) -> str:
    lines = ["# QC Report", "", f"- Project: `{report['project_id']}`", f"- Status: **{report['status']}**", "", "## Checks", ""]
    for group, group_report in report["reports"].items():
        lines.append(f"### {group.replace('_', ' ').title()}")
        lines.append("")
        for name, passed in group_report["checks"].items():
            lines.append(f"- {'PASS' if passed else 'FAIL'} · `{name}`")
        lines.append("")
    if report["failed_reports"]:
        lines.extend(["## Failed reports", "", *[f"- `{name}`" for name in report["failed_reports"]], ""])
    return "\n".join(lines)


def finalize_qc(directory: Path, project_id: str) -> dict[str, Any]:
    directory = Path(directory).resolve()
    state = load_run_state(directory, project_id)
    if state["status"] != "EDITED":
        raise StateError(f"QC finalization requires status EDITED; current status is {state['status']}")
    reports: dict[str, dict[str, Any]] = {}
    for filename in REPORT_FILES:
        report = _load_json(directory / "qc" / filename, filename)
        checks = report.get("checks")
        if report.get("status") not in {"PASS", "FAIL"} or not isinstance(checks, dict) or not checks:
            raise AutoFixError(f"{filename} is missing a valid status or checks")
        if set(checks) != EXPECTED_CHECKS[filename] or any(type(value) is not bool for value in checks.values()):
            raise AutoFixError(f"{filename} does not contain the complete required check set")
        reports[filename.removesuffix(".json").replace("-", "_")] = report
    auto_fix_report = directory / "qc" / "auto-fix.json"
    if auto_fix_report.is_file():
        fix = _load_json(auto_fix_report, "auto-fix.json")
        if fix.get("status") == "RERUN_QC_REQUIRED":
            fixed_at = fix.get("completed_at")
            if not isinstance(fixed_at, str) or any(not isinstance(report.get("generated_at"), str) or report["generated_at"] <= fixed_at for report in reports.values()):
                raise AutoFixError("all QC reports must be regenerated after automatic fixes")
    failed = [name for name, report in reports.items() if report["status"] != "PASS" or not all(report["checks"].values())]
    aggregate = {
        "schema_version": 1, "project_id": project_id, "status": "PASS" if not failed else "FAIL",
        "generated_at": timestamp(), "failed_reports": failed, "reports": reports,
    }
    _atomic_write(directory / "qc.json", json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(directory / "qc-report.md", _markdown(aggregate) + "\n")
    if failed:
        return {**aggregate, "state": state["status"], "outputs": ["qc.json", "qc-report.md"]}
    new_state = transition_project(directory, project_id, "QC_PASS", note="technical, content, and visual QC passed")
    return {**aggregate, "state": new_state["status"], "outputs": ["qc.json", "qc-report.md"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("project_dir", type=Path)
    plan_parser.add_argument("--request-file", type=Path, required=True)
    final_parser = subparsers.add_parser("finalize")
    final_parser.add_argument("project_dir", type=Path)
    final_parser.add_argument("project_id")
    args = parser.parse_args()
    try:
        result = write_auto_fix_plan(args.project_dir, args.request_file) if args.command == "plan" else finalize_qc(args.project_dir, args.project_id)
    except (AutoFixError, StateError) as error:
        print(f"auto_fix: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["status"] in {"READY", "PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
