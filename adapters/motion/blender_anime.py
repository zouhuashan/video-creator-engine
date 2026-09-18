"""Local Blender Anime renderer adapter boundary."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

MINIMUM_VERSION = (5, 2, 0)
MAXIMUM_EXCLUSIVE = (5, 3, 0)
DEFAULT_CANDIDATES = (
    "/opt/homebrew/bin/blender",
    "/Applications/Blender.app/Contents/MacOS/Blender",
    "blender",
)
_PRERELEASE_MARKERS = ("alpha", "beta", "rc", "daily")


class BlenderAnimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class BlenderVersion:
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


def parse_version(raw: str) -> BlenderVersion:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?", raw or "")
    if not match:
        raise BlenderAnimeError(f"cannot parse Blender version: {raw!r}")
    return BlenderVersion(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
        (raw or "").strip(),
    )


def _resolve(candidate: str) -> str | None:
    if "/" in candidate:
        path = Path(candidate).expanduser()
        return str(path) if path.is_file() and path.stat().st_mode & 0o111 else None
    return shutil.which(candidate)


def discover_binary(candidates: Iterable[str] = DEFAULT_CANDIDATES) -> str:
    for candidate in candidates:
        resolved = _resolve(candidate)
        if resolved:
            return resolved
    raise BlenderAnimeError("Blender binary not found")


def inspect_environment(binary: str | None = None) -> dict[str, object]:
    binary = binary or discover_binary()
    try:
        completed = subprocess.run(
            ["/usr/bin/arch", "-arm64", binary, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise BlenderAnimeError(f"Blender version probe failed: {error}") from error
    first_line = (completed.stdout or completed.stderr).splitlines()[0]
    version = parse_version(first_line)
    supported = (
        version.stable
        and version.tuple >= MINIMUM_VERSION
        and version.tuple < MAXIMUM_EXCLUSIVE
    )
    return {
        "binary": binary,
        "version": version.raw,
        "version_tuple": list(version.tuple),
        "stable": version.stable,
        "minimum_version": list(MINIMUM_VERSION),
        "maximum_exclusive": list(MAXIMUM_EXCLUSIVE),
        "supported": supported,
        "architecture": "arm64",
        "channel": "5.2 LTS",
    }


def smoke_command(script: Path, output: Path, binary: str | None = None) -> list[str]:
    script = Path(script).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if not script.is_file():
        raise BlenderAnimeError(f"missing Blender smoke script: {script}")
    binary = binary or discover_binary()
    return [
        "/usr/bin/arch",
        "-arm64",
        binary,
        "--background",
        "--factory-startup",
        "--python",
        str(script),
        "--",
        "--output",
        str(output),
    ]
