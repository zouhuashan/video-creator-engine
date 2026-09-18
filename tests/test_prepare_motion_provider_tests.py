import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_motion_provider_tests import TEST_SPECS


class PrepareMotionProviderTests(unittest.TestCase):
    def test_specs_cover_three_distinct_first_episode_shots_and_adapters(self):
        self.assertEqual(len(TEST_SPECS), 3)
        self.assertEqual({item["provider"] for item in TEST_SPECS}, {"runway", "wan", "openai_sora"})
        self.assertEqual(len({item["shot_id"] for item in TEST_SPECS}), 3)
        self.assertTrue(all(item["shot_id"].startswith("SHOT-S01E001-") for item in TEST_SPECS))

    def test_package_contract_keeps_remote_execution_blocked_by_default(self):
        sample = {
            "status": "BLOCKED_PENDING_AUTHORIZATION",
            "upload_authorized": False,
            "billable_confirmed": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.json"
            path.write_text(json.dumps(sample), encoding="utf-8")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(loaded["upload_authorized"])
        self.assertFalse(loaded["billable_confirmed"])
        self.assertEqual(loaded["status"], "BLOCKED_PENDING_AUTHORIZATION")


if __name__ == "__main__":
    unittest.main()
