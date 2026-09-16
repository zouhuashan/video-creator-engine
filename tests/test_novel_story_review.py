import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_episode_planning import build_episode_planning, load_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, write_script_package
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible
from scripts.novel_story_review import NovelStoryReviewError, approve_report, audit_story, load_report, summary, write_report


class NovelStoryReviewTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        project_dir = root / "project-test"
        write_project(project_dir, build_project("project-test", "TST", "测试故事"))
        write_catalog(project_dir, build_catalog("project-test", "IP-TST", "测试故事"))
        write_bible(project_dir, build_bible(project_dir))
        write_plan(project_dir, build_plan(project_dir))
        write_episode_planning(project_dir, build_episode_planning(project_dir))
        write_script_package(project_dir, build_script_package(project_dir))
        return project_dir

    def test_draft_project_produces_blocking_review_by_category(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            report = audit_story(project_dir)
        codes = [item["code"] for item in report["findings"]]
        self.assertEqual(report["overall_status"], "BLOCKED")
        self.assertIn("SERIES_PLAN_BLOCKED", codes)
        self.assertEqual(codes.count("SCRIPT_NOT_READY"), 5)
        self.assertEqual(codes.count("DELTA_NOT_READY"), 5)
        self.assertEqual(codes.count("CONTINUITY_INPUT_MISSING"), 4)
        self.assertEqual(report["category_status"]["continuity"], "BLOCKED")

    def test_finding_ids_and_order_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            first = audit_story(project_dir)
            second = audit_story(project_dir)
        self.assertEqual([(item["id"], item["code"], item["entity_refs"]) for item in first["findings"]], [(item["id"], item["code"], item["entity_refs"]) for item in second["findings"]])
        self.assertEqual(first["findings"][0]["id"], "FIND-0001")

    def test_report_round_trip_and_blocked_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            write_report(project_dir, audit_story(project_dir))
            loaded = load_report(project_dir)
            result = summary(project_dir)
            with self.assertRaisesRegex(NovelStoryReviewError, "only a PASS"):
                approve_report(project_dir, "reviewer", "not ready")
        self.assertEqual(loaded["human_review"]["status"], "PENDING")
        self.assertEqual(result["blocker_count"], len(loaded["findings"]))

    def test_upstream_revision_makes_saved_review_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            write_report(project_dir, audit_story(project_dir))
            planning = load_episode_planning(project_dir)
            planning["revision"] += 1
            planning["updated_at"] = "2026-09-16T01:00:00Z"
            write_episode_planning(project_dir, planning, overwrite=True)
            with self.assertRaisesRegex(NovelStoryReviewError, "stale"):
                approve_report(project_dir, "reviewer", "stale")


if __name__ == "__main__":
    unittest.main()
