import json
import tempfile
import unittest
from pathlib import Path

from scripts.dependency_manager import DependencyError, load_manifest, select_dependencies


class DependencyManagerTests(unittest.TestCase):
    def test_manifest_pins_hyperframes_tag_and_full_commit(self):
        dependency = select_dependencies(load_manifest(), "hyperframes")[0]

        self.assertEqual(dependency["tag"], "v0.8.40")
        self.assertEqual(dependency["commit"], "cfe5dcfad310ced2a5844998628daa2b8a0f53d7")
        self.assertEqual(dependency["update_policy"], "manual")

    def test_manifest_pins_video_use_ref_and_full_commit(self):
        dependency = select_dependencies(load_manifest(), "video-use")[0]

        self.assertEqual(dependency["ref"], "main")
        self.assertEqual(dependency["commit"], "9575612f066aa517354790a645fd90f9f95a743b")
        self.assertNotIn("tag", dependency)

    def test_manifest_rejects_floating_commit(self):
        manifest = {
            "schema_version": 1,
            "dependencies": [
                {
                    "name": "hyperframes",
                    "source": "https://example.test/hyperframes.git",
                    "tag": "latest",
                    "commit": "main",
                    "install_path": ".dependencies/hyperframes",
                    "update_policy": "manual",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dependencies.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(DependencyError, "full 40-character SHA"):
                load_manifest(path)

    def test_unknown_dependency_is_rejected(self):
        with self.assertRaisesRegex(DependencyError, "not declared"):
            select_dependencies(load_manifest(), "unknown")


if __name__ == "__main__":
    unittest.main()
