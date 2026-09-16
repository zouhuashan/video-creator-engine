import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_animatic import build_animatic, write_animatic
from scripts.novel_animatic_review import build_review as build_animatic_review, write_review as write_animatic_review
from scripts.novel_asset_review import build_asset_review, write_asset_review
from scripts.novel_audio_assets import build_audio_assets, write_audio_assets
from scripts.novel_audio_mix import build_audio_mix, write_audio_mix
from scripts.novel_dynamic_shots import build_dynamic_shots, write_dynamic_shots
from scripts.novel_edit_timelines import build_edit_timelines, write_edit_timelines
from scripts.novel_environment_assets import build_environment_assets, write_environment_assets
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, write_script_package
from scripts.novel_qc import build_qc_report, write_qc_report
from scripts.novel_acceptance import NovelAcceptanceError, build_acceptance, validate_acceptance, write_acceptance
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_shot_breakdown import build_shot_breakdown, write_shot_breakdown
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible
from scripts.novel_story_review import audit_story, write_report as write_story_review
from scripts.novel_storyboard import build_storyboard, write_storyboard
from scripts.novel_visual_bible import build_visual_bible, write_visual_bible
from scripts.novel_voice_profiles import build_voice_profiles, write_voice_profiles


class NovelAcceptanceTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        project = root / "project-test"
        write_project(project, build_project("project-test", "TST", "测试故事")); write_catalog(project, build_catalog("project-test", "IP-TST", "测试故事")); write_bible(project, build_bible(project)); write_plan(project, build_plan(project)); write_episode_planning(project, build_episode_planning(project)); write_script_package(project, build_script_package(project)); write_story_review(project, audit_story(project)); write_visual_bible(project, build_visual_bible(project)); NovelAnimeRepository(project).initialize(); write_environment_assets(project, build_environment_assets(project)); write_asset_review(project, build_asset_review(project)); write_shot_breakdown(project, build_shot_breakdown(project)); write_storyboard(project, build_storyboard(project)); write_animatic(project, build_animatic(project)); write_animatic_review(project, build_animatic_review(project)); write_voice_profiles(project, build_voice_profiles(project)); write_audio_assets(project, build_audio_assets(project)); write_audio_mix(project, build_audio_mix(project)); write_dynamic_shots(project, build_dynamic_shots(project)); write_edit_timelines(project, build_edit_timelines(project)); write_qc_report(project, build_qc_report(project))
        return project

    def test_acceptance_holds_empty_five_episode_project(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory)); report = build_acceptance(project); output = write_acceptance(project, report)
            self.assertTrue(output.is_file())
            self.assertEqual(report["decision"], "HOLD"); self.assertEqual(len(report["episodes"]), 5); self.assertEqual(len(report["motion_tests"]), 3); self.assertTrue(report["legacy_reference"]["reference_only"])

    def test_acceptance_rejects_stale_qc_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory)); report = build_acceptance(project); report["input_revisions"]["qc"] += 1
            with self.assertRaisesRegex(NovelAcceptanceError, "upstream revisions"):
                validate_acceptance(project, report)


if __name__ == "__main__":
    unittest.main()
