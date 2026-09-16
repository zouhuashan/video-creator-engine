import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "validation" / "fiction-workflow-pilot.json"
sys.path.insert(0, str(ROOT))

from scripts import novel_adaptation


def sample():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class NovelAdaptationTests(unittest.TestCase):
    def test_valid_pilot_maps_every_beat_to_source_and_keeps_main_ip_off(self):
        result = novel_adaptation.validate_adaptation(sample())

        self.assertEqual(result["novel"]["title"], "聊斋志异·种梨")
        self.assertFalse(result["is_main_ip"])
        self.assertEqual(len(result["adaptation"]["script"]), 6)
        self.assertEqual(result["adaptation"]["storyboard"][-1]["end"], 45.0)
        self.assertTrue(result["rights"]["human_review_required_before_publication"])

    def test_unknown_or_incomplete_rights_evidence_block_before_outputs(self):
        payload = sample()
        payload["rights"]["status"] = "free_to_read"
        with self.assertRaisesRegex(novel_adaptation.NovelAdaptationError, "rights gate blocked"):
            novel_adaptation.validate_adaptation(payload)

        payload = sample()
        payload["rights"]["evidence_urls"] = []
        with self.assertRaisesRegex(novel_adaptation.NovelAdaptationError, "at least one evidence URL"):
            novel_adaptation.validate_adaptation(payload)

    def test_unknown_source_mapping_and_storyboard_gap_are_rejected(self):
        payload = sample()
        payload["adaptation"]["script"][0]["source_segment_ids"] = ["SRC-999"]
        with self.assertRaisesRegex(novel_adaptation.NovelAdaptationError, "known source segments"):
            novel_adaptation.validate_adaptation(payload)

        payload = sample()
        payload["adaptation"]["storyboard"][2]["start"] = 15
        with self.assertRaisesRegex(novel_adaptation.NovelAdaptationError, "gap or overlap"):
            novel_adaptation.validate_adaptation(payload)

    def test_noncanonical_access_date_is_rejected(self):
        payload = sample()
        payload["source"]["accessed_at"] = "20260916"
        with self.assertRaisesRegex(novel_adaptation.NovelAdaptationError, "YYYY-MM-DD"):
            novel_adaptation.validate_adaptation(payload)

    def test_cli_builds_review_package_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "pilot"
            command = [
                sys.executable,
                str(ROOT / "scripts" / "novel_adaptation.py"),
                str(FIXTURE),
                "--output-dir",
                str(output_dir),
            ]
            first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            report = json.loads((output_dir / "run-report.json").read_text(encoding="utf-8"))
            rights = json.loads((output_dir / "rights-review.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "READY_FOR_HUMAN_REVIEW")
            self.assertTrue((output_dir / "rough-cut.mp4").is_file())
            self.assertEqual(rights["status"], "REQUIRES_HUMAN_REVIEW")
            self.assertFalse(rights["publication_allowed"])
            self.assertFalse(rights["evidence_checked_by_tool"])

            second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("refusing to overwrite", second.stderr)


if __name__ == "__main__":
    unittest.main()
