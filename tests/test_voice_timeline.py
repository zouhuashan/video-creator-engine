import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.voice_timeline as voice_timeline


class VoiceTimelineTests(unittest.TestCase):
    def fixtures(self):
        voices = {
            "line_assignments": [
                {
                    "unit_id": "UNIT-001",
                    "episode_id": "S01E001",
                    "kind": "NARRATION",
                    "speaker_character_id": None,
                    "profile_id": None,
                    "text": "夜色渐沉。",
                    "emotion": "",
                },
                {
                    "unit_id": "UNIT-002",
                    "episode_id": "S01E001",
                    "kind": "DIALOGUE",
                    "speaker_character_id": "CHR-001",
                    "profile_id": "VOICE-CHR-001-01",
                    "text": "这里就是沈府？",
                    "emotion": "克制",
                },
            ]
        }
        scripts = {
            "episode_scripts": [
                {
                    "episode_id": "S01E001",
                    "scenes": [
                        {
                            "id": "SC-S01E001-001",
                            "units": [
                                {"id": "UNIT-001", "estimated_duration_seconds": 1.2},
                                {"id": "UNIT-002", "estimated_duration_seconds": 2.0},
                            ],
                        }
                    ],
                }
            ]
        }
        shots = {
            "scene_breakdowns": [
                {
                    "scene_id": "SC-S01E001-001",
                    "shots": [{"id": "SHOT-S01E001-SC001-001"}],
                }
            ]
        }
        return voices, scripts, shots

    def test_build_timeline_uses_script_text_without_asr_and_recommends_shot_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            voices, scripts, shots = self.fixtures()
            with patch.object(voice_timeline, "load_voice_profiles", return_value=voices), \
                 patch.object(voice_timeline, "load_script_package", return_value=scripts), \
                 patch.object(voice_timeline, "load_shot_breakdown", return_value=shots):
                result = voice_timeline.build_timeline(project)

            self.assertFalse(result["asr_round_trip"])
            self.assertFalse(result["billable"])
            self.assertEqual(result["episodes"][0]["line_count"], 2)
            self.assertEqual(result["episodes"][0]["duration_seconds"], 3.2)
            self.assertEqual(result["episodes"][0]["lines"][0]["text"], "夜色渐沉。")
            self.assertEqual(result["shot_timing"][0]["spoken_duration_seconds"], 3.2)
            self.assertEqual(result["shot_timing"][0]["recommended_duration_seconds"], 3.8)
            self.assertEqual(result["shot_timing"][0]["timing_source"], "SCRIPT_ESTIMATE")

    def test_existing_local_timing_audio_changes_source_to_actual_tts(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            voices, scripts, shots = self.fixtures()
            audio = project / "audio" / "timing-preview" / "s01e001" / "unit-001.wav"
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b"fixture")
            timeline = {
                "episodes": [{
                    "episode_id": "S01E001",
                    "lines": [{
                        "unit_id": "UNIT-001",
                        "audio_path": "audio/timing-preview/s01e001/unit-001.wav",
                        "audio_duration_seconds": 1.7,
                        "provider": "macos_say",
                        "voice": "Tingting",
                    }],
                }]
            }
            stored = project / voice_timeline.OUTPUT
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_text(json.dumps(timeline), encoding="utf-8")
            with patch.object(voice_timeline, "load_voice_profiles", return_value=voices), \
                 patch.object(voice_timeline, "load_script_package", return_value=scripts), \
                 patch.object(voice_timeline, "load_shot_breakdown", return_value=shots):
                result = voice_timeline.build_timeline(project)

            first = result["episodes"][0]["lines"][0]
            self.assertEqual(first["status"], "READY")
            self.assertEqual(first["duration_seconds"], 1.7)
            self.assertEqual(result["shot_timing"][0]["timing_source"], "SCRIPT_ESTIMATE")


if __name__ == "__main__":
    unittest.main()
