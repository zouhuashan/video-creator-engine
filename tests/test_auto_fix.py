import json
import tempfile
import unittest
from pathlib import Path

from scripts import project_state
from scripts.auto_fix import AutoFixError, EXPECTED_CHECKS, execute_auto_fixes, finalize_qc, plan_auto_fixes


class FakeExecutor:
    def __init__(self):
        self.categories = []

    def apply(self, issue):
        self.categories.append(issue["category"])
        return {"status": "APPLIED", "artifact": issue["target"]}


class AutoFixTests(unittest.TestCase):
    @staticmethod
    def issue(number, category):
        return {"issue_id": f"FIX{number:03d}", "category": category, "target": "final.mp4",
                "reason": "QC failure", "parameters": {}}

    def test_all_six_low_risk_categories_can_be_dispatched(self):
        categories = ["subtitle_position", "audio_volume", "blank_shot", "transcoding", "minor_duration", "subtitle_segmentation"]
        plan = plan_auto_fixes({"schema_version": 1, "issues": [self.issue(i + 1, value) for i, value in enumerate(categories)]})
        executor = FakeExecutor()
        result = execute_auto_fixes(plan, executor)
        self.assertEqual(result["status"], "RERUN_QC_REQUIRED")
        self.assertEqual(executor.categories, categories)

    def test_forbidden_change_routes_whole_batch_to_script_review(self):
        request = {"schema_version": 1, "issues": [self.issue(1, "audio_volume"), self.issue(2, "core_facts")]}
        plan = plan_auto_fixes(request)
        self.assertEqual(plan["status"], "SCRIPT_REVIEW_REQUIRED")
        self.assertEqual(plan["route"], "SCRIPT_REVIEW")
        executor = FakeExecutor()
        with self.assertRaisesRegex(AutoFixError, "blocked"):
            execute_auto_fixes(plan, executor)
        self.assertEqual(executor.categories, [])

    def test_unknown_categories_and_duplicate_ids_are_rejected(self):
        with self.assertRaisesRegex(AutoFixError, "unknown"):
            plan_auto_fixes({"schema_version": 1, "issues": [self.issue(1, "rewrite_opinion")]})
        with self.assertRaisesRegex(AutoFixError, "unique"):
            plan_auto_fixes({"schema_version": 1, "issues": [self.issue(1, "transcoding"), self.issue(1, "audio_volume")]})

    def test_final_qc_passes_only_when_all_three_reports_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            project_id = "20260915-qc-final"
            directory = Path(temp) / project_id
            directory.mkdir()
            project_state.initialize_run_state(directory, project_id)
            for stage in project_state.STAGES[1:project_state.STAGES.index("EDITED") + 1]:
                project_state.transition_project(directory, project_id, stage)
            qc_dir = directory / "qc"
            qc_dir.mkdir()
            for filename in ("technical-qc.json", "content-qc.json", "visual-qc.json"):
                checks = {name: True for name in EXPECTED_CHECKS[filename]}
                (qc_dir / filename).write_text(json.dumps({"status": "PASS", "checks": checks, "generated_at": "2026-09-15T01:00:00.000Z"}))
            result = finalize_qc(directory, project_id)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["state"], "QC_PASS")
            self.assertTrue((directory / "qc-report.md").is_file())

    def test_failed_or_stale_qc_never_advances_state(self):
        with tempfile.TemporaryDirectory() as temp:
            project_id = "20260915-qc-fail"
            directory = Path(temp) / project_id
            directory.mkdir()
            project_state.initialize_run_state(directory, project_id)
            for stage in project_state.STAGES[1:project_state.STAGES.index("EDITED") + 1]:
                project_state.transition_project(directory, project_id, stage)
            qc_dir = directory / "qc"
            qc_dir.mkdir()
            for filename in ("technical-qc.json", "content-qc.json", "visual-qc.json"):
                checks = {name: True for name in EXPECTED_CHECKS[filename]}
                (qc_dir / filename).write_text(json.dumps({"status": "PASS", "checks": checks, "generated_at": "2026-09-15T01:00:00.000Z"}))
            (qc_dir / "auto-fix.json").write_text(json.dumps({"status": "RERUN_QC_REQUIRED", "completed_at": "2026-09-15T02:00:00.000Z"}))
            with self.assertRaisesRegex(AutoFixError, "regenerated"):
                finalize_qc(directory, project_id)
            self.assertEqual(project_state.load_run_state(directory, project_id)["status"], "EDITED")


if __name__ == "__main__":
    unittest.main()
