import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from scripts import project_state
from scripts.package_project import REQUIRED_FILES
from scripts.pilot_producer import PilotProductionError, _atempo_chain, produce_batch
from scripts.pilot_validation import PilotValidationError, REQUIRED_CHECKS, validate_first_five, validate_first_ten


class PilotValidationTests(unittest.TestCase):
    def _fixture(self, root, prefix="pilot"):
        projects = []
        for number in range(5):
            project_id = f"20260916-{prefix}-{number + 1}"
            directory = root / project_id
            directory.mkdir()
            project_state.initialize_run_state(directory, project_id)
            for stage in project_state.STAGES[1:project_state.STAGES.index("READY_FOR_REVIEW") + 1]:
                project_state.transition_project(directory, project_id, stage)
            video = directory / "final.mp4"
            video.write_bytes(f"video-{number}".encode())
            digest = hashlib.sha256(video.read_bytes()).hexdigest()
            checks = {name: True for name in REQUIRED_CHECKS}
            (directory / "pilot-evaluation.json").write_text(json.dumps({"status": "PASS", "checks": checks, "final_sha256": digest}))
            (directory / "qc.json").write_text(json.dumps({"status": "PASS", "failed_reports": []}))
            (directory / "package.json").write_text(json.dumps({"files": [{"name": name} for name in REQUIRED_FILES]}))
            projects.append({"project_id": project_id, "status": "PASS"})
        return {"schema_version": 1, "status": "PASS", "batch_id": prefix, "projects": projects}

    @staticmethod
    def inspector(path):
        return {"width": 1080, "height": 1920, "fps": 30.0, "video_codec": "h264",
                "audio_codec": "aac", "duration_seconds": 56.0}

    def test_independently_accepts_five_complete_ready_projects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = validate_first_five(self._fixture(root), root, self.inspector)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["verified_projects"], 5)

    def test_rejects_missing_project_failed_check_and_changed_video(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = self._fixture(root)
            with self.assertRaisesRegex(PilotValidationError, "exactly five"):
                validate_first_five({"schema_version": 1, "projects": report["projects"][:4]}, root, self.inspector)
            first = root / report["projects"][0]["project_id"]
            evaluation = json.loads((first / "pilot-evaluation.json").read_text())
            evaluation["checks"]["voice"] = False
            (first / "pilot-evaluation.json").write_text(json.dumps(evaluation))
            with self.assertRaisesRegex(PilotValidationError, "incomplete pilot checks"):
                validate_first_five(report, root, self.inspector)

    def test_independently_accepts_two_batches_as_ten_unique_projects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = self._fixture(root), self._fixture(root, "second")
            result = validate_first_ten(first, second, root, self.inspector)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["verified_projects"], 10)
            with self.assertRaisesRegex(PilotValidationError, "ten unique"):
                validate_first_ten(first, first, root, self.inspector)

    def test_batch_producer_resumes_complete_projects_to_a_custom_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            projects_dir = root / "projects"
            projects_dir.mkdir()
            today = date.today().strftime("%Y%m%d")
            specs = [{"slug": f"resume-{number}"} for number in range(5)]
            for spec in specs:
                project_id = f"{today}-{spec['slug']}"
                directory = projects_dir / project_id
                directory.mkdir()
                (directory / "pilot-evaluation.json").write_text(json.dumps({"project_id": project_id, "status": "PASS"}))
            batch_file = root / "batch.json"
            batch_file.write_text(json.dumps({"schema_version": 1, "batch_id": "resume-test", "projects": specs}))
            font = root / "font.ttc"
            font.write_text("fixture")
            output = root / "reports" / "custom.json"
            with patch("scripts.pilot_producer.FONT", font):
                report = produce_batch(batch_file, projects_dir, output)
            self.assertEqual(report["ready_projects"], 5)
            self.assertTrue(output.is_file())
            with patch("scripts.pilot_producer.FONT", font), self.assertRaisesRegex(PilotProductionError, "overwrite"):
                produce_batch(batch_file, projects_dir, output)

    def test_atempo_chain_supports_slow_and_fast_normalization(self):
        self.assertIn("atempo=0.50000000", _atempo_chain(0.25))
        self.assertIn("atempo=2.00000000", _atempo_chain(4.0))


if __name__ == "__main__":
    unittest.main()
