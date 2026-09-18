"""Local Godot cutout adapter boundary.

This module performs environment discovery, stable-version checks and builds
safe smoke-test commands. It does not upload media, publish content or mutate
project state.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

MINIMUM_GODOT_VERSION = (4, 7, 2)
DEFAULT_CANDIDATES = (
    "/opt/homebrew/bin/godot",
    "/Applications/Godot.app/Contents/MacOS/Godot",
    "godot",
)
_PRERELEASE_MARKERS = ("dev", "alpha", "beta", "rc")


class GodotCutoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class GodotVersion:
    major: int
    minor: int
    patch: int
    raw: str

    @property
    def tuple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    @property
    def stable(self) -> bool:
        lowered = self.raw.lower()
        return not any(marker in lowered for marker in _PRERELEASE_MARKERS)


def parse_version(raw: str) -> GodotVersion:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?", raw or "")
    if not match:
        raise GodotCutoutError(f"cannot parse Godot version: {raw!r}")
    return GodotVersion(
        major=int(match.group(1)),
        minor=int(match.group(2)),
        patch=int(match.group(3) or 0),
        raw=(raw or "").strip(),
    )


def _resolve_candidate(candidate: str) -> str | None:
    if "/" in candidate:
        path = Path(candidate).expanduser()
        return str(path) if path.is_file() and path.stat().st_mode & 0o111 else None
    return shutil.which(candidate)


def discover_binary(candidates: Iterable[str] = DEFAULT_CANDIDATES) -> str:
    for candidate in candidates:
        resolved = _resolve_candidate(candidate)
        if resolved:
            return resolved
    raise GodotCutoutError("Godot binary not found")


def inspect_environment(binary: str | None = None) -> dict[str, object]:
    binary = binary or discover_binary()
    try:
        completed = subprocess.run(
            [binary, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise GodotCutoutError(f"Godot version probe failed: {error}") from error

    version = parse_version((completed.stdout or completed.stderr).strip())
    return {
        "binary": binary,
        "version": version.raw,
        "version_tuple": list(version.tuple),
        "stable": version.stable,
        "minimum_version": list(MINIMUM_GODOT_VERSION),
        "supported": version.stable and version.tuple >= MINIMUM_GODOT_VERSION,
    }


def smoke_command(project_dir: Path, binary: str | None = None) -> list[str]:
    project_dir = Path(project_dir).expanduser().resolve()
    if not (project_dir / "project.godot").is_file():
        raise GodotCutoutError(f"missing project.godot: {project_dir}")
    binary = binary or discover_binary()
    return [
        binary,
        "--headless",
        "--path",
        str(project_dir),
        "--scene",
        "res://main.tscn",
        "--quit-after",
        "10",
    ]


def run_smoke(project_dir: Path, binary: str | None = None) -> dict[str, object]:
    env = inspect_environment(binary)
    if not env["supported"]:
        raise GodotCutoutError(
            f"Godot must be stable and >= {'.'.join(map(str, MINIMUM_GODOT_VERSION))}: {env['version']}"
        )
    try:
        completed = subprocess.run(
            smoke_command(project_dir, str(env["binary"])),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise GodotCutoutError(f"Godot smoke test failed: {error}") from error

    output = (completed.stdout or "") + (completed.stderr or "")
    if "VIDEO_CREATOR_GODOT_SMOKE_PASS" not in output:
        raise GodotCutoutError("Godot smoke marker was not emitted")
    return {**env, "smoke": "PASS"}
