import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.publication_copy import PublicationCopyError, validate_and_score, write_publication_copy


class PublicationCopyTests(unittest.TestCase):
    def setUp(self):
        self.project_id = "20260915-copy-test"
        self.payload = {"schema_version": 1, "project_id": self.project_id, "topic_keyword": "ChatGPT Plus",
                        "candidates": [
            {"candidate_id": "TITLE_A", "type": "search", "text": "ChatGPT Plus值不值得买"},
            {"candidate_id": "TITLE_B", "type": "conflict", "text": "每月二十美元，到底值不值？"},
            {"candidate_id": "TITLE_C", "type": "result", "text": "实测结论：高频用户更适合"},
        ], "caption": "从价格、使用频率和功能差异三个角度，判断这项订阅是否适合你。先看需求，再决定是否付费。",
           "hashtags": ["#ChatGPT", "#AI工具", "#订阅避坑"]}

    def test_accepts_three_required_types_and_recommends_one(self):
        result = validate_and_score(self.payload)
        self.assertEqual({item["type"] for item in result["candidates"]}, {"search", "conflict", "result"})
        self.assertIn(result["recommended"], {"TITLE_A", "TITLE_B", "TITLE_C"})
        self.assertTrue(result["recommendation_reason"])

    def test_writes_title_caption_hashtags_and_trace_file(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / self.project_id
            directory.mkdir()
            result = write_publication_copy(directory, self.payload)
            self.assertEqual(result["status"], "PASS")
            self.assertIn("搜索型", (directory / "title.md").read_text())
            self.assertIn("最终推荐", (directory / "title.md").read_text())
            self.assertIn("#AI工具", (directory / "hashtags.md").read_text())
            self.assertEqual(json.loads((directory / "publication-copy.json").read_text())["recommended"], result["recommended"])

    def test_rejects_missing_type_and_invalid_type_semantics(self):
        payload = copy.deepcopy(self.payload)
        payload["candidates"][2]["type"] = "conflict"
        payload["candidates"][2]["text"] = "付费还是免费，哪个更适合？"
        with self.assertRaisesRegex(PublicationCopyError, "missing types"):
            validate_and_score(payload)
        payload = copy.deepcopy(self.payload)
        payload["candidates"][1]["text"] = "关于订阅费用的完整说明"
        with self.assertRaisesRegex(PublicationCopyError, "tension"):
            validate_and_score(payload)

    def test_rejects_search_without_keyword_and_unsupported_hype(self):
        payload = copy.deepcopy(self.payload)
        payload["candidates"][0]["text"] = "人工智能订阅值不值得买"
        with self.assertRaisesRegex(PublicationCopyError, "topic keyword"):
            validate_and_score(payload)
        payload = copy.deepcopy(self.payload)
        payload["candidates"][2]["text"] = "实测结论：这是绝对最强选择"
        with self.assertRaisesRegex(PublicationCopyError, "unsupported hype"):
            validate_and_score(payload)

    def test_rejects_invalid_caption_and_hashtags(self):
        payload = copy.deepcopy(self.payload)
        payload["caption"] = "太短"
        with self.assertRaisesRegex(PublicationCopyError, "20-500"):
            validate_and_score(payload)
        payload = copy.deepcopy(self.payload)
        payload["hashtags"] = ["#AI工具", "有 空格", "#视频号"]
        with self.assertRaisesRegex(PublicationCopyError, "begin with"):
            validate_and_score(payload)


if __name__ == "__main__":
    unittest.main()
