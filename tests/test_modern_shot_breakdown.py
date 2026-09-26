import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.cost_first_hybrid_router import save_plan, set_render_profile
from scripts.modern_shot_breakdown import apply_modern_shot_breakdown


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "projects/novel-0dbc8f5836"


class ModernShotBreakdownTest(unittest.TestCase):
    def test_short_shots_preserve_prior_breakdown_and_scope_motion_to_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / PILOT.name
            for source in PILOT.rglob("*.json"):
                target = project / source.relative_to(PILOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            set_render_profile(project, "modern_low_cost")
            result = apply_modern_shot_breakdown(project)
            plan = save_plan(project)
            self.assertGreater(result["shot_count"], result["scene_count"])
            self.assertTrue((project / result["backup"]).is_file())
            self.assertTrue((project / result["map"]).is_file())
            self.assertEqual(len(plan["routes"]), result["shot_count"])
            self.assertLessEqual(max(route["duration_seconds"] for route in plan["routes"]), 5.0)
            self.assertLess(plan["summary"]["h3_candidate_count"], result["shot_count"])


if __name__ == "__main__":
    unittest.main()
