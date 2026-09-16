import tempfile
import unittest
from pathlib import Path
from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_animatic import build_animatic, write_animatic
from scripts.novel_asset_review import build_asset_review, write_asset_review
from scripts.novel_audio_assets import build_audio_assets, write_audio_assets
from scripts.novel_audio_mix import NovelAudioMixError, build_audio_mix, validate_audio_mix, write_audio_mix
from scripts.novel_environment_assets import build_environment_assets, write_environment_assets
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, write_script_package
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_shot_breakdown import build_shot_breakdown, write_shot_breakdown
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible
from scripts.novel_storyboard import build_storyboard, write_storyboard
from scripts.novel_visual_bible import build_visual_bible, write_visual_bible
from scripts.novel_voice_profiles import build_voice_profiles, write_voice_profiles

class NovelAudioMixTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        project = root / "project-test"; write_project(project, build_project("project-test", "TST", "测试故事")); write_catalog(project, build_catalog("project-test", "IP-TST", "测试故事")); write_bible(project, build_bible(project)); write_plan(project, build_plan(project)); write_episode_planning(project, build_episode_planning(project)); write_script_package(project, build_script_package(project)); write_visual_bible(project, build_visual_bible(project)); NovelAnimeRepository(project).initialize(); write_environment_assets(project, build_environment_assets(project)); write_asset_review(project, build_asset_review(project)); write_shot_breakdown(project, build_shot_breakdown(project)); write_storyboard(project, build_storyboard(project)); write_animatic(project, build_animatic(project)); write_voice_profiles(project, build_voice_profiles(project)); write_audio_assets(project, build_audio_assets(project)); return project
    def test_mix_plan_covers_five_episodes_and_defaults_loudness(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory)); package = build_audio_mix(project); output = write_audio_mix(project, package); self.assertTrue(output.is_file())
        self.assertEqual(len(package["episodes"]), 5); self.assertEqual(package["episodes"][0]["target_lufs"], -16.0)
    def test_sync_offset_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory)); package = build_audio_mix(project); package["episodes"][0]["sync_offset_ms"] = 101
            with self.assertRaisesRegex(NovelAudioMixError, "exceeds 100ms"): validate_audio_mix(project, package)
if __name__ == "__main__": unittest.main()
