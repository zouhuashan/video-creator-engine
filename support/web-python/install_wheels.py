#!/usr/bin/env python3
"""Install already-downloaded wheel files without invoking pip's install path."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath


class WheelInstallError(RuntimeError):
    pass


def _mapped_path(member: str) -> PurePosixPath | None:
    path = PurePosixPath(member)
    parts = path.parts
    if not parts:
        return None

    for index, part in enumerate(parts):
        if part.endswith(".data") and index + 1 < len(parts):
            category = parts[index + 1]
            suffix = PurePosixPath(*parts[index + 2 :])
            if category in {"purelib", "platlib", "data"}:
                return suffix
            if category in {"scripts", "headers"}:
                return None
    return path


def _safe_destination(target: Path, relative: PurePosixPath) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise WheelInstallError(f"unsafe wheel member: {relative}")
    destination = (target / Path(*relative.parts)).resolve()
    root = target.resolve()
    if destination != root and root not in destination.parents:
        raise WheelInstallError(f"wheel member escapes target: {relative}")
    return destination


def install_wheel(wheel: Path, target: Path) -> int:
    installed = 0
    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            mapped = _mapped_path(info.filename)
            if mapped is None or str(mapped) in {"", "."}:
                continue
            destination = _safe_destination(target, mapped)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)

            mode = (info.external_attr >> 16) & 0o777
            if mode:
                os.chmod(destination, mode)
            installed += 1
    return installed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-dir", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()

    wheel_dir = args.wheel_dir.expanduser().resolve()
    target = args.target.expanduser().resolve()
    wheels = sorted(wheel_dir.glob("*.whl"))
    if not wheels:
        raise WheelInstallError(f"no wheels found in {wheel_dir}")

    target.mkdir(parents=True, exist_ok=True)
    installed_files = 0
    for wheel in wheels:
        installed_files += install_wheel(wheel, target)
        print(f"INSTALLED {wheel.name}")

    if installed_files <= 0:
        raise WheelInstallError("wheel extraction produced no files")

    print(f"PASS {len(wheels)} wheel(s), {installed_files} file(s)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WheelInstallError as error:
        print(f"FAIL {error}")
        raise SystemExit(1)
