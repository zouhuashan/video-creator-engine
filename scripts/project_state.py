#!/usr/bin/env python3
"""Initialize and advance the VideoCreator project lifecycle in run.json."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECTS_DIR = ROOT / "projects"
SCHEMA_VERSION = 1
STAGES = (
    "CREATED",
    "RESEARCHED",
    "SCRIPTED",
    "STORYBOARDED",
    "ASSETS_READY",
    "VOICE_READY",
    "EDITED",
    "QC_PASS",
    "PACKAGED",
    "READY_FOR_REVIEW",
    "PUBLISHED_MANUALLY",
)
PROJECT_ID_PATTERN = re.compile(r"\d{8}-[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class StateError(ValueError):
    """Raised when a requested project state operation is invalid."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def project_dir(project_id: str, projects_dir: Path = DEFAULT_PROJECTS_DIR) -> Path:
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise StateError(f"invalid project ID: {project_id}")
    return projects_dir / project_id


def state_path(directory: Path) -> Path:
    return directory / "run.json"


def write_state(directory: Path, state: dict[str, Any]) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=".run.json.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temp_name, state_path(directory))
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def initialize_run_state(directory: Path, project_id: str) -> dict[str, Any]:
    """Create the initial run.json for a newly reserved project directory."""
    directory = Path(directory)
    if directory.name != project_id or not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise StateError("project directory name must match its valid project ID")
    if not directory.is_dir():
        raise StateError(f"project directory does not exist: {directory}")
    path = state_path(directory)
    if path.exists():
        raise FileExistsError(f"state already exists: {path}")

    timestamp = utc_timestamp()
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "status": "CREATED",
        "created_at": timestamp,
        "updated_at": timestamp,
        "history": [
            {
                "from": None,
                "to": "CREATED",
                "at": timestamp,
                "note": "project created",
            }
        ],
    }
    write_state(directory, state)
    return state


def load_run_state(directory: Path, project_id: str) -> dict[str, Any]:
    directory = Path(directory)
    if directory.name != project_id or not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise StateError("project directory name must match its valid project ID")
    path = state_path(directory)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise StateError(f"run.json not found for project {project_id}") from error
    except json.JSONDecodeError as error:
        raise StateError(f"invalid run.json for project {project_id}: {error}") from error

    if not isinstance(state, dict):
        raise StateError("run.json must contain a JSON object")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise StateError(f"unsupported run.json schema version: {state.get('schema_version')}")
    if state.get("project_id") != project_id:
        raise StateError("run.json project_id does not match the project directory")
    if state.get("status") not in STAGES:
        raise StateError(f"unknown project status: {state.get('status')}")
    history = state.get("history")
    if (
        not isinstance(history, list)
        or not history
        or not isinstance(history[-1], dict)
        or history[-1].get("to") != state["status"]
    ):
        raise StateError("run.json history does not end at the current status")
    return state


def resume_plan(directory: Path, project_id: str) -> dict[str, Any]:
    """Return the first incomplete stage without mutating project state."""
    state = load_run_state(directory, project_id)
    status = state["status"]
    index = STAGES.index(status)

    if status == "PUBLISHED_MANUALLY":
        action = "complete"
        next_stage = None
    elif status == "READY_FOR_REVIEW":
        action = "await_human_review"
        next_stage = None
    else:
        action = "continue"
        next_stage = STAGES[index + 1]

    try:
        run_file = (directory / "run.json").relative_to(ROOT).as_posix()
    except ValueError:
        run_file = (directory / "run.json").as_posix()

    return {
        "project_id": project_id,
        "status": status,
        "completed_stages": list(STAGES[: index + 1]),
        "resume_stage": next_stage,
        "action": action,
        "run_file": run_file,
    }


def transition_project(
    directory: Path,
    project_id: str,
    target: str,
    note: str = "",
    record_manual_publication: bool = False,
) -> dict[str, Any]:
    if target not in STAGES:
        raise StateError(f"unknown target status: {target}")
    if target == "PUBLISHED_MANUALLY" and not record_manual_publication:
        raise StateError("PUBLISHED_MANUALLY requires explicit confirmation that the user published manually")
    if record_manual_publication and target != "PUBLISHED_MANUALLY":
        raise StateError("manual publication confirmation is valid only for PUBLISHED_MANUALLY")

    state = load_run_state(directory, project_id)
    current = state["status"]
    next_index = STAGES.index(current) + 1
    expected = STAGES[next_index] if next_index < len(STAGES) else None
    if target != expected:
        raise StateError(f"invalid transition {current} -> {target}; expected {expected or 'no further transition'}")

    timestamp = utc_timestamp()
    state["status"] = target
    state["updated_at"] = timestamp
    state["history"].append(
        {
            "from": current,
            "to": target,
            "at": timestamp,
            "note": note.strip(),
        }
    )
    write_state(directory, state)
    return state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR, help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Print the current run.json state")
    status_parser.add_argument("project_id")

    transition_parser = subparsers.add_parser("transition", help="Advance to the next lifecycle stage")
    transition_parser.add_argument("project_id")
    transition_parser.add_argument("--to", required=True, choices=STAGES)
    transition_parser.add_argument("--note", default="")
    transition_parser.add_argument(
        "--record-manual-publication",
        action="store_true",
        help="Record a user-confirmed manual publication after READY_FOR_REVIEW",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        directory = project_dir(args.project_id, args.projects_dir)
        if args.command == "status":
            state = load_run_state(directory, args.project_id)
        else:
            state = transition_project(
                directory,
                args.project_id,
                args.to,
                note=args.note,
                record_manual_publication=args.record_manual_publication,
            )
    except (OSError, StateError) as error:
        print(f"project_state: {error}", file=sys.stderr)
        return 1

    print(json.dumps(state, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
