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

    def test_apply_actual_tts_timing_updates_matching_shot_only(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            timeline_path = project / voice_timeline.OUTPUT
            timeline_path.parent.mkdir(parents=True, exist_ok=True)
            timeline_path.write_text(json.dumps({
                "episodes": [{
                    "episode_id": "S01E001",
                    "status": "READY",
                    "lines": [{"unit_id": "UNIT-001"}],
                }],
                "shot_timing": [{
                    "episode_id": "S01E001",
                    "shot_id": "SHOT-SC-S01E001-001-001",
                    "timing_source": "ACTUAL_TTS",
                    "recommended_duration_seconds": 4.6,
                }],
            }), encoding="utf-8")
            package = {
                "revision": 3,
                "updated_at": "old",
                "scene_breakdowns": [{
                    "episode_id": "S01E001",
                    "shots": [{
                        "id": "SHOT-SC-S01E001-001-001",
                        "sequence": 1,
                        "shot_type": "WIDE",
                        "framing": "竖屏全景",
                        "angle": "平视",
                        "movement": "静态",
                        "lens": "35mm",
                        "duration_seconds": 8.0,
                        "start_state": {},
                        "end_state": {},
                        "reference_ids": [],
                        "continuity_signature": "old",
                    }],
                }],
            }
            written = {}

            def fake_write(_project, payload, overwrite=False):
                written["payload"] = payload
                written["overwrite"] = overwrite
                return project / "storyboard" / "shot-breakdown.json"

            with patch.object(voice_timeline, "load_shot_breakdown", return_value=package), \
                 patch.object(voice_timeline, "write_shot_breakdown", side_effect=fake_write), \
                 patch.object(voice_timeline, "shot_signature", return_value="new-signature"):
                result = voice_timeline.apply_to_shot_breakdown(project, "S01E001")

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["updated_shot_count"], 1)
            self.assertEqual(result["updated"][0]["before_seconds"], 8.0)
            self.assertEqual(result["updated"][0]["after_seconds"], 4.6)
            self.assertEqual(written["payload"]["revision"], 4)
            self.assertEqual(written["payload"]["scene_breakdowns"][0]["shots"][0]["duration_seconds"], 4.6)
            self.assertEqual(written["payload"]["scene_breakdowns"][0]["shots"][0]["continuity_signature"], "new-signature")
            self.assertTrue(written["overwrite"])

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
