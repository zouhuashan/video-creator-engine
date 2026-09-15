import json
import unittest

from adapters.tts import FishAudioTTS, TTSProviderError, choose_provider


class FakeResponse:
    def __init__(self, body=b"mp3-audio"):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.body


class TTSProviderTests(unittest.TestCase):
    def test_fish_audio_implements_common_synthesize_contract(self):
        captured = {}

        def opener(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        result = FishAudioTTS(api_key="test-key", opener=opener).synthesize(
            "这是测试。", "voice-123", 1.1, "calm"
        )
        request = captured["request"]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(request.full_url, "https://api.fish.audio/v1/tts")
        self.assertEqual(request.headers["Model"], "s2-pro")
        self.assertEqual(payload["text"], "[calm] 这是测试。")
        self.assertEqual(payload["reference_id"], "voice-123")
        self.assertEqual(payload["prosody"]["speed"], 1.1)
        self.assertEqual(result.audio, b"mp3-audio")
        self.assertEqual(result.provider, "fish_audio")

    def test_fish_audio_requires_credentials_and_valid_request(self):
        with self.assertRaisesRegex(TTSProviderError, "API_KEY"):
            FishAudioTTS(api_key="").synthesize("测试", "voice-123")
        with self.assertRaisesRegex(TTSProviderError, "between"):
            FishAudioTTS(api_key="test").synthesize("测试", "voice-123", 3.0)
        with self.assertRaisesRegex(TTSProviderError, "brackets"):
            FishAudioTTS(api_key="test").synthesize("测试", "voice-123", emotion="[angry]")

    def test_provider_priority_prefers_fish_then_declared_fallbacks(self):
        self.assertEqual(choose_provider({"fish_audio": True, "edge_tts": True}), "fish_audio")
        self.assertEqual(choose_provider({"elevenlabs": True, "edge_tts": True}), "elevenlabs")
        self.assertEqual(choose_provider({"local": True}), "local")
        with self.assertRaisesRegex(TTSProviderError, "no configured"):
            choose_provider({"fish_audio": False})


if __name__ == "__main__":
    unittest.main()
