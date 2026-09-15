#!/usr/bin/env python3
"""Build an integrity-checked WeChat Channels publishing package."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

try:
    from .project_state import StateError, load_run_state, transition_project, utc_timestamp
except ImportError:
    from project_state import StateError, load_run_state, transition_project, utc_timestamp

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "packaging.json"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
REQUIRED_FILES = {"final.mp4", "cover.png", "title.md", "caption.md", "hashtags.md", "sources.md", "qc-report.md"}


class PackagingError(ValueError):
    """Raised when required artifacts cannot form a valid package."""


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PackagingError(f"invalid packaging config: {error}") from error
    if config.get("schema_version") != 1 or set(config.get("required_files", [])) != REQUIRED_FILES:
        raise PackagingError("unsupported or incomplete packaging config")
    package_directory = config.get("package_directory")
    if not isinstance(package_directory, str) or Path(package_directory).name != package_directory:
        raise PackagingError("package directory must be one local directory name")
    if config.get("auto_publish") is not False or config.get("publish_mode") != "human_confirmation":
        raise PackagingError("packaging must require human publication confirmation")
    return config


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_source(directory: Path, filename: str) -> Path:
    path = directory / filename
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise PackagingError(f"required package file is missing, empty, or a symlink: {filename}")
    if filename == "cover.png" and path.read_bytes()[:8] != PNG_SIGNATURE:
        raise PackagingError("cover.png is not a valid PNG file")
    if filename.endswith(".md"):
        try:
            if not path.read_text(encoding="utf-8").strip():
                raise PackagingError(f"required Markdown file is blank: {filename}")
        except UnicodeDecodeError as error:
            raise PackagingError(f"required Markdown file is not UTF-8: {filename}") from error
    return path


def _validate_qc(directory: Path) -> None:
    try:
        report = json.loads((directory / "qc.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PackagingError(f"valid qc.json is required before packaging: {error}") from error
    if report.get("status") != "PASS" or report.get("failed_reports"):
        raise PackagingError("publishing package requires a PASS QC report")


def package_project(directory: Path, project_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    directory = Path(directory).resolve()
    state = load_run_state(directory, project_id)
    if state["status"] != "QC_PASS":
        raise StateError(f"packaging requires status QC_PASS; current status is {state['status']}")
    active = config or load_config()
    _validate_qc(directory)
    package_dir = directory / active["package_directory"]
    manifest_path = directory / "package.json"
    if package_dir.exists() or manifest_path.exists():
        raise PackagingError("refusing to overwrite an existing publishing package")
    sources = [(filename, _validate_source(directory, filename)) for filename in active["required_files"]]
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{active['package_directory']}.", dir=directory))
    try:
        files = []
        for filename, source in sources:
            destination = temp_dir / filename
            shutil.copy2(source, destination)
            source_hash, copied_hash = _sha256(source), _sha256(destination)
            if copied_hash != source_hash:
                raise PackagingError(f"checksum mismatch while packaging {filename}")
            files.append({"name": filename, "size_bytes": destination.stat().st_size, "sha256": copied_hash})
        manifest = {
            "schema_version": 1, "project_id": project_id, "platform": active["platform"],
            "created_at": utc_timestamp(), "publish_mode": active["publish_mode"],
            "auto_publish": False, "directory": active["package_directory"], "files": files,
        }
        (temp_dir / "package.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_dir, package_dir)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        if package_dir.exists() and not manifest_path.exists():
            shutil.rmtree(package_dir)
        raise
    new_state = transition_project(directory, project_id, "PACKAGED", note="publishing package checksums verified")
    return {"project_id": project_id, "status": "PASS", "state": new_state["status"],
            "package_directory": str(package_dir), "files": files,
            "outputs": [active["package_directory"], "package.json"]}
