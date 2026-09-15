#!/usr/bin/env python3
"""Create and revise a traceable video-use edit-decision-list.json."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from adapters.video.video_use import VideoUseError, validate_edl
    from scripts.project_state import PROJECT_ID_PATTERN
except ImportError:
    import sys

    ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT_FOR_IMPORT))
    from adapters.video.video_use import VideoUseError, validate_edl
    from scripts.project_state import PROJECT_ID_PATTERN


FILENAME = "edit-decision-list.json"
HISTORY_DIRNAME = "edl-history"
DECISION_ID = re.compile(r"^EDL\d{3,}$")
EDITABLE_RANGE_FIELDS = {"source", "start", "end", "beat", "quote", "reason"}


class EDLError(ValueError):
    """Raised when an EDL operation would lose traceability."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(payload: dict[str, Any]) -> str:
    render_fields = {
        key: payload.get(key)
        for key in ("sources", "ranges", "grade", "overlays", "subtitles", "total_duration_s")
    }
    encoded = json.dumps(render_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _edl_path(edit_dir: Path) -> Path:
    edit_dir = Path(edit_dir).resolve()
    if edit_dir.name != "edit":
        raise EDLError("EDL must live in a directory named edit")
    return edit_dir / FILENAME


def _resolve_source(path: str, edit_dir: Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else (edit_dir / candidate).resolve()


def _validate_trace_fields(edl: dict[str, Any]) -> None:
    if edl.get("schema_version") != 1 or edl.get("version") != 1:
        raise EDLError("EDL schema and video-use version must both be 1")
    project_id = edl.get("project_id")
    if not isinstance(project_id, str) or not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise EDLError("EDL project_id is invalid")
    if not isinstance(edl.get("revision"), int) or edl["revision"] < 1:
        raise EDLError("EDL revision must be a positive integer")
    ranges = edl.get("ranges")
    if not isinstance(ranges, list) or not ranges:
        raise EDLError("EDL requires at least one range")
    ids: set[str] = set()
    for index, item in enumerate(ranges, start=1):
        decision_id = item.get("decision_id")
        if not isinstance(decision_id, str) or not DECISION_ID.fullmatch(decision_id):
            raise EDLError(f"range {index} has an invalid decision_id")
        if decision_id in ids:
            raise EDLError(f"duplicate decision_id: {decision_id}")
        ids.add(decision_id)
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise EDLError(f"{decision_id}: reason is required for traceability")
    checksums = edl.get("source_checksums")
    if not isinstance(checksums, dict) or set(checksums) != set(edl.get("sources", {})):
        raise EDLError("EDL source checksums must match every source")
    if edl.get("render_fingerprint") != _canonical_hash(edl):
        raise EDLError("EDL render fingerprint is invalid")


def _write_revision(edit_dir: Path, edl: dict[str, Any]) -> Path:
    _validate_trace_fields(edl)
    try:
        validate_edl(edl, edit_dir)
    except VideoUseError as error:
        raise EDLError(str(error)) from error
    current_path = _edl_path(edit_dir)
    history_path = edit_dir / HISTORY_DIRNAME / f"revision-{edl['revision']:04d}.json"
    if history_path.exists():
        raise EDLError(f"EDL history revision already exists: {edl['revision']}")
    _atomic_json(history_path, edl)
    _atomic_json(current_path, edl)
    return current_path


def create_edl(edit_dir: Path, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    edit_dir = Path(edit_dir).resolve()
    path = _edl_path(edit_dir)
    if path.exists():
        raise EDLError("edit-decision-list.json already exists; create a revision instead")
    if not isinstance(payload, dict):
        raise EDLError("EDL input must be an object")
    edl = copy.deepcopy(payload)
    edl["schema_version"] = 1
    edl["version"] = 1
    edl["project_id"] = project_id
    edl["revision"] = 1
    edl["parent_revision"] = None
    timestamp = _utc_now()
    edl["created_at"] = timestamp
    edl["updated_at"] = timestamp
    edl["change"] = {"kind": "create", "summary": "initial edit decisions"}
    ranges = edl.get("ranges")
    if isinstance(ranges, list):
        for index, item in enumerate(ranges, start=1):
            if isinstance(item, dict):
                item.setdefault("decision_id", f"EDL{index:03d}")
    sources = edl.get("sources")
    if not isinstance(sources, dict):
        raise EDLError("EDL sources must be an object")
    try:
        edl["source_checksums"] = {
            source_id: _sha256(_resolve_source(source_path, edit_dir))
            for source_id, source_path in sources.items()
        }
    except (OSError, TypeError) as error:
        raise EDLError("cannot checksum an EDL source") from error
    edl["total_duration_s"] = round(
        sum(float(item["end"]) - float(item["start"]) for item in edl.get("ranges", [])), 3
    )
    edl["render_fingerprint"] = _canonical_hash(edl)
    _write_revision(edit_dir, edl)
    return edl


def load_edl(edit_dir: Path, project_id: str) -> dict[str, Any]:
    path = _edl_path(edit_dir)
    try:
        edl = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EDLError(f"cannot read {FILENAME}: {error}") from error
    _validate_trace_fields(edl)
    if edl["project_id"] != project_id:
        raise EDLError("EDL project_id does not match")
    return edl


def verify_sources(edl: dict[str, Any], edit_dir: Path) -> None:
    for source_id, source_path in edl["sources"].items():
        path = _resolve_source(source_path, Path(edit_dir).resolve())
        try:
            actual = _sha256(path)
        except OSError as error:
            raise EDLError(f"EDL source is unavailable: {source_id}") from error
        if actual != edl["source_checksums"][source_id]:
            raise EDLError(f"EDL source changed since the decision was recorded: {source_id}")


def update_range(
    edit_dir: Path,
    project_id: str,
    decision_id: str,
    patch: dict[str, Any],
    *,
    expected_revision: int,
) -> dict[str, Any]:
    edit_dir = Path(edit_dir).resolve()
    current = load_edl(edit_dir, project_id)
    if current["revision"] != expected_revision:
        raise EDLError(f"stale EDL revision: expected {expected_revision}, found {current['revision']}")
    if not isinstance(patch, dict) or not patch or set(patch) - EDITABLE_RANGE_FIELDS:
        raise EDLError("range patch contains no fields or unsupported fields")
    revised = copy.deepcopy(current)
    target = next((item for item in revised["ranges"] if item["decision_id"] == decision_id), None)
    if target is None:
        raise EDLError(f"unknown decision_id: {decision_id}")
    target.update(patch)
    revised["parent_revision"] = current["revision"]
    revised["revision"] = current["revision"] + 1
    revised["updated_at"] = _utc_now()
    revised["change"] = {"kind": "update_range", "decision_id": decision_id}
    revised["total_duration_s"] = round(
        sum(float(item["end"]) - float(item["start"]) for item in revised["ranges"]), 3
    )
    revised["render_fingerprint"] = _canonical_hash(revised)
    _write_revision(edit_dir, revised)
    return revised


def rollback_edl(
    edit_dir: Path,
    project_id: str,
    target_revision: int,
    *,
    expected_revision: int,
) -> dict[str, Any]:
    edit_dir = Path(edit_dir).resolve()
    current = load_edl(edit_dir, project_id)
    if current["revision"] != expected_revision:
        raise EDLError(f"stale EDL revision: expected {expected_revision}, found {current['revision']}")
    history_path = edit_dir / HISTORY_DIRNAME / f"revision-{target_revision:04d}.json"
    try:
        target = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EDLError(f"cannot load EDL revision {target_revision}") from error
    _validate_trace_fields(target)
    if target["project_id"] != project_id:
        raise EDLError("rollback revision belongs to another project")
    restored = copy.deepcopy(target)
    restored["revision"] = current["revision"] + 1
    restored["parent_revision"] = current["revision"]
    restored["created_at"] = current["created_at"]
    restored["updated_at"] = _utc_now()
    restored["change"] = {"kind": "rollback", "target_revision": target_revision}
    restored["render_fingerprint"] = _canonical_hash(restored)
    _write_revision(edit_dir, restored)
    return restored


def prepare_rerender(edit_dir: Path, project_id: str) -> dict[str, Any]:
    edl = load_edl(edit_dir, project_id)
    verify_sources(edl, edit_dir)
    return {
        "status": "READY",
        "edl": str(_edl_path(edit_dir)),
        "revision": edl["revision"],
        "render_fingerprint": edl["render_fingerprint"],
        "output": str(Path(edit_dir).resolve() / "final.mp4"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("project_id")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--input-file", type=Path, required=True)
    update = subparsers.add_parser("update-range")
    update.add_argument("decision_id")
    update.add_argument("--patch-file", type=Path, required=True)
    update.add_argument("--expected-revision", type=int, required=True)
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("target_revision", type=int)
    rollback.add_argument("--expected-revision", type=int, required=True)
    subparsers.add_parser("rerender-plan")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "create":
            payload = json.loads(args.input_file.read_text(encoding="utf-8"))
            result = create_edl(args.edit_dir, args.project_id, payload)
        elif args.command == "update-range":
            patch = json.loads(args.patch_file.read_text(encoding="utf-8"))
            result = update_range(
                args.edit_dir,
                args.project_id,
                args.decision_id,
                patch,
                expected_revision=args.expected_revision,
            )
        elif args.command == "rollback":
            result = rollback_edl(
                args.edit_dir,
                args.project_id,
                args.target_revision,
                expected_revision=args.expected_revision,
            )
        else:
            result = prepare_rerender(args.edit_dir, args.project_id)
    except (OSError, ValueError, EDLError) as error:
        print(f"edit-decision-list: {error}")
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
