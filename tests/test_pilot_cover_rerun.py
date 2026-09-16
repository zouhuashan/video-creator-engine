import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.package_project import REQUIRED_FILES
from scripts.pilot_cover_rerun import PilotCoverRerunError, rerun_cover
from scripts.project_state import STAGES, initialize_run_state, load_run_state, transition_project


class PilotCoverRerunTests(unittest.TestCase):
    def _project(self, root):
        project_id = "20260916-cover-rerun"
        directory = root / project_id
        directory.mkdir()
        initialize_run_state(directory, project_id)
        for stage in STAGES[1:STAGES.index("READY_FOR_REVIEW") + 1]:
            transition_project(directory, project_id, stage)

        files = {}
        for name in REQUIRED_FILES:
            data = b"first video" if name == "final.mp4" else (b"old cover" if name == "cover.png" else f"{name} body".encode())
            (directory / name).write_bytes(data)
            files[name] = data

        covers = directory / "covers"
        covers.mkdir()
        (covers / "cover_a.png").write_bytes(b"old cover")
        (covers / "cover_b.png").write_bytes(b"new cover")
        candidates = [{"candidate_id": "COVER_A", "file": "cover_a.png", "sha256": hashlib.sha256(b"old cover").hexdigest()},
                      {"candidate_id": "COVER_B", "file": "cover_b.png", "sha256": hashlib.sha256(b"new cover").hexdigest()}]
        (directory / "cover-candidates.json").write_text(json.dumps({"schema_version": 1, "project_id": project_id,
                                                                       "selected": "COVER_A", "selected_sha256": candidates[0]["sha256"],
                                                                       "candidates": candidates}))
        package_dir = directory / "publish-package"
        package_dir.mkdir()
        package_files = []
        for name, data in files.items():
            (package_dir / name).write_bytes(data)
            package_files.append({"name": name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        (directory / "package.json").write_text(json.dumps({"schema_version": 1, "project_id": project_id,
                                                              "publish_mode": "human_confirmation", "auto_publish": False,
                                                              "directory": "publish-package", "files": package_files}))
        return directory, project_id

    def test_cover_rerun_replaces_only_cover_and_updates_package_checksums(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, project_id = self._project(Path(temp))
            before = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in REQUIRED_FILES}
            result = rerun_cover(directory, project_id, "COVER_B")
            after = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in REQUIRED_FILES}
            self.assertEqual(result["status"], "PASS")
            self.assertNotEqual(before["cover.png"], after["cover.png"])
            self.assertTrue(all(before[name] == after[name] for name in REQUIRED_FILES - {"cover.png"}))
            self.assertEqual((directory / "cover.png").read_bytes(), (directory / "publish-package" / "cover.png").read_bytes())
            self.assertEqual(load_run_state(directory, project_id)["status"], "READY_FOR_REVIEW")
            ledger = json.loads((directory / "cover-rerun.json").read_text())
            self.assertEqual(ledger["runs"][0]["to_candidate"], "COVER_B")
            self.assertFalse(ledger["runs"][0]["video_regenerated"])

    def test_cover_rerun_rejects_same_unknown_or_published_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, project_id = self._project(Path(temp))
            with self.assertRaisesRegex(PilotCoverRerunError, "different candidate"):
                rerun_cover(directory, project_id, "COVER_A")
            with self.assertRaisesRegex(PilotCoverRerunError, "unknown"):
                rerun_cover(directory, project_id, "COVER_C")
            transition_project(directory, project_id, "PUBLISHED_MANUALLY", record_manual_publication=True)
            with self.assertRaisesRegex(PilotCoverRerunError, "READY_FOR_REVIEW"):
                rerun_cover(directory, project_id, "COVER_B")


if __name__ == "__main__":
    unittest.main()
