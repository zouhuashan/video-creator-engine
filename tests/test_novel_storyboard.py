import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_asset_review import build_asset_review, write_asset_review
from scripts.novel_environment_assets import build_environment_assets, write_environment_assets
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, write_script_package
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_shot_breakdown import build_shot_breakdown, write_shot_breakdown
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible
from scripts.novel_storyboard import NovelStoryboardError, build_storyboard, validate_storyboard, write_storyboard
from scripts.novel_visual_bible import build_visual_bible, write_visual_bible


class NovelStoryboardTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        project = root / "project-test"
        write_project(project, build_project("project-test", "TST", "测试故事")); write_catalog(project, build_catalog("project-test", "IP-TST", "测试故事")); write_bible(project, build_bible(project)); write_plan(project, build_plan(project)); write_episode_planning(project, build_episode_planning(project)); write_script_package(project, build_script_package(project)); write_visual_bible(project, build_visual_bible(project)); NovelAnimeRepository(project).initialize(); write_environment_assets(project, build_environment_assets(project)); write_asset_review(project, build_asset_review(project)); write_shot_breakdown(project, build_shot_breakdown(project))
        return project

    def test_empty_shot_breakdown_creates_zero_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory)); package = build_storyboard(project); output = write_storyboard(project, package); self.assertTrue(output.is_file())
        self.assertEqual(package["frames"], [])

    def test_shot_breakdown_revision_drift_blocks_storyboard(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory)); package = build_storyboard(project); package["shot_breakdown_revision"] += 1
            with self.assertRaisesRegex(NovelStoryboardError, "upstream revisions"):
                validate_storyboard(project, package)


if __name__ == "__main__": unittest.main()
