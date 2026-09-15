"""Provider-neutral text-to-speech interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class TTSProviderError(RuntimeError):
    """Raised when a TTS request cannot be completed safely."""


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    provider: str
    voice: str
    speed: float
    emotion: str | None
    audio_format: str
    billable_generation: bool = True


def validate_synthesis_request(
    text: str, voice: str, speed: float, emotion: str | None
) -> tuple[str, str, float, str | None]:
    normalized_text = text.strip() if isinstance(text, str) else ""
    normalized_voice = voice.strip() if isinstance(voice, str) else ""
    normalized_emotion = emotion.strip() if isinstance(emotion, str) else None
    if not normalized_text:
        raise TTSProviderError("text must be a non-empty string")
    if not normalized_voice:
        raise TTSProviderError("voice must be a non-empty provider voice ID")
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not 0.5 <= speed <= 2.0:
        raise TTSProviderError("speed must be between 0.5 and 2.0")
    if normalized_emotion == "":
        normalized_emotion = None
    if normalized_emotion and any(character in normalized_emotion for character in "[]\n\r"):
        raise TTSProviderError("emotion must be plain text without brackets or line breaks")
    return normalized_text, normalized_voice, float(speed), normalized_emotion


class TTSProvider(ABC):
    name: str

    @abstractmethod
    def synthesize(
        self, text: str, voice: str, speed: float = 1.0, emotion: str | None = None
    ) -> SynthesisResult:
        """Synthesize one utterance using a provider-specific voice ID."""
