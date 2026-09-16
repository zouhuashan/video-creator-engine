#!/usr/bin/env python3
"""Execute a cover-only rerun for an unpublished pilot project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.package_project import REQUIRED_FILES, load_config as load_package_config
from scripts.project_state import DEFAULT_PROJECTS_DIR, load_run_state, utc_timestamp


class PilotCoverRerunError(ValueError):
    """Raised when a cover-only rerun cannot preserve package integrity."""


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PilotCoverRerunError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise PilotCoverRerunError(f"{label} must be a JSON object")
    return value


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stage_file(destination: Path, data: bytes) -> Path:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return Path(temporary)


def rerun_cover(project_dir: Path, project_id: str, candidate_id: str) -> dict[str, Any]:
    directory = Path(project_dir).resolve()
    if directory.name != project_id:
        raise PilotCoverRerunError("project directory must match project_id")
    state = load_run_state(directory, project_id)
    if state["status"] != "READY_FOR_REVIEW":
        raise PilotCoverRerunError("cover rerun requires an unpublished READY_FOR_REVIEW project")

    cover_manifest_path = directory / "cover-candidates.json"
    cover_manifest = _load(cover_manifest_path, "cover-candidates.json")
    if cover_manifest.get("project_id") != project_id or not isinstance(cover_manifest.get("candidates"), list):
        raise PilotCoverRerunError("cover candidate manifest does not match this project")
    previous_id = cover_manifest.get("selected")
    if candidate_id == previous_id:
        raise PilotCoverRerunError("cover rerun must select a different candidate")
    candidate = next((item for item in cover_manifest["candidates"]
                      if isinstance(item, dict) and item.get("candidate_id") == candidate_id), None)
    if candidate is None:
        raise PilotCoverRerunError(f"unknown cover candidate: {candidate_id}")
    filename = candidate.get("file")
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise PilotCoverRerunError("cover candidate filename must be a plain filename")
    source = directory / "covers" / filename
    if source.is_symlink() or not source.is_file():
        raise PilotCoverRerunError("selected cover candidate is missing or unsafe")
    new_data = source.read_bytes()
    new_sha = _sha_bytes(new_data)
    if new_sha != candidate.get("sha256"):
        raise PilotCoverRerunError("selected cover candidate checksum does not match its manifest")

    package_config = load_package_config()
    package_dir = directory / package_config["package_directory"]
    root_cover = directory / "cover.png"
    package_cover = package_dir / "cover.png"
    if any(path.is_symlink() or not path.is_file() for path in (root_cover, package_cover)):
        raise PilotCoverRerunError("project and package covers must both exist as regular files")
    old_data = root_cover.read_bytes()
    old_sha = _sha_bytes(old_data)
    if _sha_bytes(package_cover.read_bytes()) != old_sha or cover_manifest.get("selected_sha256") != old_sha:
        raise PilotCoverRerunError("current cover and package checksums are inconsistent")

    package_manifest_path = directory / "package.json"
    package = _load(package_manifest_path, "package.json")
    files = package.get("files")
    names = {item.get("name") for item in files if isinstance(item, dict)} if isinstance(files, list) else set()
    if names != REQUIRED_FILES or package.get("project_id") != project_id or package.get("auto_publish") is not False:
        raise PilotCoverRerunError("existing publish package is incomplete or has unsafe publication settings")
    cover_entries = [item for item in files if item.get("name") == "cover.png"]
    if len(cover_entries) != 1 or cover_entries[0].get("sha256") != old_sha:
        raise PilotCoverRerunError("package manifest does not match the current cover")
    updated_package = json.loads(json.dumps(package))
    cover_entry = next(item for item in updated_package["files"] if item["name"] == "cover.png")
    cover_entry.update({"size_bytes": len(new_data), "sha256": new_sha})
    updated_package["updated_at"] = utc_timestamp()

    cover_manifest["selected"] = candidate_id
    cover_manifest["selected_sha256"] = new_sha
    ledger_path = directory / "cover-rerun.json"
    if ledger_path.exists():
        ledger = _load(ledger_path, "cover-rerun.json")
        if ledger.get("schema_version") != 1 or ledger.get("project_id") != project_id or not isinstance(ledger.get("runs"), list):
            raise PilotCoverRerunError("existing cover rerun ledger is invalid")
    else:
        ledger = {"schema_version": 1, "project_id": project_id, "runs": []}
    preserved = []
    for item in files:
        if item["name"] not in {"cover.png"}:
            path = package_dir / item["name"]
            if not path.is_file() or _sha_bytes(path.read_bytes()) != item.get("sha256"):
                raise PilotCoverRerunError(f"cannot preserve invalid package file: {item['name']}")
            preserved.append(item["name"])
    ledger["runs"].append({"at": utc_timestamp(), "from_candidate": previous_id, "to_candidate": candidate_id,
                           "reason": "intentional alternate-cover test for the P14 partial-rerun gate; no defect was detected",
                           "old_sha256": old_sha, "new_sha256": new_sha, "preserved_package_files": sorted(preserved),
                           "video_regenerated": False, "project_state_changed": False})

    replacements = {
        root_cover: new_data,
        package_cover: new_data,
        cover_manifest_path: (json.dumps(cover_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        package_manifest_path: (json.dumps(updated_package, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        ledger_path: (json.dumps(ledger, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    }
    staged: dict[Path, Path] = {}
    backups: dict[Path, bytes | None] = {}
    try:
        for destination, data in replacements.items():
            if destination.exists():
                backups[destination] = destination.read_bytes()
            else:
                backups[destination] = None
            staged[destination] = _stage_file(destination, data)
        for destination, temporary in staged.items():
            os.replace(temporary, destination)
    except Exception:
        for destination, previous in backups.items():
            try:
                if previous is None:
                    destination.unlink(missing_ok=True)
                else:
                    rollback = _stage_file(destination, previous)
                    os.replace(rollback, destination)
            except OSError:
                pass
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)

    return {"status": "PASS", "project_id": project_id, "selected": candidate_id,
            "old_sha256": old_sha, "new_sha256": new_sha,
            "preserved_package_files": sorted(preserved), "video_regenerated": False,
            "project_state": state["status"], "ledger": str(ledger_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_id")
    parser.add_argument("candidate_id")
    parser.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    args = parser.parse_args()
    try:
        result = rerun_cover(args.projects_dir / args.project_id, args.project_id, args.candidate_id)
    except (OSError, ValueError) as error:
        print(f"pilot_cover_rerun: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
