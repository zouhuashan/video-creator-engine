#!/usr/bin/env python3
"""Install the small CC0 MakeHuman asset subset used by the P47-08 pilot.

The official pack is about 268 MiB.  This installer reads its ZIP central
directory with HTTP range requests and downloads only the approved character
files, keeping the pilot reproducible without caching the complete pack.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import re
import struct
import urllib.request
import zlib
from pathlib import Path, PurePosixPath


PACK_URL = "https://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip"
LICENSE_URL = "https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html"
PREFIXES = (
    "clothes/male_casualsuit01/",
    "clothes/shoes01/",
    "hair/short01/",
    "hair/short02/",
    "hair/short03/",
    "hair/short04/",
    "eyes/high-poly/",
    "eyes/materials/brown.",
    "eyes/materials/brown_",
    "skins/young_asian_male/",
)


def _request(byte_range: str) -> tuple[bytes, str]:
    request = urllib.request.Request(
        PACK_URL,
        headers={"Range": byte_range, "User-Agent": "VideoCreator-P47-08/1.0"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read(), str(response.headers.get("Content-Range") or "")


def _central_directory() -> list[dict[str, object]]:
    tail, content_range = _request("bytes=-2097152")
    match = re.search(r"bytes\s+(\d+)-(\d+)/(\d+)", content_range)
    if not match:
        raise RuntimeError("official asset server did not honor the ZIP tail range")
    tail_start = int(match.group(1))
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise RuntimeError("official asset ZIP end record is missing")
    values = struct.unpack_from("<4s4H2LH", tail, eocd)
    entry_count, central_size, central_offset = values[4], values[5], values[6]
    local_offset = central_offset - tail_start
    if local_offset < 0 or local_offset + central_size > len(tail):
        raise RuntimeError("ZIP central directory does not fit in audit range")
    entries = []
    cursor = local_offset
    for _ in range(entry_count):
        values = struct.unpack_from("<4s6H3L5H2L", tail, cursor)
        if values[0] != b"PK\x01\x02":
            raise RuntimeError("invalid ZIP central directory entry")
        filename_length, extra_length, comment_length = values[10], values[11], values[12]
        name = tail[cursor + 46 : cursor + 46 + filename_length].decode("utf-8")
        entries.append({
            "name": name,
            "method": values[4],
            "crc32": values[7],
            "compressed_size": values[8],
            "size": values[9],
            "local_offset": values[16],
        })
        cursor += 46 + filename_length + extra_length + comment_length
    return entries


def _extract(entry: dict[str, object]) -> bytes:
    start = int(entry["local_offset"])
    compressed_size = int(entry["compressed_size"])
    # Read enough for the local header, name, extra fields and compressed data.
    block, _ = _request(f"bytes={start}-{start + compressed_size + 8191}")
    if block[:4] != b"PK\x03\x04":
        raise RuntimeError(f"invalid local ZIP entry: {entry['name']}")
    local = struct.unpack_from("<4s5H3L2H", block, 0)
    name_length, extra_length = local[9], local[10]
    data_start = 30 + name_length + extra_length
    compressed = block[data_start : data_start + compressed_size]
    if len(compressed) != compressed_size:
        raise RuntimeError(f"truncated asset entry: {entry['name']}")
    method = int(entry["method"])
    if method == 0:
        payload = compressed
    elif method == 8:
        payload = zlib.decompress(compressed, -15)
    else:
        raise RuntimeError(f"unsupported ZIP method {method}: {entry['name']}")
    if len(payload) != int(entry["size"]):
        raise RuntimeError(f"asset size mismatch: {entry['name']}")
    if binascii.crc32(payload) & 0xFFFFFFFF != int(entry["crc32"]):
        raise RuntimeError(f"asset CRC mismatch: {entry['name']}")
    return payload


def install(destination: Path) -> dict[str, object]:
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    selected = [entry for entry in _central_directory() if not str(entry["name"]).endswith("/") and str(entry["name"]).startswith(PREFIXES)]
    if not selected:
        raise RuntimeError("official asset subset was not found")
    files = []
    for entry in selected:
        relative = PurePosixPath(str(entry["name"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("unsafe asset path")
        output = destination.joinpath(*relative.parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.is_file() and output.stat().st_size == int(entry["size"]):
            payload = output.read_bytes()
            if binascii.crc32(payload) & 0xFFFFFFFF != int(entry["crc32"]):
                payload = _extract(entry)
                output.write_bytes(payload)
        else:
            payload = _extract(entry)
            output.write_bytes(payload)
        files.append({
            "path": relative.as_posix(),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
        print(f"installed {relative} ({len(payload)} bytes)", flush=True)
    manifest = {
        "schema_version": 1,
        "provider": "makehuman_system_assets",
        "source_pack": PACK_URL,
        "source_catalog": LICENSE_URL,
        "license": "CC0-1.0",
        "selection": list(PREFIXES),
        "files": files,
    }
    (destination / "asset-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = install(args.destination)
    print(json.dumps({"status": "PASS", "files": len(result["files"]), "license": result["license"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
