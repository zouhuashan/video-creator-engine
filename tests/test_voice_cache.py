import json
import tempfile
import unittest
from pathlib import Path

from adapters.tts import CachedTTS, SynthesisResult, TTSProvider, VoiceCacheError, voice_cache_key


class CountingProvider(TTSProvider):
    name = "fish_audio"

    def __init__(self):
        self.calls = 0

    def synthesize(self, text, voice, speed=1.0, emotion=None):
        self.calls += 1
        return SynthesisResult(
            audio=f"audio-{self.calls}".encode(),
            provider=self.name,
            voice=voice,
            speed=float(speed),
            emotion=emotion,
            audio_format="mp3",
        )


class VoiceCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temporary.name)
        self.provider = CountingProvider()
        self.cached = CachedTTS(self.provider, self.cache_dir)

    def tearDown(self):
        self.temporary.cleanup()

    def test_same_identity_hits_cache_without_second_generation(self):
        first = self.cached.synthesize("相同文本", "voice-a", 1.0, "calm")
        second = self.cached.synthesize("相同文本", "voice-a", 1, "calm")

        self.assertEqual(self.provider.calls, 1)
        self.assertTrue(first.billable_generation)
        self.assertFalse(second.billable_generation)
        self.assertEqual(first.audio, second.audio)

    def test_required_identity_fields_change_cache_key(self):
        baseline = voice_cache_key("文本", "voice-a", 1.0, "fish_audio")
        variants = {
            voice_cache_key("另一段", "voice-a", 1.0, "fish_audio"),
            voice_cache_key("文本", "voice-b", 1.0, "fish_audio"),
            voice_cache_key("文本", "voice-a", 1.1, "fish_audio"),
            voice_cache_key("文本", "voice-a", 1.0, "local"),
        }

        self.assertNotIn(baseline, variants)
        self.assertEqual(len(variants), 4)

    def test_emotion_is_sound_affecting_cache_variant(self):
        calm = self.cached.synthesize("文本", "voice-a", emotion="calm")
        excited = self.cached.synthesize("文本", "voice-a", emotion="excited")

        self.assertEqual(self.provider.calls, 2)
        self.assertNotEqual(calm.audio, excited.audio)

    def test_corrupt_cache_fails_without_rebilling(self):
        self.cached.synthesize("文本", "voice-a")
        metadata_path = next(self.cache_dir.glob("*.json"))
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        (self.cache_dir / f"{metadata['key']}.mp3").write_bytes(b"corrupt")

        with self.assertRaisesRegex(VoiceCacheError, "checksum"):
            self.cached.synthesize("文本", "voice-a")
        self.assertEqual(self.provider.calls, 1)


if __name__ == "__main__":
    unittest.main()
