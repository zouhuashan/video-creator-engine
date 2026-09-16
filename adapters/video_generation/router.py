"""Deterministic video-generation provider selection."""

from __future__ import annotations

from .base import VideoGenerationError

VIDEO_GENERATION_PROVIDER_PRIORITY = ("local_ken_burns", "runway")


def choose_video_generation_provider(available: dict[str, bool], preferred: str | None = None) -> str:
    if not isinstance(available, dict):
        raise VideoGenerationError("video-generation provider availability must be a mapping")
    unknown = set(available) - set(VIDEO_GENERATION_PROVIDER_PRIORITY)
    if unknown:
        raise VideoGenerationError(f"unsupported video-generation provider: {sorted(unknown)[0]}")
    if preferred is not None:
        if preferred not in VIDEO_GENERATION_PROVIDER_PRIORITY:
            raise VideoGenerationError(f"unsupported video-generation provider: {preferred}")
        if available.get(preferred) is True:
            return preferred
    for provider in VIDEO_GENERATION_PROVIDER_PRIORITY:
        if available.get(provider) is True:
            return provider
    raise VideoGenerationError("no configured video-generation provider is available")
