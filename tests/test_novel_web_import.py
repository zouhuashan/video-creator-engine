import json
import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import load_project
from scripts.novel_source_catalog import load_catalog
from scripts.novel_web_import import create_project_from_web_upload


SOURCE = """第一章 初见
少年推开山门。
第二章 夜雨
少女站在雨中。
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

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["import"]["chapter_count"], 2)
            self.assertFalse(result["full_text_stored"])
            self.assertTrue(result["script_adaptation_allowed"])
            self.assertFalse(result["publication_allowed"])
            self.assertEqual(catalog["status"], "LICENSED")
            self.assertTrue(catalog["adaptation_policy"]["script_adaptation_allowed"])
            self.assertFalse(catalog["adaptation_policy"]["publication_allowed"])
            self.assertEqual(len(catalog["chapters"]), 2)
            self.assertEqual(manifest["ip"]["source_edition_ids"], [catalog["editions"][0]["id"]])
            self.assertTrue((project / "story-bible" / "world.json").is_file())
            self.assertTrue((project / "series-plan.json").is_file())
            self.assertFalse((project / ".videocreator" / "upload-tmp").exists())

            import_payload = json.loads((project / result["import"]["output"]).read_text(encoding="utf-8"))
            self.assertEqual(import_payload["source_file_name"], "测试新小说.txt")
            self.assertFalse(import_payload["full_text_stored"])
            self.assertNotIn("少年推开山门", json.dumps(import_payload, ensure_ascii=False))

    def test_technical_test_upload_does_not_unlock_script_adaptation(self):
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

            self.assertTrue(result["import"]["test_only"])
            self.assertFalse(result["script_adaptation_allowed"])
            self.assertEqual(catalog["status"], "UNASSESSED")
            self.assertFalse(catalog["adaptation_policy"]["script_adaptation_allowed"])
            self.assertEqual(catalog["chapters"], [])
            self.assertFalse((project / ".videocreator" / "upload-tmp").exists())


if __name__ == "__main__":
    unittest.main()
