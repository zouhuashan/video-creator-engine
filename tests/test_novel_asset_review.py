import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_asset_review import NovelAssetReviewError, build_asset_review, readiness, validate_asset_review, write_asset_review
from scripts.novel_environment_assets import build_environment_assets, write_environment_assets
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, write_script_package
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible
from scripts.novel_visual_bible import build_visual_bible, write_visual_bible


class NovelAssetReviewTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        project = root / "project-test"
        write_project(project, build_project("project-test", "TST", "测试故事"))
        write_catalog(project, build_catalog("project-test", "IP-TST", "测试故事"))
        write_bible(project, build_bible(project))
        write_plan(project, build_plan(project)); write_episode_planning(project, build_episode_planning(project)); write_script_package(project, build_script_package(project))
        write_visual_bible(project, build_visual_bible(project)); write_environment_assets(project, build_environment_assets(project))
        NovelAnimeRepository(project).initialize()
        return project

    def test_empty_reference_package_is_valid_but_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory)); package = build_asset_review(project); write_asset_review(project, package)
            self.assertEqual(package["reference_packages"], [])
            self.assertFalse(readiness(project)["ready"])

    def test_selected_reference_requires_current_registered_version(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory)); asset = project / "assets" / "keyframe.png"; asset.parent.mkdir(parents=True); asset.write_bytes(b"frame")
            NovelAnimeRepository(project).register_asset("AST-KEYFRAME-TST-001", "keyframe", asset, source_entity_ids=["IP-TST"])
            package = build_asset_review(project); review = package["art_reviews"][0] if package["art_reviews"] else {"id": "ARTREV-REFE-REFPACK-TST", "target_type": "REFERENCE_PACKAGE", "target_id": "REFPACK-TST", "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": "", "blocking_findings": []}
            package["reference_packages"] = [{"id": "REFPACK-TST", "entity_id": "IP-TST", "entity_type": "episode", "purpose": "测试关键帧", "references": [{"id": "REF-KEYFRAME-TST", "view": "KEYFRAME", "asset_id": "AST-KEYFRAME-TST-001", "version": 1, "role": "KEYFRAME", "status": "SELECTED", "continuity_signature": "a" * 64}], "selected_reference_ids": ["REF-KEYFRAME-TST"], "human_review": {**review, "id": "ARTREV-REFE-REFPACK-TST", "target_id": "REFPACK-TST"}}]
            package["art_reviews"] = [package["reference_packages"][0]["human_review"]]
            package["selection_records"] = [{"id": "ASSEL-KEYFRAME-TST", "reference_id": "REF-KEYFRAME-TST", "asset_id": "AST-KEYFRAME-TST-001", "version": 1, "selected_at": "2026-09-16T00:00:00Z", "selected_by": "tester", "reason": "清晰", "status": "SELECTED"}]
            validate_asset_review(project, package)
            package["selection_records"][0]["version"] = 2
            with self.assertRaisesRegex(NovelAssetReviewError, "does not match"):
                validate_asset_review(project, package)

    def test_write_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory)); output = write_asset_review(project, build_asset_review(project)); self.assertTrue(output.is_file())


if __name__ == "__main__": unittest.main()
