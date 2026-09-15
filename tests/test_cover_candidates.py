import copy
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.cover_candidates import CoverError, create_cover_candidates, select_cover


class CoverCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project_id = "20260915-cover-test"
        self.directory = Path(self.temp.name) / self.project_id
        self.directory.mkdir()
        self.payload = {"schema_version": 1, "project_id": self.project_id, "candidates": [
            {"candidate_id": "COVER_A", "core_text": "到底值不值", "supporting_text": "一分钟说清楚", "background": "#10131A", "foreground": "#FFFFFF", "accent": "#35E08D"},
            {"candidate_id": "COVER_B", "core_text": "该不该买？", "supporting_text": "先看这三个条件", "background": "#F2F0E9", "foreground": "#111111", "accent": "#E14B31"},
        ]}

    def tearDown(self):
        self.temp.cleanup()

    def test_renders_two_mobile_cover_candidates_and_manifest(self):
        result = create_cover_candidates(self.directory, self.payload)
        self.assertEqual(len(result["candidates"]), 2)
        for candidate in result["candidates"]:
            with Image.open(self.directory / "covers" / candidate["file"]) as image:
                self.assertEqual(image.size, (1080, 1920))
            self.assertGreaterEqual(candidate["core_font_size"], 120)

    def test_selects_verified_candidate_as_final_cover(self):
        create_cover_candidates(self.directory, self.payload)
        result = select_cover(self.directory, "COVER_B")
        self.assertEqual(result["status"], "PASS")
        self.assertTrue((self.directory / "cover.png").is_file())
        with Image.open(self.directory / "cover.png") as image:
            self.assertEqual(image.size, (1080, 1920))

    def test_rejects_too_short_long_or_non_question_core_text(self):
        for text, message in (("值吗", "3-10"), ("这个产品到底是不是值得所有人购买", "3-10"), ("产品真实体验", "question")):
            payload = copy.deepcopy(self.payload)
            payload["candidates"][0]["core_text"] = text
            with self.assertRaisesRegex(CoverError, message):
                create_cover_candidates(self.directory, payload)

    def test_rejects_dense_supporting_text_and_candidate_count(self):
        payload = copy.deepcopy(self.payload)
        payload["candidates"][0]["supporting_text"] = "这是一行远远超过移动端阅读限制的辅助说明文字"
        with self.assertRaisesRegex(CoverError, "one short line"):
            create_cover_candidates(self.directory, payload)
        payload = copy.deepcopy(self.payload)
        payload["candidates"] = payload["candidates"][:1]
        with self.assertRaisesRegex(CoverError, "2-3"):
            create_cover_candidates(self.directory, payload)


if __name__ == "__main__":
    unittest.main()
