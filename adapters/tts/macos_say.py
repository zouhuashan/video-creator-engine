"""Local, non-billable macOS speech synthesis adapter."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .base import SynthesisResult, TTSProvider, TTSProviderError, validate_synthesis_request


class MacOSSayTTS(TTSProvider):
    name = "macos_say"

    def __init__(
        self,
        *,
        executable: str = "/usr/bin/say",
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ) -> None:
        self.executable = executable
        self.runner = runner

    def synthesize(
        self, text: str, voice: str, speed: float = 1.0, emotion: str | None = None
    ) -> SynthesisResult:
        text, voice, speed, emotion = validate_synthesis_request(text, voice, speed, emotion)
        if emotion is not None:
            raise TTSProviderError("macOS local TTS does not support emotion controls")
        rate = round(175 * speed)
        with tempfile.TemporaryDirectory(prefix="video-creator-say-") as temporary:
            output = Path(temporary) / "voice.aiff"
            try:
                completed = self.runner(
                    [self.executable, "-v", voice, "-r", str(rate), "-o", str(output), "--", text],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except OSError as error:
                raise TTSProviderError("macOS say executable is unavailable") from error
            if completed.returncode != 0:
                raise TTSProviderError("macOS local TTS synthesis failed")
            try:
                audio = output.read_bytes()
            except OSError as error:
                raise TTSProviderError("macOS local TTS produced no readable audio") from error
        if not audio:
            raise TTSProviderError("macOS local TTS returned empty audio")
        return SynthesisResult(
            audio=audio,
            provider=self.name,
            voice=voice,
            speed=speed,
            emotion=None,
            audio_format="aiff",
            billable_generation=False,
        )
