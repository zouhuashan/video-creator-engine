"""Content-addressed voice cache with a per-key billing lock."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .base import SynthesisResult, TTSProvider, TTSProviderError, validate_synthesis_request


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = ROOT / "cache" / "voice"
FORMAT_PATTERN = re.compile(r"^[a-z0-9]{2,8}$")


class VoiceCacheError(TTSProviderError):
    """Raised when an existing cache entry cannot be trusted."""


def cache_identity(
    text: str,
    voice: str,
    speed: float,
    provider: str,
    emotion: str | None = None,
) -> dict[str, Any]:
    text, voice, speed, emotion = validate_synthesis_request(text, voice, speed, emotion)
    if not isinstance(provider, str) or not provider.strip():
        raise VoiceCacheError("provider must be a non-empty string")
    return {
        "text": text,
        "voice": voice,
        "speed": speed,
        "provider": provider.strip(),
        "emotion": emotion,
    }


def voice_cache_key(
    text: str,
    voice: str,
    speed: float,
    provider: str,
    emotion: str | None = None,
) -> str:
    identity = cache_identity(text, voice, speed, provider, emotion)
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@contextmanager
def _key_lock(cache_dir: Path, key: str) -> Iterator[None]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cache_dir / f"{key}.lock"
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _atomic_write(path: Path, data: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


class CachedTTS(TTSProvider):
    """Wrap a provider and synthesize at most once per cache identity."""

    def __init__(self, provider: TTSProvider, cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
        self.provider = provider
        self.name = provider.name
        self.cache_dir = Path(cache_dir)

    def _read(self, key: str, identity: dict[str, Any]) -> SynthesisResult | None:
        metadata_path = self.cache_dir / f"{key}.json"
        if not metadata_path.exists():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise VoiceCacheError(f"voice cache metadata is invalid for key {key}") from error
        expected = {
            "schema_version": 1,
            "key": key,
            "text_sha256": hashlib.sha256(identity["text"].encode("utf-8")).hexdigest(),
            "voice": identity["voice"],
            "speed": identity["speed"],
            "provider": identity["provider"],
            "emotion": identity["emotion"],
        }
        if any(metadata.get(field) != value for field, value in expected.items()):
            raise VoiceCacheError(f"voice cache identity mismatch for key {key}")
        audio_format = metadata.get("audio_format")
        if not isinstance(audio_format, str) or not FORMAT_PATTERN.fullmatch(audio_format):
            raise VoiceCacheError(f"voice cache format is invalid for key {key}")
        audio_path = self.cache_dir / f"{key}.{audio_format}"
        try:
            audio = audio_path.read_bytes()
        except OSError as error:
            raise VoiceCacheError(f"voice cache audio is missing for key {key}") from error
        if not audio or hashlib.sha256(audio).hexdigest() != metadata.get("audio_sha256"):
            raise VoiceCacheError(f"voice cache checksum mismatch for key {key}")
        return SynthesisResult(
            audio=audio,
            provider=identity["provider"],
            voice=identity["voice"],
            speed=identity["speed"],
            emotion=identity["emotion"],
            audio_format=audio_format,
            billable_generation=False,
        )

    def _write(self, key: str, identity: dict[str, Any], result: SynthesisResult) -> None:
        if result.provider != self.name or not result.audio:
            raise VoiceCacheError("provider returned an invalid synthesis result")
        if not FORMAT_PATTERN.fullmatch(result.audio_format):
            raise VoiceCacheError("provider returned an unsafe audio format")
        audio_path = self.cache_dir / f"{key}.{result.audio_format}"
        metadata_path = self.cache_dir / f"{key}.json"
        metadata = {
            "schema_version": 1,
            "key": key,
            "text_sha256": hashlib.sha256(identity["text"].encode("utf-8")).hexdigest(),
            "voice": identity["voice"],
            "speed": identity["speed"],
            "provider": identity["provider"],
            "emotion": identity["emotion"],
            "audio_format": result.audio_format,
            "audio_sha256": hashlib.sha256(result.audio).hexdigest(),
        }
        _atomic_write(audio_path, result.audio)
        _atomic_write(
            metadata_path,
            (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )

    def synthesize(
        self, text: str, voice: str, speed: float = 1.0, emotion: str | None = None
    ) -> SynthesisResult:
        identity = cache_identity(text, voice, speed, self.name, emotion)
        key = voice_cache_key(text, voice, speed, self.name, emotion)
        with _key_lock(self.cache_dir, key):
            cached = self._read(key, identity)
            if cached is not None:
                return cached
            result = self.provider.synthesize(text, voice, speed, emotion)
            self._write(key, identity, result)
            return result
