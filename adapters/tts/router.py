"""Deterministic TTS provider priority without hidden fallback billing."""

from __future__ import annotations

from .base import TTSProviderError


PRIMARY_PROVIDER = "fish_audio"
FALLBACK_PROVIDERS = ("elevenlabs", "edge_tts", "local")
PROVIDER_PRIORITY = (PRIMARY_PROVIDER, *FALLBACK_PROVIDERS)


def choose_provider(available: dict[str, bool]) -> str:
    if not isinstance(available, dict):
        raise TTSProviderError("provider availability must be a mapping")
    unknown = set(available) - set(PROVIDER_PRIORITY)
    if unknown:
        raise TTSProviderError(f"unsupported TTS provider: {sorted(unknown)[0]}")
    for provider in PROVIDER_PRIORITY:
        if available.get(provider) is True:
            return provider
    raise TTSProviderError("no configured TTS provider is available")
