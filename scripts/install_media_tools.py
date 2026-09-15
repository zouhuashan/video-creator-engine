#!/usr/bin/env python3
"""Install pinned project-local media tools with archive verification."""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "media-tool-manifest.json"


class MediaToolError(RuntimeError):
    pass


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MediaToolError(f"cannot read media tool manifest: {error}") from error
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("tools"), list):
        raise MediaToolError("unsupported media tool manifest")
    return manifest


def _tool(name: str) -> dict[str, Any]:
    matches = [item for item in load_manifest()["tools"] if item.get("name") == name]
    if len(matches) != 1:
        raise MediaToolError(f"media tool is not declared exactly once: {name}")
    return matches[0]


def verify(name: str) -> str:
    tool = _tool(name)
    path = (ROOT / tool["install_path"]).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise MediaToolError(f"{name} is not installed at {tool['install_path']}")
    try:
        version = subprocess.run(
            [str(path), "-version"], check=True, capture_output=True, text=True
        ).stdout.splitlines()[0]
    except (OSError, subprocess.CalledProcessError, IndexError) as error:
        raise MediaToolError(f"cannot execute installed {name}") from error
    if f"version {tool['version']}" not in version:
        raise MediaToolError(f"{name} version mismatch: {version}")
    return version


def install(name: str) -> str:
    tool = _tool(name)
    expected_platform = f"{platform.system().lower()}-{platform.machine().lower()}"
    if expected_platform not in tool["platforms"]:
        raise MediaToolError(
            f"{name} archive does not support current platform {expected_platform}"
        )
    target = (ROOT / tool["install_path"]).resolve()
    if target.exists():
        return verify(name)
    try:
        with urllib.request.urlopen(tool["source"], timeout=180) as response:
            archive = response.read()
    except OSError as error:
        raise MediaToolError(f"cannot download pinned {name} archive") from error
    actual_hash = hashlib.sha256(archive).hexdigest()
    if actual_hash != tool["archive_sha256"]:
        raise MediaToolError(f"{name} archive checksum mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            if package.namelist() != [name]:
                raise MediaToolError(f"{name} archive contains unexpected files")
            binary = package.read(name)
    except zipfile.BadZipFile as error:
        raise MediaToolError(f"{name} archive is invalid") from error
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(binary)
        os.chmod(temporary_name, 0o755)
        os.replace(temporary_name, target)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return verify(name)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "verify"))
    parser.add_argument("name", choices=("ffprobe",))
    args = parser.parse_args()
    try:
        result = install(args.name) if args.action == "install" else verify(args.name)
    except MediaToolError as error:
        print(f"FAIL: {error}")
        return 1
    print(f"{args.name} {result} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
