import json
import tempfile
import unittest
from pathlib import Path

from scripts import project_state
from scripts.package_project import PackagingError, load_config, package_project


class PackageProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project_id = "20260915-package-test"
        self.directory = Path(self.temp.name) / self.project_id
        self.directory.mkdir()
        project_state.initialize_run_state(self.directory, self.project_id)
        for stage in project_state.STAGES[1:project_state.STAGES.index("QC_PASS") + 1]:
            project_state.transition_project(self.directory, self.project_id, stage)
        (self.directory / "qc.json").write_text(json.dumps({"status": "PASS", "failed_reports": []}))
        for filename in load_config()["required_files"]:
            content = b"\x89PNG\r\n\x1a\nimage" if filename == "cover.png" else b"video" if filename == "final.mp4" else b"content\n"
            (self.directory / filename).write_bytes(content)

    def tearDown(self):
        self.temp.cleanup()

    def test_builds_complete_checksum_package_and_advances_state(self):
        result = package_project(self.directory, self.project_id)
        manifest = json.loads((self.directory / "package.json").read_text())
        self.assertEqual(result["state"], "PACKAGED")
        self.assertEqual(len(manifest["files"]), 7)
        self.assertFalse(manifest["auto_publish"])
        for item in manifest["files"]:
            self.assertEqual(len(item["sha256"]), 64)
            self.assertTrue((self.directory / "publish-package" / item["name"]).is_file())

    def test_requires_qc_pass_and_every_nonempty_artifact(self):
        (self.directory / "qc.json").write_text(json.dumps({"status": "FAIL", "failed_reports": ["visual_qc"]}))
        with self.assertRaisesRegex(PackagingError, "PASS QC"):
            package_project(self.directory, self.project_id)
        self.assertFalse((self.directory / "publish-package").exists())

        (self.directory / "qc.json").write_text(json.dumps({"status": "PASS", "failed_reports": []}))
        (self.directory / "title.md").write_text("")
        with self.assertRaisesRegex(PackagingError, "missing, empty"):
            package_project(self.directory, self.project_id)

    def test_rejects_fake_png_and_existing_package(self):
        (self.directory / "cover.png").write_bytes(b"not-png")
        with self.assertRaisesRegex(PackagingError, "valid PNG"):
            package_project(self.directory, self.project_id)
        (self.directory / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
        package_project(self.directory, self.project_id)
        with self.assertRaisesRegex(project_state.StateError, "QC_PASS"):
            package_project(self.directory, self.project_id)

    def test_config_keeps_publication_manual(self):
        config = load_config()
        self.assertEqual(config["publish_mode"], "human_confirmation")
        self.assertFalse(config["auto_publish"])


if __name__ == "__main__":
    unittest.main()
