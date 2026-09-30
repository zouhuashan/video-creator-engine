from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from adapters.tts.base import TTSProviderError
from adapters.tts.gpt_sovits_local import GPTSoVITSLocalTTS, load_voice_profiles


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


class GPTSoVITSLocalTests(unittest.TestCase):
    def test_posts_named_local_profile_and_is_non_billable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ref = root / "voice.wav"
            ref.write_bytes(b"RIFFref")
            captured = {}

            def opener(request, timeout):
                captured["url"] = request.full_url
                captured["payload"] = json.loads(request.data.decode("utf-8"))
                return _Response()

            provider = GPTSoVITSLocalTTS(
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
            result = provider.synthesize("今天开始。", "hero", speed=1.1)

        self.assertEqual(result.provider, "gpt_sovits_local")
        self.assertFalse(result.billable_generation)
        self.assertTrue(result.audio.startswith(b"RIFF"))
        self.assertEqual(captured["url"], "http://127.0.0.1:9880/tts")
        self.assertEqual(captured["payload"]["speed_factor"], 1.1)

    def test_rejects_remote_endpoint_by_default(self):
        with self.assertRaises(TTSProviderError):
            GPTSoVITSLocalTTS(endpoint="https://example.com:9880")

    def test_requires_existing_reference_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.wav"
            provider = GPTSoVITSLocalTTS(
                voice_profiles={"hero": {"ref_audio_path": str(missing.resolve())}}
            )
            with self.assertRaises(TTSProviderError):
                provider.synthesize("hello", "hero")

    def test_load_voice_profiles_requires_registry_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voices.json"
            path.write_text('{"schema_version":1,"voices":{"hero":{"ref_audio_path":"/tmp/a.wav"}}}', encoding="utf-8")
            self.assertIn("hero", load_voice_profiles(path))
            path.write_text('{"schema_version":2,"voices":{}}', encoding="utf-8")
            with self.assertRaises(TTSProviderError):
                load_voice_profiles(path)


if __name__ == "__main__":
    unittest.main()
