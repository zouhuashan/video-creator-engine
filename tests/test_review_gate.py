import json
import tempfile
import unittest
from pathlib import Path

from scripts import project_state
from scripts.package_project import load_config, package_project
from scripts.review_gate import ReviewGateError, enter_review_gate, terminal_summary


class ReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project_id = "20260915-review-gate"
        self.directory = Path(self.temp.name) / self.project_id
        self.directory.mkdir()
        project_state.initialize_run_state(self.directory, self.project_id)
        for stage in project_state.STAGES[1:project_state.STAGES.index("QC_PASS") + 1]:
            project_state.transition_project(self.directory, self.project_id, stage)
        (self.directory / "qc.json").write_text(json.dumps({"status": "PASS", "failed_reports": []}))
        for filename in load_config()["required_files"]:
            content = b"\x89PNG\r\n\x1a\nimage" if filename == "cover.png" else b"video" if filename == "final.mp4" else b"content\n"
            (self.directory / filename).write_bytes(content)
        package_project(self.directory, self.project_id)

    def tearDown(self):
        self.temp.cleanup()

    def test_verified_package_enters_ready_for_review(self):
        result = enter_review_gate(self.directory, self.project_id)
        self.assertEqual(result["state"], "READY_FOR_REVIEW")
        self.assertEqual(result["next_action"], "WAITING_FOR_HUMAN_PUBLISH")
        self.assertEqual(len(result["files"]), 7)
        self.assertTrue((self.directory / "review-gate.json").is_file())

    def test_terminal_summary_matches_human_gate_contract(self):
        output = terminal_summary()
        for expected in ("FINAL READY", "✓ final.mp4", "✓ cover.png", "✓ title", "✓ caption",
                         "✓ hashtags", "✓ sources", "✓ QC PASS", "WAITING FOR HUMAN PUBLISH"):
            self.assertIn(expected, output)

    def test_changed_package_file_blocks_review_without_state_change(self):
        (self.directory / "publish-package" / "title.md").write_text("changed")
        with self.assertRaisesRegex(ReviewGateError, "changed after packaging"):
            enter_review_gate(self.directory, self.project_id)
        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "PACKAGED")
        self.assertFalse((self.directory / "review-gate.json").exists())

    def test_failed_qc_and_non_manual_manifest_are_rejected(self):
        (self.directory / "qc.json").write_text(json.dumps({"status": "FAIL", "failed_reports": ["visual_qc"]}))
        with self.assertRaisesRegex(ReviewGateError, "QC PASS"):
            enter_review_gate(self.directory, self.project_id)

        (self.directory / "qc.json").write_text(json.dumps({"status": "PASS", "failed_reports": []}))
        manifest = json.loads((self.directory / "package.json").read_text())
        manifest["auto_publish"] = True
        (self.directory / "package.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ReviewGateError, "human publication"):
            enter_review_gate(self.directory, self.project_id)


if __name__ == "__main__":
    unittest.main()
