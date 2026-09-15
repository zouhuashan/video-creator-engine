"""Adapters for ElevenLabs, Whisper API/local, and custom ASR clients."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .base import ASRError, ASRProvider, ASRTranscript, normalize_transcript


Transcriber = Callable[[Path, str | None, int | None], dict[str, Any]]


class ClientASRProvider(ASRProvider):
    def __init__(self, name: str, transcriber: Transcriber, *, uploads_media: bool) -> None:
        if not callable(transcriber):
            raise ASRError(f"{name}: transcriber must be callable")
        self.name = name
        self.transcriber = transcriber
        self.uploads_media = uploads_media

    def transcribe(
        self,
        media_path: Path,
        *,
        language: str | None = None,
        num_speakers: int | None = None,
        media_upload_authorized: bool = False,
    ) -> ASRTranscript:
        path = Path(media_path).resolve()
        if not path.is_file():
            raise ASRError(f"{self.name}: media file does not exist: {path}")
        if self.uploads_media and not media_upload_authorized:
            raise ASRError(f"{self.name}: media upload requires explicit authorization")
        if num_speakers is not None and (not isinstance(num_speakers, int) or num_speakers < 1):
            raise ASRError(f"{self.name}: num_speakers must be a positive integer")
        try:
            payload = self.transcriber(path, language, num_speakers)
        except ASRError:
            raise
        except Exception as error:
            raise ASRError(f"{self.name}: transcription failed") from error
        return ASRTranscript(payload=normalize_transcript(payload, self.name), provider=self.name)


class ElevenLabsASR(ClientASRProvider):
    def __init__(self, transcriber: Transcriber) -> None:
        super().__init__("elevenlabs", transcriber, uploads_media=True)


class WhisperAPIASR(ClientASRProvider):
    def __init__(self, transcriber: Transcriber) -> None:
        super().__init__("whisper_api", transcriber, uploads_media=True)


class LocalWhisperASR(ClientASRProvider):
    def __init__(self, transcriber: Transcriber) -> None:
        super().__init__("local_whisper", transcriber, uploads_media=False)


class OtherASR(ClientASRProvider):
    def __init__(
        self, name: str, transcriber: Transcriber, *, uploads_media: bool = False
    ) -> None:
        if name in {"elevenlabs", "whisper_api", "local_whisper"} or not name.strip():
            raise ASRError("custom ASR provider requires a distinct non-empty name")
        super().__init__(name.strip(), transcriber, uploads_media=uploads_media)
