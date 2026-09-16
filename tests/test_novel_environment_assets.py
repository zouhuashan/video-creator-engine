import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_environment_assets import (
    NovelEnvironmentAssetError,
    build_environment_assets,
    continuity_signature,
    summary,
    validate_environment_assets,
    write_environment_assets,
)
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, write_script_package
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible
from scripts.novel_visual_bible import build_visual_bible, write_visual_bible


def original():
    return {"kind": "ORIGINAL", "source_refs": [], "note": "测试原创"}


def script_original():
    return {"kind": "ORIGINAL", "source_refs": [], "story_refs": [], "note": "测试原创"}


def pending():
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


class NovelEnvironmentAssetTests(unittest.TestCase):
    def make_project(self, root: Path) -> tuple[Path, str, str]:
        project_dir = root / "project-test"
        write_project(project_dir, build_project("project-test", "TST", "测试故事"))
        write_catalog(project_dir, build_catalog("project-test", "IP-TST", "测试故事"))
        bible = build_bible(project_dir)
        bible["locations"] = [{"id": "LOCN-TST-HARBOR", "name": "海港", "description": "出发地", "region": "东岸", "visual_traits": ["木船"], "provenance": original(), "human_review": pending()}]
        bible["characters"] = [{"id": "CHR-TST-HERO", "name": "主角", "aliases": [], "role": "protagonist", "description": "旅人", "goals": [], "traits": [], "baseline_state": {"location_id": "LOCN-TST-HARBOR", "costume_id": None, "carried_prop_ids": ["PROP-TST-COMPASS"], "injuries": [], "knowledge": [], "emotional_state": ""}, "provenance": original(), "human_review": pending()}]
        bible["props"] = [{"id": "PROP-TST-COMPASS", "name": "罗盘", "description": "导航", "owner_character_id": "CHR-TST-HERO", "home_location_id": None, "story_function": "引路", "provenance": original(), "human_review": pending()}]
        write_bible(project_dir, bible)
        write_plan(project_dir, build_plan(project_dir))
        write_episode_planning(project_dir, build_episode_planning(project_dir))
        scripts = build_script_package(project_dir)
        scripts["episode_scripts"][0]["scenes"] = [{
            "id": "S01E001-SC001", "sequence": 1, "title": "启程", "purpose": "建立旅程",
            "location_id": "LOCN-TST-HARBOR", "time_of_day": "清晨", "character_ids": ["CHR-TST-HERO"],
            "units": [{"id": "UNIT-S01E001-SC001-001", "sequence": 1, "kind": "ACTION", "text": "主角握紧罗盘。", "speaker_character_id": None, "emotion": None, "sound": None, "estimated_duration_seconds": 2, "beat_ref": None, "provenance": script_original()}],
            "provenance": script_original(), "human_review": pending(),
        }]
        write_script_package(project_dir, scripts)
        visual = build_visual_bible(project_dir)
        visual["color_script"]["swatches"] = [{"id": "COLOR-TST-INK", "name": "墨色", "hex": "#20252B", "role": "轮廓"}]
        write_visual_bible(project_dir, visual)
        repository = NovelAnimeRepository(project_dir)
        repository.initialize()
        location_file = project_dir / "assets" / "locations" / "harbor.png"
        prop_file = project_dir / "assets" / "props" / "compass.png"
        location_file.parent.mkdir(parents=True); prop_file.parent.mkdir(parents=True)
        location_file.write_bytes(b"location"); prop_file.write_bytes(b"prop")
        location_asset = "AST-LOCN-TST-HARBOR-SHEET"; prop_asset = "AST-PROP-TST-COMPASS-SHEET"
        repository.register_asset(location_asset, "location", location_file, source_entity_ids=["IP-TST"])
        repository.register_asset(prop_asset, "prop", prop_file, source_entity_ids=["IP-TST"])
        return project_dir, location_asset, prop_asset

    def ready_package(self, project_dir: Path, location_asset: str, prop_asset: str):
        package = build_environment_assets(project_dir)
        location = package["location_designs"][0]
        location["layout"] = {"orientation": "港口朝东", "scale": "中型码头", "zones": ["栈桥", "市集"], "entrances": ["西门"], "fixed_landmarks": ["红色灯塔"]}
        signature = continuity_signature(location["layout"])
        location.update({"status": "READY", "visual_language": "水墨海港", "base_palette_swatch_ids": ["COLOR-TST-INK"], "continuity_signature": signature, "prompt_template": {"positive": "固定灯塔与栈桥方位", "negative": "不得镜像地标"}})
        location["camera_views"] = [{"id": "CAMVIEW-TST-HARBOR-WIDE", "name": "港口全景", "description": "向东看海", "status": "SELECTED", "asset_id": location_asset, "continuity_signature": signature}]
        location["variants"] = [{"id": "LVAR-TST-HARBOR-DAWN-CLEAR", "weather": "晴", "time_of_day": "清晨", "lighting": "冷色侧逆光", "season": "春", "palette_swatch_ids": ["COLOR-TST-INK"], "status": "SELECTED", "asset_id": location_asset, "continuity_signature": signature, "continuity_note": "首集启程版本"}]
        prop = package["prop_designs"][0]
        identity = {"dimensions": "直径十五厘米", "materials": ["黄铜"], "distinctive_marks": ["缺口指针"], "interaction_rules": ["指针始终朝向海外"]}
        prop_signature = continuity_signature(identity)
        prop.update({**identity, "status": "READY", "palette_swatch_ids": ["COLOR-TST-INK"], "continuity_signature": prop_signature, "default_state_id": "PSTATE-TST-COMPASS-INTACT", "prompt_template": {"positive": "固定缺口指针", "negative": "不得改变材质"}})
        prop["states"] = [{"id": "PSTATE-TST-COMPASS-INTACT", "condition": "完好", "holder_character_id": "CHR-TST-HERO", "location_id": None, "status": "SELECTED", "asset_id": prop_asset, "continuity_signature": prop_signature, "continuity_note": "主角手持"}]
        package["scene_environment_assignments"][0].update({"location_variant_id": "LVAR-TST-HARBOR-DAWN-CLEAR", "weather": "晴", "lighting": "冷色侧逆光", "prop_state_ids": ["PSTATE-TST-COMPASS-INTACT"]})
        return package

    def test_skeleton_covers_locations_props_and_located_scenes(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, _, _ = self.make_project(Path(directory))
            package = build_environment_assets(project_dir)
            write_environment_assets(project_dir, package)
            result = summary(project_dir)
        self.assertEqual([item["location_id"] for item in package["location_designs"]], ["LOCN-TST-HARBOR"])
        self.assertEqual([item["prop_id"] for item in package["prop_designs"]], ["PROP-TST-COMPASS"])
        self.assertEqual(result["scene_assignment_count"], 1)

    def test_ready_variants_and_states_require_registered_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, location_asset, prop_asset = self.make_project(Path(directory))
            package = validate_environment_assets(project_dir, self.ready_package(project_dir, location_asset, prop_asset))
            self.assertEqual(package["location_designs"][0]["status"], "READY")
            package = self.ready_package(project_dir, location_asset, prop_asset)
            package["location_designs"][0]["camera_views"][0]["asset_id"] = "AST-MISSING"
            with self.assertRaisesRegex(NovelEnvironmentAssetError, "registered asset"):
                validate_environment_assets(project_dir, package)

    def test_location_and_prop_signatures_detect_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, location_asset, prop_asset = self.make_project(Path(directory))
            package = self.ready_package(project_dir, location_asset, prop_asset)
            package["location_designs"][0]["layout"]["orientation"] = "港口朝西"
            with self.assertRaisesRegex(NovelEnvironmentAssetError, "signature drift"):
                validate_environment_assets(project_dir, package)

    def test_scene_assignment_must_match_selected_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir, location_asset, prop_asset = self.make_project(Path(directory))
            package = self.ready_package(project_dir, location_asset, prop_asset)
            package["scene_environment_assignments"][0]["weather"] = "暴雨"
            with self.assertRaisesRegex(NovelEnvironmentAssetError, "does not match"):
                validate_environment_assets(project_dir, package)


if __name__ == "__main__":
    unittest.main()
