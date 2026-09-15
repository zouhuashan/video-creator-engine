"""Fish Audio S2-Pro TTS adapter."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .base import SynthesisResult, TTSProvider, TTSProviderError, validate_synthesis_request


FISH_AUDIO_TTS_URL = "https://api.fish.audio/v1/tts"


class FishAudioTTS(TTSProvider):
    name = "fish_audio"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._opener = opener
        self._timeout_seconds = timeout_seconds

    def _credential(self) -> str:
        credential = self._api_key or os.environ.get("FISH_AUDIO_API_KEY", "")
        if not credential:
            raise TTSProviderError("Fish Audio is selected but FISH_AUDIO_API_KEY is not configured")
        return credential

    @staticmethod
    def _apply_emotion(text: str, emotion: str | None) -> str:
        return f"[{emotion}] {text}" if emotion else text

    def synthesize(
        self, text: str, voice: str, speed: float = 1.0, emotion: str | None = None
    ) -> SynthesisResult:
        text, voice, speed, emotion = validate_synthesis_request(text, voice, speed, emotion)
        payload = {
            "text": self._apply_emotion(text, emotion),
            "reference_id": voice,
            "prosody": {"speed": speed, "volume": 0, "normalize_loudness": True},
            "normalize": True,
            "format": "mp3",
            "sample_rate": 44100,
            "mp3_bitrate": 128,
            "latency": "normal",
        }
        request = urllib.request.Request(
            FISH_AUDIO_TTS_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._credential()}",
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
                "model": "s2-pro",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                audio = response.read()
        except (OSError, urllib.error.HTTPError, urllib.error.URLError) as error:
            status = getattr(error, "code", "unavailable")
            raise TTSProviderError(f"Fish Audio synthesis failed with status {status}") from error
        if not audio:
            raise TTSProviderError("Fish Audio returned an empty audio response")
        return SynthesisResult(
            audio=audio,
            provider=self.name,
            voice=voice,
            speed=speed,
            emotion=emotion,
            audio_format="mp3",
        )
