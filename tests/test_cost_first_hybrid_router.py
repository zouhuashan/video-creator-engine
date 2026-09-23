import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.cost_first_hybrid_router as router


class CostFirstHybridRouterTests(unittest.TestCase):
    def fake_shots(self):
        def state(chars):
            return {"location_id": "LOC-GATE", "character_ids": chars, "prop_state_ids": [], "emotion": "", "continuity_signature": "x"}
        return {
            "revision": 7,
            "scene_breakdowns": [
                {
                    "scene_id": "S01E001-SC001",
                    "episode_id": "S01E001",
                    "location_id": "LOC-GATE",
                    "shots": [{
                        "id": "SHOT-S01E001-SC001-001", "shot_type": "MEDIUM", "movement": "静态",
                        "duration_seconds": 4.0, "start_state": state(["CHR-HERO"]), "end_state": state(["CHR-HERO"]),
                    }],
                },
                {
                    "scene_id": "S01E001-SC002",
                    "episode_id": "S01E001",
                    "location_id": "LOC-GATE",
                    "shots": [{
                        "id": "SHOT-S01E001-SC002-001", "shot_type": "WIDE", "movement": "跟拍",
                        "duration_seconds": 5.0, "start_state": state(["CHR-HERO"]), "end_state": state(["CHR-HERO"]),
                    }],
                },
            ],
        }

    def fake_scripts(self):
        def unit(uid, kind, text):
            return {
                "id": uid, "sequence": 1, "kind": kind, "text": text,
                "speaker_character_id": "CHR-HERO" if kind == "DIALOGUE" else None,
                "emotion": None, "sound": None, "estimated_duration_seconds": 2,
                "beat_ref": None, "provenance": {},
            }
        return {
            "revision": 11,
            "episode_scripts": [{
                "episode_id": "S01E001",
                "scenes": [
                    {
                        "id": "S01E001-SC001", "location_id": "LOC-GATE", "time_of_day": "夜",
                        "character_ids": ["CHR-HERO"],
                        "units": [unit("U1", "DIALOGUE", "这里就是沈府？")],
                    },
                    {
                        "id": "S01E001-SC002", "location_id": "LOC-GATE", "time_of_day": "夜",
                        "character_ids": ["CHR-HERO"],
                        "units": [unit("U2", "ACTION", "主角拔剑冲刺，与黑衣人挥剑交手。")],
                    },
                ],
            }],
        }

    def test_dialogue_goes_local_and_high_action_is_h3_locked(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(router, "load_shot_breakdown", return_value=self.fake_shots()), \
             patch.object(router, "load_script_package", return_value=self.fake_scripts()):
            result = router.build_plan(Path(directory))

        first, second = result["routes"]
        self.assertEqual(first["route"], "LOCAL_MICRO_MOTION")
        self.assertFalse(first["h3_locked"])
        self.assertEqual(second["route"], "H3_CANDIDATE")
        self.assertTrue(second["h3_locked"])
        self.assertFalse(second["h3_escalation"]["approved"])
        self.assertIn("挥剑", second["motion"]["high_keywords"])
        self.assertIn("冲刺", second["motion"]["high_keywords"])

    def test_hybrid_cost_only_counts_h3_candidates_and_reports_savings(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(router, "load_shot_breakdown", return_value=self.fake_shots()), \
             patch.object(router, "load_script_package", return_value=self.fake_scripts()):
            result = router.build_plan(Path(directory))

        summary = result["summary"]
        self.assertEqual(summary["all_h3_estimated_shells"], 126.0)
        self.assertEqual(summary["hybrid_h3_estimated_shells"], 70.0)
        self.assertEqual(summary["estimated_shells_saved"], 56.0)
        self.assertGreater(summary["estimated_shell_savings_percent"], 40)
        self.assertEqual(summary["estimated_new_still_generations_after_reuse"], 1)

    def test_same_visual_signature_reuses_still_instead_of_regenerating_per_shot(self):
        shots = self.fake_shots()
        scripts = self.fake_scripts()
        scripts["episode_scripts"][0]["scenes"][1]["units"] = [{
            "id": "U2", "sequence": 1, "kind": "DIALOGUE", "text": "无人回应。",
            "speaker_character_id": "CHR-HERO", "emotion": None, "sound": None,
            "estimated_duration_seconds": 2, "beat_ref": None, "provenance": {},
        }]
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(router, "load_shot_breakdown", return_value=shots), \
             patch.object(router, "load_script_package", return_value=scripts):
            result = router.build_plan(Path(directory))

        self.assertEqual([item["route"] for item in result["routes"]], ["LOCAL_MICRO_MOTION", "LOCAL_MICRO_MOTION"])
        self.assertEqual(result["summary"]["estimated_new_still_generations_after_reuse"], 1)
        self.assertEqual(len(result["reuse_requirements"]), 1)


if __name__ == "__main__":
    unittest.main()
