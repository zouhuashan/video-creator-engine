import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_animatic import build_animatic, write_animatic
from scripts.novel_animatic_review import NovelAnimaticReviewError, build_review, validate_review, write_review
from scripts.novel_asset_review import build_asset_review, write_asset_review
from scripts.novel_environment_assets import build_environment_assets, write_environment_assets
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, write_script_package
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_shot_breakdown import build_shot_breakdown, write_shot_breakdown
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible
from scripts.novel_storyboard import build_storyboard, write_storyboard
from scripts.novel_visual_bible import build_visual_bible, write_visual_bible


class NovelAnimaticReviewTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        project = root / "project-test"
        write_project(project, build_project("project-test", "TST", "测试故事")); write_catalog(project, build_catalog("project-test", "IP-TST", "测试故事")); write_bible(project, build_bible(project)); write_plan(project, build_plan(project)); write_episode_planning(project, build_episode_planning(project)); write_script_package(project, build_script_package(project)); write_visual_bible(project, build_visual_bible(project)); NovelAnimeRepository(project).initialize(); write_environment_assets(project, build_environment_assets(project)); write_asset_review(project, build_asset_review(project)); write_shot_breakdown(project, build_shot_breakdown(project)); write_storyboard(project, build_storyboard(project)); write_animatic(project, build_animatic(project))
        return project

    def test_empty_animatic_is_blocked_with_deterministic_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory)); report = build_review(project); write_review(project, report)
        self.assertEqual(report["overall_status"], "BLOCKED"); self.assertGreaterEqual(len(report["findings"]), 1)

    def test_upstream_revision_drift_blocks_review(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory)); report = build_review(project); report["animatic_revision"] += 1
            with self.assertRaisesRegex(NovelAnimaticReviewError, "upstream revisions"):
                validate_review(project, report)


if __name__ == "__main__": unittest.main()
