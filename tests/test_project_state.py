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


class ProjectStateTests(unittest.TestCase):
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

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_new_project_is_initialized_at_created(self):
        state = json.loads((self.directory / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "CREATED")
        self.assertEqual(state["project_id"], self.project_id)
        self.assertEqual(state["history"][-1]["to"], "CREATED")
        self.assertTrue(state["created_at"].endswith("Z"))

    def test_only_next_stage_is_allowed_and_persisted(self):
        with self.assertRaisesRegex(project_state.StateError, "expected RESEARCHED"):
            project_state.transition_project(self.directory, self.project_id, "SCRIPTED")

        state = project_state.load_run_state(self.directory, self.project_id)
        self.assertEqual(state["status"], "CREATED")
        state = project_state.transition_project(self.directory, self.project_id, "RESEARCHED", "Sources checked")
        self.assertEqual(state["status"], "RESEARCHED")
        self.assertEqual(state["history"][-1]["note"], "Sources checked")

    def test_manual_publication_requires_explicit_recording(self):
        for target in project_state.STAGES[1:-1]:
            project_state.transition_project(self.directory, self.project_id, target)

        with self.assertRaisesRegex(project_state.StateError, "explicit confirmation"):
            project_state.transition_project(self.directory, self.project_id, "PUBLISHED_MANUALLY")
        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "READY_FOR_REVIEW")

        state = project_state.transition_project(
            self.directory,
            self.project_id,
            "PUBLISHED_MANUALLY",
            note="User confirmed publication",
            record_manual_publication=True,
        )
        self.assertEqual(state["status"], "PUBLISHED_MANUALLY")

    def test_resume_plan_starts_after_last_completed_stage(self):
        plan = project_state.resume_plan(self.directory, self.project_id)
        self.assertEqual(plan["action"], "continue")
        self.assertEqual(plan["resume_stage"], "RESEARCHED")
        self.assertEqual(plan["completed_stages"], ["CREATED"])

        project_state.transition_project(self.directory, self.project_id, "RESEARCHED")
        project_state.transition_project(self.directory, self.project_id, "SCRIPTED")
        plan = project_state.resume_plan(self.directory, self.project_id)
        self.assertEqual(plan["resume_stage"], "STORYBOARDED")
        self.assertEqual(plan["completed_stages"][-1], "SCRIPTED")

    def test_resume_cli_prints_checkpoint_without_mutating_state(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "video_creator.py"),
                "resume",
                self.project_id,
                "--projects-dir",
                str(self.projects_dir),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        plan = json.loads(result.stdout)
        self.assertEqual(plan["resume_stage"], "RESEARCHED")
        self.assertEqual(plan["action"], "continue")
        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "CREATED")

    def test_resume_waits_for_human_review_and_stops_when_complete(self):
        for target in project_state.STAGES[1:-1]:
            project_state.transition_project(self.directory, self.project_id, target)

        plan = project_state.resume_plan(self.directory, self.project_id)
        self.assertEqual(plan["action"], "await_human_review")
        self.assertIsNone(plan["resume_stage"])

        project_state.transition_project(
            self.directory,
            self.project_id,
            "PUBLISHED_MANUALLY",
            note="User confirmed publication",
            record_manual_publication=True,
        )
        plan = project_state.resume_plan(self.directory, self.project_id)
        self.assertEqual(plan["action"], "complete")
        self.assertIsNone(plan["resume_stage"])


if __name__ == "__main__":
    unittest.main()
