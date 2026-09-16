import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_character_designs import NovelCharacterDesignError, build_character_designs, check_identity_observation, identity_signature, summary, validate_character_designs, write_character_designs
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, write_script_package
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible
from scripts.novel_story_review import audit_story, write_report
from scripts.novel_visual_bible import build_visual_bible, write_visual_bible


def pending():
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def approved():
    return {"required": True, "status": "APPROVED", "reviewed_at": "2026-09-16T00:00:00Z", "reviewed_by": "reviewer", "note": "test"}


def original():
    return {"kind": "ORIGINAL", "source_refs": [], "note": "测试原创"}


class NovelCharacterDesignTests(unittest.TestCase):
    def make_project(self, root: Path) -> tuple[Path, str]:
        project_dir = root / "project-test"
        write_project(project_dir, build_project("project-test", "TST", "测试故事"))
        write_catalog(project_dir, build_catalog("project-test", "IP-TST", "测试故事"))
        bible = build_bible(project_dir)
        bible["characters"] = [{"id": "CHR-TST-HERO", "name": "主角", "aliases": [], "role": "protagonist", "description": "旅人", "goals": [], "traits": [], "baseline_state": {"location_id": None, "costume_id": None, "carried_prop_ids": [], "injuries": [], "knowledge": [], "emotional_state": ""}, "provenance": original(), "human_review": pending()}]
        write_bible(project_dir, bible)
        write_plan(project_dir, build_plan(project_dir))
        write_episode_planning(project_dir, build_episode_planning(project_dir))
        write_script_package(project_dir, build_script_package(project_dir))
        write_report(project_dir, audit_story(project_dir))
        visual = build_visual_bible(project_dir)
        visual["color_script"]["swatches"] = [{"id": "COLOR-TST-INK", "name": "墨色", "hex": "#20252B", "role": "轮廓"}]
        write_visual_bible(project_dir, visual)
        repository = NovelAnimeRepository(project_dir)
        repository.initialize()
        asset_file = project_dir / "assets" / "characters" / "hero" / "identity-sheet.png"
        asset_file.parent.mkdir(parents=True)
        asset_file.write_bytes(b"test-character-sheet")
        asset_id = "AST-CHR-TST-HERO-SHEET"
        repository.register_asset(asset_id, "character", asset_file, source_entity_ids=["IP-TST"])
        return project_dir, asset_id

    def ready_package(self, project_dir: Path, asset_id: str):
        package = build_character_designs(project_dir)
        design = package["character_designs"][0]
        design["identity"] = {"height_heads": 7.0, "body_type": "修长", "face_shape": "鹅蛋脸", "skin_tone": "暖白", "hair_shape": "高束长发", "hair_color": "墨黑", "eye_shape": "杏眼", "eye_color": "深褐", "distinguishing_marks": ["右眉尾小痣"], "immutable_features": ["高束长发", "右眉尾小痣"], "negative_constraints": ["不得改变脸型", "不得改变发际线"]}
        signature = identity_signature(design["identity"])
        design.update({"status": "READY", "identity_signature": signature, "palette_swatch_ids": ["COLOR-TST-INK"], "default_costume_id": "COSTUME-TST-HERO-DEFAULT", "prompt_template": {"positive": "统一角色脸型、发型、比例", "negative": "identity drift, different face"}, "human_review": approved()})
        for item in design["turnarounds"]:
            item.update({"status": "SELECTED", "asset_id": asset_id, "identity_signature": signature})
        for item in design["expressions"]:
            item.update({"status": "SELECTED", "asset_id": asset_id, "identity_signature": signature})
        design["costumes"] = [{"id": "COSTUME-TST-HERO-DEFAULT", "name": "常服", "is_default": True, "usage": "日常旅程", "layers": ["中衣", "外袍"], "palette_swatch_ids": ["COLOR-TST-INK"], "accessories": ["发带"], "status": "SELECTED", "asset_id": asset_id, "identity_signature": signature, "continuity_note": "默认服装，换装必须记录 delta"}]
        return package

    def test_skeleton_covers_every_story_character(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, _ = self.make_project(Path(directory))
            package = build_character_designs(project_dir)
            write_character_designs(project_dir, package)
            result = summary(project_dir)
        self.assertEqual(package["character_designs"][0]["character_id"], "CHR-TST-HERO")
        self.assertEqual({item["view"] for item in package["character_designs"][0]["turnarounds"]}, {"FRONT", "THREE_QUARTER", "SIDE", "BACK", "CLOSEUP"})
        self.assertEqual(result["character_count"], 1)

    def test_ready_identity_contract_with_registered_sheet_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, asset_id = self.make_project(Path(directory))
            package = validate_character_designs(project_dir, self.ready_package(project_dir, asset_id))
        self.assertEqual(package["character_designs"][0]["status"], "READY")
        self.assertEqual(package["character_designs"][0]["default_costume_id"], "COSTUME-TST-HERO-DEFAULT")

    def test_identity_signature_and_registered_asset_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, asset_id = self.make_project(Path(directory))
            package = self.ready_package(project_dir, asset_id)
            package["character_designs"][0]["identity"]["hair_color"] = "银白"
            with self.assertRaisesRegex(NovelCharacterDesignError, "signature drift"):
                validate_character_designs(project_dir, package)
            package = self.ready_package(project_dir, asset_id)
            package["character_designs"][0]["turnarounds"][0]["asset_id"] = "AST-MISSING"
            with self.assertRaisesRegex(NovelCharacterDesignError, "registered asset"):
                validate_character_designs(project_dir, package)

    def test_identity_observation_reports_exact_drift_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, asset_id = self.make_project(Path(directory))
            design = self.ready_package(project_dir, asset_id)["character_designs"][0]
            observation = {**{key: design["identity"][key] for key in ("height_heads", "body_type", "face_shape", "skin_tone", "hair_shape", "hair_color", "eye_shape", "eye_color", "distinguishing_marks")}}
            passing = check_identity_observation(design, observation)
            observation["face_shape"] = "圆脸"
            observation["height_heads"] = 6.2
            failing = check_identity_observation(design, observation)
        self.assertTrue(passing["pass"])
        self.assertFalse(failing["pass"])
        self.assertEqual({item["field"] for item in failing["issues"]}, {"face_shape", "height_heads"})

    def test_default_costume_must_be_unique_and_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, asset_id = self.make_project(Path(directory))
            package = self.ready_package(project_dir, asset_id)
            package["character_designs"][0]["costumes"][0]["is_default"] = False
            with self.assertRaisesRegex(NovelCharacterDesignError, "default costume"):
                validate_character_designs(project_dir, package)


if __name__ == "__main__":
    unittest.main()
