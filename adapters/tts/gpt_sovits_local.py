"""Loopback GPT-SoVITS adapter with named local voice profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .base import SynthesisResult, TTSProvider, TTSProviderError, validate_synthesis_request


class GPTSoVITSLocalTTS(TTSProvider):
    """Use a user-managed GPT-SoVITS api_v2 service."""

    name = "gpt_sovits_local"

    def __init__(
        self,
        *,
        endpoint: str = "http://127.0.0.1:9880",
        voice_profiles: dict[str, dict[str, Any]] | None = None,
        timeout: float = 120.0,
        allow_remote: bool = False,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise TTSProviderError("GPT-SoVITS endpoint must be an http(s) URL")
        if not allow_remote and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise TTSProviderError("GPT-SoVITS endpoint must be loopback unless allow_remote=True")
        if timeout <= 0:
            raise TTSProviderError("GPT-SoVITS timeout must be positive")
        self.endpoint = endpoint.rstrip("/")
        self.voice_profiles = dict(voice_profiles or {})
        self.timeout = float(timeout)
        self._opener = opener

    def _profile(self, voice: str) -> dict[str, Any]:
        profile = self.voice_profiles.get(voice)
        if not isinstance(profile, dict):
            raise TTSProviderError(f"GPT-SoVITS voice profile is not configured: {voice}")
        reference = Path(str(profile.get("ref_audio_path") or "")).expanduser()
        if not reference.is_absolute() or not reference.is_file():
            raise TTSProviderError(f"GPT-SoVITS reference audio is missing for voice: {voice}")
        prompt_lang = str(profile.get("prompt_lang") or "zh").strip()
        text_lang = str(profile.get("text_lang") or "zh").strip()
        if not prompt_lang or not text_lang:
            raise TTSProviderError("GPT-SoVITS language fields must be non-empty")
        return {
            "ref_audio_path": str(reference),
            "prompt_text": str(profile.get("prompt_text") or "").strip(),
            "prompt_lang": prompt_lang,
            "text_lang": text_lang,
            "text_split_method": str(profile.get("text_split_method") or "cut5"),
        }

    def synthesize(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        emotion: str | None = None,
    ) -> SynthesisResult:
        text, voice, speed, emotion = validate_synthesis_request(text, voice, speed, emotion)
        profile = self._profile(voice)
        payload = {
            "text": text,
            "text_lang": profile["text_lang"],
            "ref_audio_path": profile["ref_audio_path"],
            "prompt_text": profile["prompt_text"],
            "prompt_lang": profile["prompt_lang"],
            "text_split_method": profile["text_split_method"],
            "batch_size": 1,
            "media_type": "wav",
            "streaming_mode": False,
            "speed_factor": speed,
            "parallel_infer": True,
        }
        request = Request(
            self.endpoint + "/tts",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "audio/wav"},
            method="POST",
        )
        try:
            response = self._opener(request, timeout=self.timeout)
            with response:
                audio = response.read()
                content_type = str(response.headers.get("Content-Type", "")).lower()
        except Exception as error:
            raise TTSProviderError(f"GPT-SoVITS request failed: {error}") from error
        if not audio:
            raise TTSProviderError("GPT-SoVITS returned empty audio")
        if content_type and "audio" not in content_type and "octet-stream" not in content_type:
            raise TTSProviderError(f"GPT-SoVITS returned unexpected content type: {content_type}")
        return SynthesisResult(
            audio=audio,
            provider=self.name,
            voice=voice,
            speed=speed,
            emotion=emotion,
            audio_format="wav",
            billable_generation=False,
        )
