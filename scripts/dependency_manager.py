#!/usr/bin/env python3
"""Install and verify Git dependencies pinned by dependency-manifest.json."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "dependency-manifest.json"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_FIELDS = {"name", "source", "commit", "install_path", "update_policy"}


class DependencyError(RuntimeError):
    """Raised when a dependency declaration or checkout is invalid."""


def _run(*command: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd or ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DependencyError(f"cannot read dependency manifest: {error}") from error

    if manifest.get("schema_version") != 1:
        raise DependencyError("dependency manifest schema_version must be 1")
    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise DependencyError("dependency manifest must declare at least one dependency")

    names: set[str] = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict) or not REQUIRED_FIELDS.issubset(dependency):
            raise DependencyError("dependency entry is missing required fields")
        name = dependency["name"]
        if not isinstance(name, str) or not name or name in names:
            raise DependencyError("dependency names must be unique non-empty strings")
        names.add(name)
        if not COMMIT_PATTERN.fullmatch(str(dependency["commit"])):
            raise DependencyError(f"{name}: commit must be a full 40-character SHA")
        tag = dependency.get("tag")
        ref = dependency.get("ref")
        if bool(tag) == bool(ref):
            raise DependencyError(f"{name}: declare exactly one tag or ref")
        if tag is not None and not isinstance(tag, str):
            raise DependencyError(f"{name}: tag must be a string")
        if ref is not None and not isinstance(ref, str):
            raise DependencyError(f"{name}: ref must be a string")
        if dependency["update_policy"] != "manual":
            raise DependencyError(f"{name}: update_policy must be manual")
        _install_path(dependency)
    return manifest


def _install_path(dependency: dict[str, Any]) -> Path:
    relative = Path(str(dependency["install_path"]))
    target = (ROOT / relative).resolve()
    dependency_root = (ROOT / ".dependencies").resolve()
    if relative.is_absolute() or target == dependency_root or dependency_root not in target.parents:
        raise DependencyError(f"{dependency.get('name', 'dependency')}: install_path must be inside .dependencies/")
    return target


def select_dependencies(manifest: dict[str, Any], name: str | None) -> list[dict[str, Any]]:
    dependencies = manifest["dependencies"]
    if name is None:
        return dependencies
    selected = [dependency for dependency in dependencies if dependency["name"] == name]
    if not selected:
        raise DependencyError(f"dependency is not declared: {name}")
    return selected


def verify_dependency(dependency: dict[str, Any]) -> str:
    target = _install_path(dependency)
    if not (target / ".git").exists():
        raise DependencyError(f"{dependency['name']}: not installed at {target.relative_to(ROOT)}")
    actual_commit = _run("git", "rev-parse", "HEAD", cwd=target)
    if actual_commit != dependency["commit"]:
        raise DependencyError(
            f"{dependency['name']}: expected {dependency['commit']}, found {actual_commit}"
        )
    actual_source = _run("git", "remote", "get-url", "origin", cwd=target)
    if actual_source != dependency["source"]:
        raise DependencyError(
            f"{dependency['name']}: expected source {dependency['source']}, found {actual_source}"
        )
    return actual_commit


def install_dependency(dependency: dict[str, Any]) -> str:
    target = _install_path(dependency)
    if target.exists():
        return verify_dependency(dependency)

    target.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["GIT_LFS_SKIP_SMUDGE"] = "1"
    try:
        target.mkdir()
        _run("git", "init", "--quiet", cwd=target, env=environment)
        _run("git", "remote", "add", "origin", dependency["source"], cwd=target, env=environment)
        _run(
            "git", "fetch", "--quiet", "--depth", "1", "origin", dependency["commit"],
            cwd=target, env=environment,
        )
        _run(
            "git",
            "-c",
            "filter.lfs.smudge=",
            "-c",
            "filter.lfs.required=false",
            "checkout",
            "--quiet",
            "--detach",
            dependency["commit"],
            cwd=target,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise DependencyError(f"{dependency['name']}: installation failed: {error}") from error
    return verify_dependency(dependency)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "verify"))
    parser.add_argument("name", nargs="?", help="dependency name; defaults to all")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = load_manifest()
        dependencies = select_dependencies(manifest, args.name)
        for dependency in dependencies:
            commit = (
                install_dependency(dependency)
                if args.action == "install"
                else verify_dependency(dependency)
            )
            selector = dependency.get("tag") or dependency.get("ref")
            print(f"{dependency['name']} {selector} {commit} PASS")
    except DependencyError as error:
        print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
