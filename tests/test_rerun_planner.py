import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import project_id
import project_state
import rerun_planner


class RerunPlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.temp_dir.name) / "projects"
        self.project_id = project_id.reserve_project_id(
            "ChatGPT Plus worth it",
            "chatgpt-plus-worth-it",
            self.projects_dir,
            date_override="20260915",
        )
        self.directory = self.projects_dir / self.project_id
        (self.directory / "storyboard.json").write_text(
            json.dumps({"scenes": [{"scene_id": "SC007"}, {"scene_id": "SC008"}]}),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def advance_to(self, status):
        for target in project_state.STAGES[1 : project_state.STAGES.index(status) + 1]:
            project_state.transition_project(self.directory, self.project_id, target)

    def test_scene_plan_preserves_other_work_and_does_not_mutate_state(self):
        self.advance_to("EDITED")
        before = (self.directory / "run.json").read_text(encoding="utf-8")

        plan = rerun_planner.rerun_plan(self.directory, self.project_id, "scene", "SC007")

        self.assertEqual(plan["target"], {"type": "scene", "scene_id": "SC007"})
        self.assertEqual(plan["checkpoint"], "VOICE_READY")
        self.assertEqual(plan["resume_stage"], "EDITED")
        self.assertEqual(plan["rebuild"][0], "SC007")
        self.assertIn("all_other_scenes", plan["preserve"])
        self.assertIn("voice", plan["preserve"])
        self.assertNotIn("research", plan["rebuild"])
        self.assertFalse(plan["execution_ready"])
        self.assertFalse(plan["state_changed"])
        self.assertEqual((self.directory / "run.json").read_text(encoding="utf-8"), before)

    def test_scene_plan_accepts_markdown_storyboard_and_rejects_unknown_scene(self):
        (self.directory / "storyboard.json").unlink()
        (self.directory / "storyboard.md").write_text("## SC007\n## SC008-not-an-id\n", encoding="utf-8")
        self.advance_to("EDITED")

        plan = rerun_planner.rerun_plan(self.directory, self.project_id, "scene", "SC007")
        self.assertEqual(plan["target"]["scene_id"], "SC007")
        with self.assertRaisesRegex(project_state.StateError, "not found"):
            rerun_planner.rerun_plan(self.directory, self.project_id, "scene", "SC009")

    def test_each_target_has_a_bounded_rebuild_scope(self):
        self.advance_to("READY_FOR_REVIEW")

        voice = rerun_planner.rerun_plan(self.directory, self.project_id, "voice")
        self.assertEqual(voice["checkpoint"], "ASSETS_READY")
        self.assertIn("reuse_voice_cache", voice["cache_policy"])
        self.assertNotIn("cover.png", voice["rebuild"])

        cover = rerun_planner.rerun_plan(self.directory, self.project_id, "cover")
        self.assertEqual(cover["checkpoint"], "QC_PASS")
        self.assertEqual(cover["rebuild"], ["cover.png", "package.json"])
        self.assertIn("final.mp4", cover["preserve"])

        qc = rerun_planner.rerun_plan(self.directory, self.project_id, "qc")
        self.assertEqual(qc["checkpoint"], "EDITED")
        self.assertEqual(qc["rebuild"], ["qc.json", "qc-report.md", "package.json"])
        self.assertIn("final.mp4", qc["preserve"])

    def test_incomplete_and_published_projects_cannot_be_rerun(self):
        with self.assertRaisesRegex(project_state.StateError, "requires status EDITED"):
            rerun_planner.rerun_plan(self.directory, self.project_id, "scene", "SC007")

        self.advance_to("READY_FOR_REVIEW")
        project_state.transition_project(
            self.directory,
            self.project_id,
            "PUBLISHED_MANUALLY",
            note="User confirmed publication",
            record_manual_publication=True,
        )
        with self.assertRaisesRegex(project_state.StateError, "after manual publication"):
            rerun_planner.rerun_plan(self.directory, self.project_id, "qc")

    def test_rerun_cli_returns_machine_readable_scope(self):
        self.advance_to("EDITED")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "video_creator.py"),
                "rerun",
                self.project_id,
                "--projects-dir",
                str(self.projects_dir),
                "scene",
                "SC007",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        plan = json.loads(result.stdout)
        self.assertEqual(plan["action"], "plan_only")
        self.assertEqual(plan["target"]["scene_id"], "SC007")
        self.assertFalse(plan["state_changed"])


if __name__ == "__main__":
    unittest.main()
