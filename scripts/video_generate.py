#!/usr/bin/env python3
"""Generate a motion video from image keyframes through the selected provider."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.video_generation import (
    LocalKenBurnsVideo,
    OpenAISoraVideo,
    RunwayImageToVideo,
    VideoGenerationError,
    VideoGenerationRequest,
    WanImageToVideo,
    normalize_image_paths,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path, help="ordered image keyframes")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--shot-duration", type=float, default=3.0)
    parser.add_argument("--transition", type=float, default=0.4)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--provider", choices=("local_ken_burns", "openai_sora", "runway", "wan"), default="local_ken_burns")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--model", default="gen4.5", help="provider model (OpenAI maps the legacy default to sora-2)")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    request = VideoGenerationRequest(
        image_paths=normalize_image_paths(args.images),
        output_path=args.output,
        shot_duration_seconds=args.shot_duration,
        transition_seconds=args.transition,
        fps=args.fps,
        width=args.width,
        height=args.height,
        prompt_text=args.prompt,
        model=args.model,
    )
    providers = {
        "local_ken_burns": LocalKenBurnsVideo,
        "openai_sora": OpenAISoraVideo,
        "runway": RunwayImageToVideo,
        "wan": WanImageToVideo,
    }
    provider = providers[args.provider]()
    try:
        result = provider.generate(request)
    except VideoGenerationError as error:
        print(f"FAIL: provider={args.provider} error={error}", file=sys.stderr)
        return 1
    print(f"PASS: provider={result.provider} images={result.image_count} duration={result.duration_seconds:.2f}s")
    print(f"OUTPUT: {result.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
