"""Text-to-speech provider contracts and adapters."""

from .base import SynthesisResult, TTSProvider, TTSProviderError, validate_synthesis_request
from .cache import CachedTTS, VoiceCacheError, voice_cache_key
from .fish_audio import FishAudioTTS
from .router import FALLBACK_PROVIDERS, PRIMARY_PROVIDER, choose_provider

__all__ = [
    "FALLBACK_PROVIDERS",
    "PRIMARY_PROVIDER",
    "FishAudioTTS",
    "CachedTTS",
    "SynthesisResult",
    "TTSProvider",
    "TTSProviderError",
    "VoiceCacheError",
    "choose_provider",
    "validate_synthesis_request",
    "voice_cache_key",
]
