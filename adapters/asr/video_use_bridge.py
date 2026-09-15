"""Write any ASR provider result into video-use's transcript boundary."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .base import ASRError, ASRProvider, ASRTranscript, normalize_transcript


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def transcribe_for_video_use(
    provider: ASRProvider,
    media_path: Path,
    edit_dir: Path,
    *,
    language: str | None = None,
    num_speakers: int | None = None,
    media_upload_authorized: bool = False,
) -> tuple[Path, ASRTranscript]:
    media_path = Path(media_path).resolve()
    edit_dir = Path(edit_dir).resolve()
    if not media_path.is_file():
        raise ASRError(f"media file does not exist: {media_path}")
    if edit_dir.name != "edit":
        raise ASRError("video-use transcripts must be written under an edit directory")
    if provider.uploads_media and not media_upload_authorized:
        raise ASRError(f"{provider.name}: media upload requires explicit authorization")

    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = transcripts_dir / f"{media_path.stem}.json"
    # Keep cache metadata out of video-use's transcripts/*.json scan.
    metadata_path = transcripts_dir / f"{media_path.stem}.meta"
    source_hash = _source_sha256(media_path)
    identity = {
        "schema_version": 1,
        "source_sha256": source_hash,
        "provider": provider.name,
        "language": language,
        "num_speakers": num_speakers,
    }
    if transcript_path.exists() or metadata_path.exists():
        if not transcript_path.exists() or not metadata_path.exists():
            raise ASRError("transcript cache is incomplete; refusing an implicit paid retry")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            cached_payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ASRError("transcript cache is invalid; refusing an implicit paid retry") from error
        if metadata == identity:
            normalized = normalize_transcript(cached_payload, provider.name)
            return transcript_path, ASRTranscript(normalized, provider.name, cache_hit=True)

    transcript = provider.transcribe(
        media_path,
        language=language,
        num_speakers=num_speakers,
        media_upload_authorized=media_upload_authorized,
    )
    _atomic_json(transcript_path, transcript.payload)
    _atomic_json(metadata_path, identity)
    return transcript_path, transcript
