import json
from pathlib import Path

import pytest

from adapters.tts.gpt_sovits_local import GPTSoVITSLocalTTS
from adapters.tts.base import TTSProviderError


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _Response:
    def __init__(self, body=b"RIFFfake", content_type="audio/wav"):
        self.body = body
        self.headers = _Headers({"Content-Type": content_type})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def test_gpt_sovits_local_posts_named_profile(tmp_path: Path):
    ref = tmp_path / "voice.wav"
    ref.write_bytes(b"RIFFref")
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response()

    tts = GPTSoVITSLocalTTS(
        voice_profiles={
            "hero": {
                "ref_audio_path": str(ref.resolve()),
                "prompt_text": "你好。",
                "prompt_lang": "zh",
                "text_lang": "zh",
            }
        },
        opener=opener,
    )
    result = tts.synthesize("今天开始。", "hero", speed=1.1)
    assert result.provider == "gpt_sovits_local"
    assert result.billable_generation is False
    assert result.audio.startswith(b"RIFF")
    assert captured["url"] == "http://127.0.0.1:9880/tts"
    assert captured["payload"]["ref_audio_path"] == str(ref.resolve())
    assert captured["payload"]["speed_factor"] == 1.1


def test_gpt_sovits_local_rejects_remote_endpoint():
    with pytest.raises(TTSProviderError):
        GPTSoVITSLocalTTS(endpoint="https://example.com:9880")


def test_gpt_sovits_local_requires_existing_reference(tmp_path: Path):
    tts = GPTSoVITSLocalTTS(
        voice_profiles={"hero": {"ref_audio_path": str((tmp_path / "missing.wav").resolve())}}
    )
    with pytest.raises(TTSProviderError):
        tts.synthesize("hello", "hero")
