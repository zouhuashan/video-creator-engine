import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.modern_editable_timeline import load_timeline, rerender_shot, update_shot


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "projects/novel-0dbc8f5836"


class ModernEditableTimelineTest(unittest.TestCase):
    def test_one_shot_edit_and_local_rerender_preserve_other_shots(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / PILOT.name
            for source in PILOT.rglob("*.json"):
                target = project / source.relative_to(PILOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            timeline = load_timeline(project)
            self.assertGreater(timeline["shot_count"], 0)
            self.assertEqual(len(timeline["tracks"]), 10)
            first, second = timeline["shots"][:2]
            shot_id = first["shot_id"]
            update_shot(project, shot_id, {"motion_strategy": "SCREEN_MG", "screen_mg": {"template": "chat", "title": "消息", "lines": ["请来办公室"]}})
            edited = load_timeline(project)
            self.assertEqual(edited["shots"][0]["motion_strategy"], "SCREEN_MG")
            self.assertEqual(edited["shots"][0]["status"], "DIRTY")
            self.assertEqual(edited["shots"][1]["shot_id"], second["shot_id"])
            self.assertEqual(edited["shots"][1]["motion_strategy"], second["motion_strategy"])
            rendered = rerender_shot(project, shot_id)
            self.assertEqual(rendered["status"], "PREVIEW_READY")
            self.assertTrue((project / rendered["preview"]["output"]).is_file())
            self.assertFalse(load_timeline(project)["shots"][1]["preview"])


if __name__ == "__main__":
    unittest.main()
