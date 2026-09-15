"""Replaceable speech-to-text provider boundary."""

from .base import ASRError, ASRProvider, ASRTranscript, normalize_transcript
from .providers import ElevenLabsASR, LocalWhisperASR, OtherASR, WhisperAPIASR
from .router import ASR_PROVIDER_PRIORITY, choose_asr_provider
from .video_use_bridge import transcribe_for_video_use

__all__ = [
    "ASRError",
    "ASRProvider",
    "ASRTranscript",
    "ASR_PROVIDER_PRIORITY",
    "ElevenLabsASR",
    "LocalWhisperASR",
    "OtherASR",
    "WhisperAPIASR",
    "choose_asr_provider",
    "normalize_transcript",
    "transcribe_for_video_use",
]
