import tempfile
import unittest
from pathlib import Path

from scripts.cost_first_hybrid_router import CostFirstRoutingError, MOTION_STRATEGIES, _motion_strategy, load_render_profile, set_render_profile


class ModernMotionStrategyTest(unittest.TestCase):
    def test_six_strategies_are_exclusive_and_cost_explicit(self):
        base = {"character_ids": ["CHR-A"], "units": [{"kind": "DIALOGUE", "text": "你好"}]}
        shot = {"shot_type": "CLOSE_UP"}
        motion = {}
        cases = [
            (base, "LOCAL_SCENE_PLATE", "STATIC"),
            (base, "LOCAL_MICRO_MOTION", "LOCAL_MOTION"),
            (base, "LOCAL_TWO_CUT", "LAYERED_2_5D"),
            ({**base, "units": [{"text": "手机屏幕收到短信"}]}, "LOCAL_SCENE_PLATE", "SCREEN_MG"),
            ({"character_ids": [], "units": [{"text": "城市夜景车流"}]}, "LOCAL_SCENE_PLATE", "STOCK_BROLL"),
            (base, "H3_CANDIDATE", "AI_VIDEO"),
        ]
        self.assertEqual(len(cases), len(MOTION_STRATEGIES))
        for scene, route, expected in cases:
            with self.subTest(strategy=expected):
                result = _motion_strategy(scene, shot, motion, route, "modern_low_cost", 35.0)
                self.assertEqual(result["motion_strategy"], expected)
                self.assertTrue(result["renderer"])
                self.assertTrue(result["reason"])
                self.assertIn("amount", result["estimated_cost"])
        self.assertEqual(_motion_strategy(base, shot, motion, "H3_CANDIDATE", "modern_low_cost", 35.0)["estimated_cost"]["amount"], 35.0)

    def test_profile_is_persistent_and_rejects_unknown_values(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.assertEqual(load_render_profile(project), "ancient_cinematic")
            set_render_profile(project, "modern_low_cost")
            self.assertEqual(load_render_profile(project), "modern_low_cost")
            with self.assertRaises(CostFirstRoutingError):
                set_render_profile(project, "other")


if __name__ == "__main__":
    unittest.main()
