"""Regression for recovering an old project with empty episode scenes."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.novel_scene_backfill import apply_scene_seed
from scripts.novel_shot_breakdown import build_shot_breakdown, write_shot_breakdown
from scripts.repair_scene_dependencies import reconcile_after_scene_backfill


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "projects/novel-0dbc8f5836"


class SceneBackfillRebuildTest(unittest.TestCase):
    def test_backfill_preserves_assets_and_builds_real_shots(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / PILOT.name
            for source in PILOT.rglob("*.json"):
                target = project / source.relative_to(PILOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            for path in (project / "writing-room/episodes").glob("*/script.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["episode_script"]["scenes"] = []
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            (project / "storyboard/shot-breakdown.json").unlink(missing_ok=True)
            original_review = json.loads((project / "visual-bible/asset-review.json").read_text(encoding="utf-8"))

            result = apply_scene_seed(project)
            dependencies = reconcile_after_scene_backfill(project)
            shots = build_shot_breakdown(project)
            write_shot_breakdown(project, shots, overwrite=True)

            self.assertEqual(result["scene_count"], 15)
            self.assertEqual(len(shots["scene_breakdowns"]), 15)
            self.assertEqual(sum(len(scene["shots"]) for scene in shots["scene_breakdowns"]), 15)
            self.assertEqual(dependencies["script_revision"], result["script_revision"])
            self.assertEqual(json.loads((project / "visual-bible/asset-review.json").read_text(encoding="utf-8"))["reference_packages"], original_review["reference_packages"])


if __name__ == "__main__":
    unittest.main()
