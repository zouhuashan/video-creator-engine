import tempfile
import unittest
import json
from pathlib import Path

from scripts.pilot_metrics import PilotMetricsError, create_tracker, record_metrics, validate_metrics
from scripts.project_state import STAGES, initialize_run_state, transition_project


class PilotMetricsTests(unittest.TestCase):
    def _projects(self, root):
        ids = []
        for number in range(10):
            project_id = f"20260916-metrics-{number + 1}"
            directory = root / project_id
            directory.mkdir()
            initialize_run_state(directory, project_id)
            for stage in STAGES[1:STAGES.index("READY_FOR_REVIEW") + 1]:
                transition_project(directory, project_id, stage)
            ids.append(project_id)
        return ids

    @staticmethod
    def _report(ids):
        return {"status": "PASS", "verified_projects": 10,
                "projects": [{"project_id": project_id} for project_id in ids]}

    @staticmethod
    def _sample():
        return {"views": 1000, "completion_rate": 35.5, "retention_3s": 78,
                "retention_5s": 62, "likes": 40, "comments": 3,
                "favorites": 12, "shares": 9, "follows": 2}

    def test_bootstrap_creates_ten_empty_entries_and_requires_manual_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ids = self._projects(root)
            tracker = create_tracker(self._report(ids), root)
            self.assertEqual(len(tracker["projects"]), 10)
            self.assertTrue(all(item["collection_status"] == "awaiting_manual_publish" for item in tracker["projects"]))
            tracker_path = root / "metrics.json"
            tracker_path.write_text(json.dumps(tracker))
            with self.assertRaisesRegex(PilotMetricsError, "manually published"):
                record_metrics(tracker_path, ids[0], root, self._sample(), "2026-09-16T12:00:00+08:00", "WeChat Channels", "export.csv")

    def test_records_a_valid_observation_only_after_manual_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ids = self._projects(root)
            tracker_path = root / "metrics.json"
            tracker_path.write_text(json.dumps(create_tracker(self._report(ids), root)))
            transition_project(root / ids[0], ids[0], "PUBLISHED_MANUALLY",
                               record_manual_publication=True, note="user manually published")
            result = record_metrics(tracker_path, ids[0], root, self._sample(),
                                    "2026-09-16T12:00:00+08:00", "WeChat Channels", "creator-center-export.csv")
            self.assertEqual(result["projects"][0]["collection_status"], "recorded")
            self.assertEqual(result["projects"][0]["observations"][0]["metrics"]["views"], 1000)
            with self.assertRaisesRegex(PilotMetricsError, "already exists"):
                record_metrics(tracker_path, ids[0], root, self._sample(),
                               "2026-09-16T12:00:00+08:00", "WeChat Channels", "creator-center-export.csv")

    def test_rejects_missing_fields_invalid_percentages_and_boolean_counts(self):
        sample = self._sample()
        with self.assertRaisesRegex(PilotMetricsError, "fields mismatch"):
            validate_metrics({"views": 10})
        sample["retention_3s"] = 101
        with self.assertRaisesRegex(PilotMetricsError, "percentage"):
            validate_metrics(sample)
        sample["retention_3s"] = 50
        sample["views"] = True
        with self.assertRaisesRegex(PilotMetricsError, "integer"):
            validate_metrics(sample)


if __name__ == "__main__":
    unittest.main()
