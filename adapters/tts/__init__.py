"""Text-to-speech provider contracts and adapters."""

from .base import SynthesisResult, TTSProvider, TTSProviderError, validate_synthesis_request
from .fish_audio import FishAudioTTS
from .router import FALLBACK_PROVIDERS, PRIMARY_PROVIDER, choose_provider

__all__ = [
    "FALLBACK_PROVIDERS",
    "PRIMARY_PROVIDER",
    "FishAudioTTS",
    "SynthesisResult",
    "TTSProvider",
    "TTSProviderError",
    "choose_provider",
    "validate_synthesis_request",
]
