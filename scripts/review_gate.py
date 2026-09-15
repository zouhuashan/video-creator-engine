#!/usr/bin/env python3
"""Verify a publishing package and enter the human review gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from .package_project import REQUIRED_FILES, load_config
    from .project_state import StateError, load_run_state, transition_project, utc_timestamp
except ImportError:
    from package_project import REQUIRED_FILES, load_config
    from project_state import StateError, load_run_state, transition_project, utc_timestamp


class ReviewGateError(ValueError):
    """Raised when a package cannot safely enter human review."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewGateError(f"invalid {label}: {error}") from error
    if not isinstance(payload, dict):
        raise ReviewGateError(f"{label} must be a JSON object")
    return payload


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def verify_review_package(directory: Path, project_id: str) -> dict[str, Any]:
    directory = Path(directory).resolve()
    state = load_run_state(directory, project_id)
    if state["status"] != "PACKAGED":
        raise StateError(f"review gate requires status PACKAGED; current status is {state['status']}")
    config = load_config()
    manifest = _load_json(directory / "package.json", "package.json")
    if (
        manifest.get("schema_version") != 1 or manifest.get("project_id") != project_id
        or manifest.get("publish_mode") != "human_confirmation" or manifest.get("auto_publish") is not False
        or manifest.get("directory") != config["package_directory"] or manifest.get("platform") != config["platform"]
    ):
        raise ReviewGateError("package manifest does not preserve the human publication boundary")
    entries = manifest.get("files")
    if (
        not isinstance(entries, list) or len(entries) != len(REQUIRED_FILES)
        or {entry.get("name") for entry in entries if isinstance(entry, dict)} != REQUIRED_FILES
    ):
        raise ReviewGateError("package manifest does not contain exactly the seven required deliverables")
    package_dir = directory / config["package_directory"]
    checked = []
    for entry in entries:
        if set(entry) != {"name", "size_bytes", "sha256"}:
            raise ReviewGateError("package manifest contains an invalid file entry")
        path = package_dir / entry["name"]
        if path.is_symlink() or not path.is_file():
            raise ReviewGateError(f"package file is missing or a symlink: {entry['name']}")
        actual_size, actual_hash = path.stat().st_size, _sha256(path)
        if actual_size != entry["size_bytes"] or actual_hash != entry["sha256"]:
            raise ReviewGateError(f"package file changed after packaging: {entry['name']}")
        checked.append({"name": entry["name"], "size_bytes": actual_size, "sha256": actual_hash})
    qc = _load_json(directory / "qc.json", "qc.json")
    if qc.get("status") != "PASS" or qc.get("failed_reports"):
        raise ReviewGateError("human review requires aggregate QC PASS")
    return {"schema_version": 1, "project_id": project_id, "status": "PASS", "verified_at": utc_timestamp(),
            "package_directory": config["package_directory"], "files": checked, "qc_status": "PASS",
            "publish_mode": "human_confirmation", "next_action": "WAITING_FOR_HUMAN_PUBLISH"}


def terminal_summary() -> str:
    return "\n".join([
        "FINAL READY", "", "✓ final.mp4", "✓ cover.png", "✓ title", "✓ caption",
        "✓ hashtags", "✓ sources", "✓ QC PASS", "", "WAITING FOR HUMAN PUBLISH",
    ])


def enter_review_gate(directory: Path, project_id: str) -> dict[str, Any]:
    directory = Path(directory).resolve()
    output = directory / "review-gate.json"
    if output.exists():
        raise ReviewGateError("refusing to overwrite an existing review gate record")
    report = verify_review_package(directory, project_id)
    _write_atomic(output, report)
    try:
        state = transition_project(directory, project_id, "READY_FOR_REVIEW", note="publishing package verified; waiting for human publication")
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return {**report, "state": state["status"], "output": "review-gate.json", "terminal_summary": terminal_summary()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("project_id")
    args = parser.parse_args()
    try:
        result = enter_review_gate(args.project_dir, args.project_id)
    except (ReviewGateError, StateError) as error:
        print(f"review_gate: {error}", file=sys.stderr)
        return 1
    print(result["terminal_summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
