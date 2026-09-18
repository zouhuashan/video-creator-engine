"""VideoCreator Web bootstrap compatibility hooks.

Python may report an empty macOS version on some macOS 26 hosts.  pip,
packaging and truststore expect a numeric release string.  At interpreter
startup, fill the missing value from /usr/bin/sw_vers without changing the
reported architecture or touching system configuration.
"""

from __future__ import annotations

import platform
import subprocess

_ORIGINAL_MAC_VER = platform.mac_ver


def _sw_vers_product_version() -> str:
    try:
        completed = subprocess.run(
            ["/usr/bin/sw_vers", "-productVersion"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return completed.stdout.strip()


def _patched_mac_ver(
    release: str = "",
    versioninfo: tuple[str, str, str] = ("", "", ""),
    machine: str = "",
) -> tuple[str, tuple[str, str, str], str]:
    current = _ORIGINAL_MAC_VER(release, versioninfo, machine)
    if current[0]:
        return current

    product_version = _sw_vers_product_version()
    if not product_version:
        return current

    detected_machine = current[2] or platform.machine()
    return (product_version, current[1], detected_machine)


if not _ORIGINAL_MAC_VER()[0]:
    platform.mac_ver = _patched_mac_ver
