import json
import tempfile
import unittest
from pathlib import Path

from scripts import project_state
from scripts.storyboard_review import review_storyboard, write_storyboard_review


class StoryboardReviewTests(unittest.TestCase):
    def setUp(self):
        self.script = {
            "sections": [
                {"section": "hook", "narration": "别买。", "source_ids": []},
                {"section": "evidence", "narration": "官方说明。", "source_ids": ["S001"]},
                {"section": "conclusion", "narration": "按需决定。", "source_ids": []},
            ]
        }
        self.storyboard = {
            "scenes": [
                self.scene("SC001", 0, 3, "别买。", "别买", "价格标签被划掉", "screenshot", []),
                self.scene("SC002", 3, 10, "", "价格", "价格页全景", "screenshot", []),
                self.scene("SC003", 10, 18, "官方说明。", "官方说明", "官方页面高亮", "screenshot", ["S001"]),
                self.scene("SC004", 18, 26, "", "套餐", "套餐卡片", "chart", []),
                self.scene("SC005", 26, 34, "", "差异", "差异图表", "comparison", []),
                self.scene("SC006", 34, 42, "", "使用频率", "使用频率图", "chart", []),
                self.scene("SC007", 42, 50, "", "适合谁", "用户类型对比", "comparison", []),
                self.scene("SC008", 50, 55, "按需决定。", "按需决定", "结论对比图", "comparison", []),
                self.scene("SC009", 55, 60, "", "评论区", "评论引导", "text_only", []),
            ]
        }

    @staticmethod
    def scene(scene_id, start, end, spoken_text, caption, visual_description, visual_type, source):
        return {"scene_id": scene_id, "start": start, "end": end, "spoken_text": spoken_text, "caption": caption, "visual_description": visual_description, "visual_type": visual_type, "asset_query": visual_description, "motion": "静止", "source": source}

    def test_reports_pass_for_distinct_visuals_with_evidence_and_conclusion_emphasis(self):
        result = review_storyboard(self.storyboard, self.script)
        self.assertTrue(result["passed"])
        self.assertTrue(all(result["checks"].values()))

    def test_reports_each_review_failure(self):
        storyboard = {"scenes": [
            self.scene("SC001", 0, 5, "别买。", "别买", "同一张图", "text_only", []),
            self.scene("SC002", 5, 10, "官方说明。", "官方说明", "同一张图", "text_only", []),
            self.scene("SC003", 10, 60, "按需决定。", "按需决定", "同一张图", "real_image", []),
        ]}
        result = review_storyboard(storyboard, self.script)
        self.assertFalse(result["passed"])
        self.assertEqual({issue["check"] for issue in result["issues"]}, {"visual_change", "duplicate_visual", "text_stack", "evidence_visual", "hook_visual", "conclusion_visual"})

    def test_writes_review_without_advancing_storyboard_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_dir = Path(temp_dir) / "projects"
            project_id = "20260915-review-test"
            directory = projects_dir / project_id
            directory.mkdir(parents=True)
            project_state.initialize_run_state(directory, project_id)
            for target in ("RESEARCHED", "SCRIPTED", "STORYBOARDED"):
                project_state.transition_project(directory, project_id, target)
            (directory / "storyboard.json").write_text(json.dumps(self.storyboard), encoding="utf-8")
            (directory / "script.json").write_text(json.dumps(self.script), encoding="utf-8")
            result = write_storyboard_review(directory, project_id)
            self.assertTrue(result["passed"])
            self.assertTrue((directory / "storyboard-review.md").is_file())
            self.assertEqual(project_state.load_run_state(directory, project_id)["status"], "STORYBOARDED")


if __name__ == "__main__":
    unittest.main()
