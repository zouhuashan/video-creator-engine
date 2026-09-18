#!/usr/bin/env python3
"""Mux a local Rig video with its timeline audio; keep SRT as a sidecar asset."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def mux(video: Path, audio: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-i", str(audio),
        "-filter_complex", "[1:a]apad[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(output),
    ], check=True, capture_output=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("video", type=Path); parser.add_argument("audio", type=Path); parser.add_argument("output", type=Path); args = parser.parse_args(); print(mux(args.video, args.audio, args.output)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
