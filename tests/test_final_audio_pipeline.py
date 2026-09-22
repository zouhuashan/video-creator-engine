import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.final_audio_pipeline as final_audio


class FakeSynthesis:
    audio = b"fake-mp3"
    provider = "fish_audio"
    voice = "voice-001"
    speed = 1.0
    emotion = "calm"
    audio_format = "mp3"
    billable_generation = True


class FakeFish:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def synthesize(self, text, voice, speed=1.0, emotion=None):
        result = FakeSynthesis()
        result.voice = voice
        result.speed = speed
        result.emotion = emotion
        return result


class FinalAudioPipelineTests(unittest.TestCase):
    def voice_profiles(self):
        return {
            "profiles": [{
                "id": "VOICE-CHR-001-01",
                "character_id": "CHR-001",
                "speed": 1.0,
            }],
            "line_assignments": [],
        }

    def bible(self):
        return {"characters": [{"id": "CHR-001", "name": "云澈"}]}

    def write_ready_timeline(self, project: Path):
        path = project / final_audio.TIMELINE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "episodes": [{
                "episode_id": "S01E001",
                "status": "READY",
                "duration_seconds": 4.0,
                "lines": [
                    {
                        "unit_id": "UNIT-001",
                        "kind": "NARRATION",
                        "speaker_character_id": None,
                        "text": "夜色渐沉。",
                        "emotion": "",
                        "start_seconds": 0.0,
                        "end_seconds": 1.5,
                        "duration_seconds": 1.5,
                    },
                    {
                        "unit_id": "UNIT-002",
                        "kind": "DIALOGUE",
                        "speaker_character_id": "CHR-001",
                        "text": "这里就是沈府？",
                        "emotion": "calm",
                        "start_seconds": 1.5,
                        "end_seconds": 4.0,
                        "duration_seconds": 2.5,
                    },
                ],
            }],
        }), encoding="utf-8")

    def test_voice_lock_persists_narrator_and_character_without_touching_old_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with patch.object(final_audio, "load_voice_profiles", return_value=self.voice_profiles()), \
                 patch.object(final_audio, "load_bible", return_value=self.bible()):
                locks = final_audio.save_voice_lock(
                    project,
                    character_id="CHR-001",
                    voice_id="fish-char-1",
                    speed=0.95,
                    emotion_default="calm",
                )
                locks = final_audio.save_voice_lock(
                    project,
                    character_id="NARRATOR",
                    voice_id="fish-narrator-1",
                    speed=1.0,
                    emotion_default="calm",
                )

            self.assertEqual(locks["characters"][0]["voice_id"], "fish-char-1")
            self.assertEqual(locks["characters"][0]["status"], "LOCKED")
            self.assertEqual(locks["narrator"]["voice_id"], "fish-narrator-1")
            self.assertTrue((project / final_audio.LOCKS_PATH).is_file())

    def test_final_voice_requires_billable_and_text_upload_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_ready_timeline(project)
            with patch.object(final_audio, "load_voice_profiles", return_value=self.voice_profiles()), \
                 patch.object(final_audio, "load_bible", return_value=self.bible()):
                with self.assertRaisesRegex(final_audio.FinalAudioError, "付费确认"):
                    final_audio.generate_final_voice_line(
                        project, "S01E001", "UNIT-001",
                        api_key="fish-key-123",
                        confirm_billable=False,
                        text_upload_authorized=True,
                    )
                with self.assertRaisesRegex(final_audio.FinalAudioError, "允许"):
                    final_audio.generate_final_voice_line(
                        project, "S01E001", "UNIT-001",
                        api_key="fish-key-123",
                        confirm_billable=True,
                        text_upload_authorized=False,
                    )

    def test_final_voice_is_conformed_to_locked_p33_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_ready_timeline(project)
            with patch.object(final_audio, "load_voice_profiles", return_value=self.voice_profiles()), \
                 patch.object(final_audio, "load_bible", return_value=self.bible()):
                final_audio.save_voice_lock(project, character_id="NARRATOR", voice_id="fish-narrator-1")
                final_audio.save_voice_lock(project, character_id="CHR-001", voice_id="fish-char-1")

                def fake_conform(source, output, target_seconds):
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(b"RIFF")
                    return {
                        "source_duration_seconds": 2.2,
                        "target_duration_seconds": target_seconds,
                        "speed_ratio": 1.46667,
                        "output_duration_seconds": target_seconds,
                    }

                with patch.object(final_audio, "FishAudioTTS", FakeFish), \
                     patch.object(final_audio, "_conform_audio", side_effect=fake_conform):
                    item = final_audio.generate_final_voice_line(
                        project, "S01E001", "UNIT-001",
                        api_key="fish-key-123",
                        confirm_billable=True,
                        text_upload_authorized=True,
                    )

            self.assertEqual(item["status"], "READY")
            self.assertEqual(item["target_duration_seconds"], 1.5)
            self.assertEqual(item["output_duration_seconds"], 1.5)
            self.assertEqual(item["voice_id"], "fish-narrator-1")
            self.assertEqual(item["provider"], "fish_audio")

    def test_mix_graph_ducks_bgm_and_applies_loudness_target(self):
        lines = [
            {"start_seconds": 0.0},
            {"start_seconds": 1.5},
        ]
        graph, label = final_audio._voice_mix_graph(lines, ["bgm", "ambience", "sfx"], 4.0)
        self.assertEqual(label, "[mix]")
        self.assertIn("sidechaincompress", graph)
        self.assertIn("threshold=0.035", graph)
        self.assertIn("ratio=10", graph)
        self.assertIn("loudnorm=I=-16:TP=-1:LRA=11", graph)
        self.assertIn("adelay=1500|1500", graph)

    def test_audio_asset_upload_accepts_real_wav_header_and_rejects_html(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            wav = b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 24
            uploaded = final_audio.upload_audio_asset(
                project,
                kind="bgm",
                filename="theme.wav",
                content=wav,
            )
            self.assertEqual(uploaded["kind"], "bgm")
            self.assertTrue((project / uploaded["path"]).is_file())
            with self.assertRaisesRegex(final_audio.FinalAudioError, "文件头"):
                final_audio.upload_audio_asset(
                    project,
                    kind="sfx",
                    filename="fake.mp3",
                    content=b"<html>not audio</html>",
                )

    def test_inventory_reports_audio_candidates_and_process_only_key_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "audio" / "bgm").mkdir(parents=True)
            (project / "audio" / "bgm" / "theme.mp3").write_bytes(b"x")
            with patch.object(final_audio, "load_voice_profiles", return_value=self.voice_profiles()), \
                 patch.object(final_audio, "load_bible", return_value=self.bible()):
                result = final_audio.inventory(project)
            self.assertEqual(result["provider"]["key_persistence"], "PROCESS_ONLY")
            self.assertEqual(result["audio_candidates"]["bgm"], ["audio/bgm/theme.mp3"])
            self.assertEqual(result["mix_profile"]["target_lufs"], -16.0)


if __name__ == "__main__":
    unittest.main()
