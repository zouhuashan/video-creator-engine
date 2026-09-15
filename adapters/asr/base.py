"""Provider-neutral ASR contract compatible with video-use word timestamps."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ASRError(RuntimeError):
    """Raised when transcription input or output violates the ASR contract."""


@dataclass(frozen=True)
class ASRTranscript:
    payload: dict[str, Any]
    provider: str
    cache_hit: bool = False


class ASRProvider(ABC):
    name: str
    uploads_media: bool

    @abstractmethod
    def transcribe(
        self,
        media_path: Path,
        *,
        language: str | None = None,
        num_speakers: int | None = None,
        media_upload_authorized: bool = False,
    ) -> ASRTranscript:
        """Return verbatim word-level timestamps in the common transcript format."""


def normalize_transcript(payload: dict[str, Any], provider: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ASRError(f"{provider}: transcript response must be an object")
    raw_words = payload.get("words")
    if not isinstance(raw_words, list):
        segments = payload.get("segments")
        if isinstance(segments, list):
            raw_words = [word for segment in segments for word in (segment.get("words") or [])]
    if not isinstance(raw_words, list) or not raw_words:
        raise ASRError(f"{provider}: word-level timestamps are required")

    words: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_words):
        if not isinstance(raw, dict):
            raise ASRError(f"{provider}: word {index} must be an object")
        text = raw.get("text", raw.get("word"))
        try:
            start = float(raw["start"])
            end = float(raw["end"])
        except (KeyError, TypeError, ValueError) as error:
            raise ASRError(f"{provider}: word {index} has invalid timing") from error
        if not isinstance(text, str) or not text or start < 0 or end < start:
            raise ASRError(f"{provider}: word {index} is invalid")
        word = {
            "text": text,
            "start": start,
            "end": end,
            "type": raw.get("type", "word"),
        }
        if raw.get("speaker_id") is not None:
            word["speaker_id"] = raw["speaker_id"]
        words.append(word)

    transcript_text = payload.get("text")
    if not isinstance(transcript_text, str) or not transcript_text.strip():
        transcript_text = "".join(word["text"] for word in words)
    language_code = payload.get("language_code", payload.get("language"))
    return {
        "language_code": language_code,
        "language_probability": payload.get("language_probability"),
        "text": transcript_text,
        "words": words,
        "provider": provider,
    }
