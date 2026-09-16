import json
import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import (
    NovelAnimeProjectError,
    SCHEMA_PATH,
    build_project,
    load_project,
    validate_project,
    write_project,
)


class NovelAnimeProjectTests(unittest.TestCase):
    def test_builds_one_season_with_five_stable_episode_ids(self):
        project = build_project("jinghua-yuan-series", "JHY", "镜花缘", episode_count=5)
        self.assertEqual(project["ip"]["id"], "IP-JHY")
        self.assertEqual(project["series"]["id"], "SER-JHY-01")
        self.assertEqual(project["seasons"][0]["id"], "S01")
        self.assertEqual([episode["id"] for episode in project["episodes"]], [f"S01E{index:03d}" for index in range(1, 6)])
        self.assertEqual(project["seasons"][0]["episode_ids"], [episode["id"] for episode in project["episodes"]])
        self.assertFalse(project["ip"]["publication_allowed"])

    def test_rejects_duplicate_ids_and_unknown_relationships(self):
        duplicate = build_project("test-series", "TEST", "测试")
        duplicate["episodes"][1]["id"] = duplicate["episodes"][0]["id"]
        with self.assertRaisesRegex(NovelAnimeProjectError, "duplicate entity ID"):
            validate_project(duplicate)

        unknown = build_project("test-series", "TEST", "测试")
        unknown["seasons"][0]["episode_ids"].append("S01E999")
        with self.assertRaisesRegex(NovelAnimeProjectError, "unknown reference"):
            validate_project(unknown)

    def test_rejects_scene_or_shot_outside_parent_scope(self):
        project = build_project("test-series", "TEST", "测试", episode_count=1)
        common = {"revision": 1, "status": "DRAFT", "input_refs": [], "source_refs": [], "provider": None, "human_review": {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None}}
        project["episodes"][0]["scene_ids"] = ["S01E001-SC001"]
        project["scenes"] = [{"id": "S01E001-SC001", "title": "测试场", **common, "episode_id": "S01E001", "scene_number": 1, "location_ref": None, "character_refs": [], "shot_ids": ["S01E001-SC001-SH001"]}]
        project["shots"] = [{"id": "S01E001-SC001-SH001", "title": "测试镜头", **common, "scene_id": "S01E001-SC001", "shot_number": 1, "duration_seconds": 3.0, "asset_refs": [], "render_strategy": "local_animatic"}]
        self.assertEqual(validate_project(project)["shots"][0]["id"], "S01E001-SC001-SH001")
        project["shots"][0]["scene_id"] = "S01E001-SC999"
        with self.assertRaisesRegex(NovelAnimeProjectError, "unknown reference"):
            validate_project(project)

    def test_manifest_round_trip_and_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory) / "series"
            output = write_project(project_dir, build_project("test-series", "TEST", "测试"))
            self.assertEqual(load_project(output)["project_id"], "test-series")
            with self.assertRaisesRegex(NovelAnimeProjectError, "refusing to overwrite"):
                write_project(project_dir, build_project("test-series", "TEST", "测试"))

    def test_json_schema_declares_every_core_entity(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        expected = {"ip", "source_edition", "series", "season", "arc", "episode", "scene", "shot", "asset", "render"}
        self.assertTrue(expected.issubset(schema["$defs"]))
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)


if __name__ == "__main__":
    unittest.main()
