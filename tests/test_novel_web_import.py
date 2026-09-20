import json
import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import load_project
from scripts.novel_character_designs import load_character_designs
from scripts.novel_story_bible import load_bible
from scripts.novel_source_catalog import load_catalog
from scripts.novel_web_import import create_project_from_web_upload, recover_project_characters


SOURCE = """第一章 初见
顾临渊推开山门，抬头看见灯火。
顾临渊说道：“今夜先住下。”
苏照雪看向顾临渊，轻声道：“我陪你。”
第二章 夜雨
苏照雪站在雨中，顾临渊走出屋檐。
顾临渊问道：“你为何还在这里？”
苏照雪答道：“灯还没有灭。”
"""


class NovelWebImportTests(unittest.TestCase):
    def test_owned_or_licensed_upload_creates_full_project_scaffold_without_persisting_source_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = create_project_from_web_upload(
                root,
                title="测试新小说",
                author="测试作者",
                episode_count=5,
                rights_mode="OWNED_OR_LICENSED",
                rights_confirmed=True,
                source_name="测试新小说.txt",
                source_text=SOURCE,
            )
            project = root / result["directory_id"]
            catalog = load_catalog(project / "sources" / "source-catalog.json")
            manifest = load_project(project / "novel-anime-project.json")
            bible = load_bible(project)
            designs = load_character_designs(project)

            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["reused_existing"])
            self.assertEqual(result["import"]["chapter_count"], 2)
            self.assertGreaterEqual(result["character_count"], 2)
            self.assertFalse(result["full_text_stored"])
            self.assertTrue(result["script_adaptation_allowed"])
            self.assertFalse(result["publication_allowed"])
            self.assertEqual(catalog["status"], "LICENSED")
            self.assertTrue(catalog["adaptation_policy"]["script_adaptation_allowed"])
            self.assertFalse(catalog["adaptation_policy"]["publication_allowed"])
            self.assertEqual(len(catalog["chapters"]), 2)
            self.assertEqual(manifest["ip"]["source_edition_ids"], [catalog["editions"][0]["id"]])
            self.assertGreaterEqual(len(bible["characters"]), 2)
            self.assertEqual(
                {item["character_id"] for item in designs["character_designs"]},
                {item["id"] for item in bible["characters"]},
            )
            self.assertTrue((project / "story-bible" / "world.json").is_file())
            self.assertTrue((project / "story-bible" / "image-studio-character-candidates.json").is_file())
            self.assertTrue((project / "writing-room" / "series-plan.json").is_file())
            self.assertFalse((project / ".videocreator" / "upload-tmp").exists())

            import_payload = json.loads((project / result["import"]["output"]).read_text(encoding="utf-8"))
            self.assertEqual(import_payload["source_file_name"], "测试新小说.txt")
            self.assertFalse(import_payload["full_text_stored"])
            self.assertNotIn("今夜先住下", json.dumps(import_payload, ensure_ascii=False))

    def test_identical_web_import_is_idempotent_and_reuses_existing_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = dict(
                title="照骨灯",
                author="测试作者",
                episode_count=5,
                rights_mode="OWNED_OR_LICENSED",
                rights_confirmed=True,
                source_name="照骨灯.txt",
                source_text=SOURCE,
            )
            first = create_project_from_web_upload(root, **args)
            second = create_project_from_web_upload(root, **args)

            self.assertFalse(first["reused_existing"])
            self.assertTrue(second["reused_existing"])
            self.assertEqual(second["directory_id"], first["directory_id"])
            self.assertEqual(len(list(root.glob("*/novel-anime-project.json"))), 1)
            self.assertGreaterEqual(second["character_count"], 2)

    def test_technical_test_upload_keeps_publication_locked_but_builds_project_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = create_project_from_web_upload(
                root,
                title="测试技术样片",
                author="",
                episode_count=3,
                rights_mode="TECHNICAL_TEST",
                rights_confirmed=False,
                source_name="sample.txt",
                source_text=SOURCE,
            )
            project = root / result["directory_id"]
            catalog = load_catalog(project / "sources" / "source-catalog.json")
            bible = load_bible(project)

            self.assertTrue(result["import"]["test_only"])
            self.assertFalse(result["script_adaptation_allowed"])
            self.assertEqual(catalog["status"], "UNASSESSED")
            self.assertFalse(catalog["adaptation_policy"]["script_adaptation_allowed"])
            self.assertEqual(catalog["chapters"], [])
            self.assertGreaterEqual(len(bible["characters"]), 2)
            self.assertTrue(all(item["provenance"]["kind"] == "SOURCE" for item in bible["characters"]))
            self.assertFalse((project / ".videocreator" / "upload-tmp").exists())

    def test_old_empty_story_bible_recovers_from_persisted_character_candidates_without_source_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = create_project_from_web_upload(
                root,
                title="恢复测试",
                author="",
                episode_count=3,
                rights_mode="TECHNICAL_TEST",
                rights_confirmed=False,
                source_name="recover.txt",
                source_text=SOURCE,
            )
            project = root / result["directory_id"]

            # Simulate the old P31 bug: Story Bible and derived Character Designs
            # exist but contain no characters, while persisted extraction/candidate
            # metadata is still present and the source prose is not.
            bible = load_bible(project)
            bible["characters"] = []
            bible["revision"] += 1
            from scripts.novel_story_bible import write_bible
            write_bible(project, bible, overwrite=True)

            recovery = recover_project_characters(project)
            repaired = load_bible(project)
            repaired_designs = load_character_designs(project)
            self.assertEqual(recovery["status"], "READY")
            self.assertTrue(recovery["promoted"])
            self.assertGreaterEqual(len(repaired["characters"]), 2)
            self.assertEqual(len(repaired_designs["character_designs"]), len(repaired["characters"]))


if __name__ == "__main__":
    unittest.main()
