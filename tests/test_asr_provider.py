import json
import tempfile
import unittest
from pathlib import Path

from adapters.asr import (
    ASRError,
    ElevenLabsASR,
    LocalWhisperASR,
    OtherASR,
    WhisperAPIASR,
    choose_asr_provider,
    transcribe_for_video_use,
)


def whisper_payload(path, language, num_speakers):
    return {
        "language": language or "zh",
        "text": "你好 AI",
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.0, "end": 0.4},
                    {"word": " AI", "start": 0.5, "end": 0.8},
                ]
            }
        ],
    }


class ASRProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.media = self.root / "source.mp4"
        self.media.write_bytes(b"private-media")
        self.edit_dir = self.root / "edit"

    def tearDown(self):
        self.temporary.cleanup()

    def test_all_provider_types_share_word_level_contract(self):
        providers = [
            ElevenLabsASR(whisper_payload),
            WhisperAPIASR(whisper_payload),
            LocalWhisperASR(whisper_payload),
            OtherASR("custom", whisper_payload),
        ]

        for provider in providers:
            result = provider.transcribe(
                self.media,
                language="zh",
                media_upload_authorized=provider.uploads_media,
            )
            self.assertEqual(result.payload["words"][0]["type"], "word")
            self.assertEqual(result.payload["provider"], provider.name)

    def test_router_honors_preference_then_falls_back(self):
        available = {"elevenlabs": True, "local_whisper": True}

        self.assertEqual(choose_asr_provider(available, "local_whisper"), "local_whisper")
        self.assertEqual(choose_asr_provider(available), "elevenlabs")

    def test_cloud_provider_requires_media_upload_authorization(self):
        provider = WhisperAPIASR(whisper_payload)

        with self.assertRaisesRegex(ASRError, "explicit authorization"):
            transcribe_for_video_use(provider, self.media, self.edit_dir)

    def test_bridge_writes_video_use_format_and_reuses_cache(self):
        calls = []

        def transcriber(path, language, num_speakers):
            calls.append(path)
            return whisper_payload(path, language, num_speakers)

        provider = LocalWhisperASR(transcriber)
        path, first = transcribe_for_video_use(provider, self.media, self.edit_dir, language="zh")
        same_path, second = transcribe_for_video_use(provider, self.media, self.edit_dir, language="zh")

        self.assertEqual(path, same_path)
        self.assertEqual(len(calls), 1)
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["words"][1]["text"], " AI")

    def test_bridge_retranscribes_when_source_or_provider_changes(self):
        calls = []

        def transcriber(path, language, num_speakers):
            calls.append(path.read_bytes())
            return whisper_payload(path, language, num_speakers)

        provider = LocalWhisperASR(transcriber)
        transcribe_for_video_use(provider, self.media, self.edit_dir)
        self.media.write_bytes(b"changed-media")
        transcribe_for_video_use(provider, self.media, self.edit_dir)

        self.assertEqual(len(calls), 2)

    def test_rejects_phrase_only_transcript(self):
        provider = LocalWhisperASR(lambda path, language, speakers: {"text": "no words"})

        with self.assertRaisesRegex(ASRError, "word-level"):
            provider.transcribe(self.media)


if __name__ == "__main__":
    unittest.main()
