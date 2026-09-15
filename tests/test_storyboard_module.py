import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import project_state
from scripts.storyboard_module import StoryboardInputError, write_storyboard_artifacts


ROOT = Path(__file__).resolve().parents[1]


class StoryboardModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.temp_dir.name) / "projects"
        self.project_id = "20260915-storyboard-test"
        self.directory = self.projects_dir / self.project_id
        self.directory.mkdir(parents=True)
        project_state.initialize_run_state(self.directory, self.project_id)
        project_state.transition_project(self.directory, self.project_id, "RESEARCHED")
        project_state.transition_project(self.directory, self.project_id, "SCRIPTED")
        self.script = {
            "schema_version": 1,
            "project_id": self.project_id,
            "topic": "可信主题",
            "platform": "wechat_channels",
            "target_duration_seconds": 60,
            "sections": [
                {"section": "hook", "narration": "别买，真的不值。", "source_ids": []},
                {"section": "problem", "narration": "GPT贵。", "source_ids": []},
                {"section": "evidence", "narration": "官方价格写得很清楚。", "source_ids": ["S001"]},
                {"section": "comparison", "narration": "免费版够多数人用。", "source_ids": []},
                {"section": "conclusion", "narration": "按需求再决定。", "source_ids": []},
                {"section": "cta", "narration": "评论区说说你的用法。", "source_ids": []},
            ],
            "sources": [
                {
                    "source_id": "S001",
                    "title": "官方说明",
                    "url": "https://example.com/official",
                    "source_type": "official",
                }
            ],
        }
        (self.directory / "script.json").write_text(json.dumps(self.script, ensure_ascii=False), encoding="utf-8")
        spoken = [section["narration"] for section in self.script["sections"]]
        self.payload = {
            "schema_version": 1,
            "scenes": [
                self.scene("SC001", 0, 3, spoken[0], "别买", "价格标签被划掉", "text_only", "产品价格", "快速推近", "硬切", []),
                self.scene("SC002", 3, 10, spoken[1], "GPT贵", "账单金额出现", "screenshot", "订阅账单", "轻微平移", "叠化", []),
                self.scene("SC003", 10, 35, spoken[2], "官方价格", "官方价格页高亮", "screenshot", "官方定价页面", "局部放大", "擦除", ["S001"]),
                self.scene("SC004", 35, 50, spoken[3], "免费版够用", "两栏对比", "comparison", "免费版与付费版", "左右滑动", "叠化", []),
                self.scene("SC005", 50, 55, spoken[4], "按需决定", "按需决定", "text_only", "结论文字", "缓慢推近", "淡入", []),
                self.scene("SC006", 55, 60, spoken[5], "说说你的用法", "留言告诉我", "text_only", "评论引导", "静止", "淡出", []),
            ],
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def scene(scene_id, start, end, spoken_text, caption, visual_description, visual_type, asset_query, motion, transition, source):
        return {
            "scene_id": scene_id,
            "start": start,
            "end": end,
            "spoken_text": spoken_text,
            "caption": caption,
            "visual_description": visual_description,
            "visual_type": visual_type,
            "asset_query": asset_query,
            "motion": motion,
            "transition": transition,
            "source": source,
        }

    def test_writes_complete_timed_storyboard_and_advances_state(self):
        result = write_storyboard_artifacts(self.directory, self.project_id, self.payload)

        self.assertEqual(result["scene_count"], 6)
        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "STORYBOARDED")
        storyboard = json.loads((self.directory / "storyboard.json").read_text(encoding="utf-8"))
        self.assertEqual(storyboard["scenes"][2]["source"], ["S001"])
        self.assertEqual(storyboard["scenes"][-1]["end"], 60.0)
        markdown = (self.directory / "storyboard.md").read_text(encoding="utf-8")
        self.assertIn("## SC003 · 10–35 秒", markdown)
        self.assertIn("- 来源：[S001]", markdown)

    def test_rejects_time_gaps_without_outputs_or_state_change(self):
        payload = copy.deepcopy(self.payload)
        payload["scenes"][2]["start"] = 11
        with self.assertRaisesRegex(StoryboardInputError, "must start at 10"):
            write_storyboard_artifacts(self.directory, self.project_id, payload)
        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "SCRIPTED")
        self.assertFalse((self.directory / "storyboard.json").exists())

    def test_rejects_missing_spoken_text_and_evidence_visual(self):
        payload = copy.deepcopy(self.payload)
        payload["scenes"][5]["spoken_text"] = "评论区见。"
        with self.assertRaisesRegex(StoryboardInputError, "cover.*exactly"):
            write_storyboard_artifacts(self.directory, self.project_id, payload)

        payload = copy.deepcopy(self.payload)
        payload["scenes"][2]["source"] = []
        with self.assertRaisesRegex(StoryboardInputError, "evidence visual"):
            write_storyboard_artifacts(self.directory, self.project_id, payload)

    def test_rejects_unknown_sources_and_nonsequential_ids(self):
        payload = copy.deepcopy(self.payload)
        payload["scenes"][2]["source"] = ["S999"]
        with self.assertRaisesRegex(StoryboardInputError, "unknown script source"):
            write_storyboard_artifacts(self.directory, self.project_id, payload)

        payload = copy.deepcopy(self.payload)
        payload["scenes"][1]["scene_id"] = "SC009"
        with self.assertRaisesRegex(StoryboardInputError, "sequential"):
            write_storyboard_artifacts(self.directory, self.project_id, payload)

    def test_rejects_visual_types_outside_the_supported_catalog(self):
        payload = copy.deepcopy(self.payload)
        payload["scenes"][0]["visual_type"] = "animated_gif"
        with self.assertRaisesRegex(StoryboardInputError, "visual_type must be one of"):
            write_storyboard_artifacts(self.directory, self.project_id, payload)

    def test_refuses_to_overwrite_and_requires_scripted_state(self):
        (self.directory / "storyboard.md").write_text("保留", encoding="utf-8")
        with self.assertRaisesRegex(project_state.StateError, "refusing to overwrite"):
            write_storyboard_artifacts(self.directory, self.project_id, self.payload)
        self.assertEqual((self.directory / "storyboard.md").read_text(encoding="utf-8"), "保留")

    def test_cli_writes_artifacts(self):
        input_file = Path(self.temp_dir.name) / "storyboard-input.json"
        input_file.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "video_creator.py"),
                "storyboard",
                self.project_id,
                "--input-file",
                str(input_file),
                "--projects-dir",
                str(self.projects_dir),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout)["state"], "STORYBOARDED")
        self.assertTrue((self.directory / "storyboard.json").is_file())


if __name__ == "__main__":
    unittest.main()
