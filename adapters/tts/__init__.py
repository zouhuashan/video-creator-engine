"""Text-to-speech provider contracts and adapters."""

from .base import SynthesisResult, TTSProvider, TTSProviderError, validate_synthesis_request
from .cache import CachedTTS, VoiceCacheError, voice_cache_key
from .fish_audio import FishAudioTTS
from .kokoro_sherpa import (
    KOKORO_VOICE_TO_SID,
    KokoroSherpaTTS,
    normalize_chinese_punctuation,
    resolve_kokoro_voice,
)
from .macos_say import MacOSSayTTS
from .router import FALLBACK_PROVIDERS, PRIMARY_PROVIDER, choose_provider
from .zh_speech import ChineseSpeechError, SpeechPlan, optimize_chinese_speech

__all__ = [
    "FALLBACK_PROVIDERS",
    "PRIMARY_PROVIDER",
    "FishAudioTTS",
    "KOKORO_VOICE_TO_SID",
    "KokoroSherpaTTS",
    "MacOSSayTTS",
    "CachedTTS",
    "ChineseSpeechError",
    "SynthesisResult",
    "SpeechPlan",
    "TTSProvider",
    "TTSProviderError",
    "VoiceCacheError",
    "choose_provider",
    "optimize_chinese_speech",
    "normalize_chinese_punctuation",
    "resolve_kokoro_voice",
    "validate_synthesis_request",
    "voice_cache_key",
]
