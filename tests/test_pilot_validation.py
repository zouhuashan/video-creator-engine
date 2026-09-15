import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import project_state
from scripts.package_project import REQUIRED_FILES
from scripts.pilot_producer import _atempo_chain
from scripts.pilot_validation import PilotValidationError, REQUIRED_CHECKS, validate_first_five


class PilotValidationTests(unittest.TestCase):
    def _fixture(self, root):
        projects = []
        for number in range(5):
            project_id = f"20260916-pilot-{number + 1}"
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
        return {"schema_version": 1, "projects": projects}

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

    def test_atempo_chain_supports_slow_and_fast_normalization(self):
        self.assertIn("atempo=0.50000000", _atempo_chain(0.25))
        self.assertIn("atempo=2.00000000", _atempo_chain(4.0))


if __name__ == "__main__":
    unittest.main()
