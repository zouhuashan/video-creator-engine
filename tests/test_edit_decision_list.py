import tempfile
import unittest
from pathlib import Path

from scripts.edit_decision_list import (
    EDLError,
    create_edl,
    load_edl,
    prepare_rerender,
    rollback_edl,
    update_range,
)


class EditDecisionListTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.edit_dir = self.root / "edit"
        self.edit_dir.mkdir()
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"source-v1")
        self.project_id = "20260915-edl-test"
        self.payload = {
            "sources": {"A": str(self.source)},
            "ranges": [
                {"source": "A", "start": 0.2, "end": 1.2, "reason": "keep hook"},
                {"source": "A", "start": 1.5, "end": 3.0, "reason": "remove filler gap"},
            ],
            "overlays": [],
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_create_writes_traceable_current_and_history_revision(self):
        edl = create_edl(self.edit_dir, self.project_id, self.payload)

        self.assertEqual(edl["revision"], 1)
        self.assertEqual([item["decision_id"] for item in edl["ranges"]], ["EDL001", "EDL002"])
        self.assertEqual(len(edl["source_checksums"]["A"]), 64)
        self.assertTrue((self.edit_dir / "edit-decision-list.json").is_file())
        self.assertTrue((self.edit_dir / "edl-history" / "revision-0001.json").is_file())

    def test_update_changes_one_range_and_preserves_prior_revision(self):
        original = create_edl(self.edit_dir, self.project_id, self.payload)
        revised = update_range(
            self.edit_dir,
            self.project_id,
            "EDL002",
            {"start": 1.7, "reason": "tighter filler removal"},
            expected_revision=1,
        )

        self.assertEqual(revised["revision"], 2)
        self.assertEqual(revised["parent_revision"], 1)
        self.assertEqual(revised["ranges"][0], original["ranges"][0])
        self.assertNotEqual(revised["render_fingerprint"], original["render_fingerprint"])
        self.assertEqual(load_edl(self.edit_dir, self.project_id)["revision"], 2)

    def test_stale_update_is_rejected(self):
        create_edl(self.edit_dir, self.project_id, self.payload)

        with self.assertRaisesRegex(EDLError, "stale"):
            update_range(
                self.edit_dir,
                self.project_id,
                "EDL001",
                {"reason": "late edit"},
                expected_revision=0,
            )

    def test_rollback_restores_content_as_a_new_auditable_revision(self):
        original = create_edl(self.edit_dir, self.project_id, self.payload)
        update_range(
            self.edit_dir,
            self.project_id,
            "EDL001",
            {"end": 1.0, "reason": "shorter hook"},
            expected_revision=1,
        )
        restored = rollback_edl(
            self.edit_dir, self.project_id, 1, expected_revision=2
        )

        self.assertEqual(restored["revision"], 3)
        self.assertEqual(restored["change"]["kind"], "rollback")
        self.assertEqual(restored["ranges"], original["ranges"])

    def test_rerender_plan_detects_changed_source(self):
        create_edl(self.edit_dir, self.project_id, self.payload)
        ready = prepare_rerender(self.edit_dir, self.project_id)
        self.assertEqual(ready["status"], "READY")

        self.source.write_bytes(b"source-v2")
        with self.assertRaisesRegex(EDLError, "source changed"):
            prepare_rerender(self.edit_dir, self.project_id)

    def test_duplicate_create_is_rejected(self):
        create_edl(self.edit_dir, self.project_id, self.payload)

        with self.assertRaisesRegex(EDLError, "already exists"):
            create_edl(self.edit_dir, self.project_id, self.payload)


if __name__ == "__main__":
    unittest.main()
