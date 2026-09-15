"""ASR provider selection independent of video-use."""

from __future__ import annotations

from .base import ASRError


ASR_PROVIDER_PRIORITY = ("elevenlabs", "whisper_api", "local_whisper", "other")


def choose_asr_provider(available: dict[str, bool], preferred: str | None = None) -> str:
    if not isinstance(available, dict):
        raise ASRError("ASR provider availability must be a mapping")
    if preferred is not None:
        if preferred not in ASR_PROVIDER_PRIORITY:
            raise ASRError(f"unsupported ASR provider: {preferred}")
        if available.get(preferred) is True:
            return preferred
    for provider in ASR_PROVIDER_PRIORITY:
        if available.get(provider) is True:
            return provider
    raise ASRError("no configured ASR provider is available")
