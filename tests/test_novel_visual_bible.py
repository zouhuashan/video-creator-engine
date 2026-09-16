import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import build_script_package, load_script_package, write_script_package
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible
from scripts.novel_story_review import audit_story, write_report
from scripts.novel_visual_bible import NovelVisualBibleError, build_visual_bible, load_visual_bible, summary, validate_visual_bible, write_visual_bible


def approved():
    return {"required": True, "status": "APPROVED", "reviewed_at": "2026-09-16T00:00:00Z", "reviewed_by": "reviewer", "note": "test"}


class NovelVisualBibleTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        project_dir = root / "project-test"
        write_project(project_dir, build_project("project-test", "TST", "测试故事"))
        write_catalog(project_dir, build_catalog("project-test", "IP-TST", "测试故事"))
        write_bible(project_dir, build_bible(project_dir))
        write_plan(project_dir, build_plan(project_dir))
        write_episode_planning(project_dir, build_episode_planning(project_dir))
        write_script_package(project_dir, build_script_package(project_dir))
        write_report(project_dir, audit_story(project_dir))
        return project_dir

    def ready_visual(self, project_dir: Path):
        visual = build_visual_bible(project_dir)
        visual["style"].update({
            "status": "READY", "art_direction": "工笔线描结合淡彩国风动画", "cultural_basis": ["古典器物与服饰形制"],
            "linework": "清晰墨线", "rendering": "二维赛璐璐淡彩", "texture": "宣纸颗粒", "character_language": "克制比例与清晰剪影",
            "environment_language": "层叠山水与留白", "motion_language": "缓入快出、衣带有惯性", "prompt_prefix": "国风二维动漫，统一角色设计",
            "provenance": {"kind": "ORIGINAL", "source_refs": [], "story_refs": [], "note": "测试原创视觉方向"}, "human_review": approved(),
        })
        visual["color_script"].update({
            "status": "READY", "human_review": approved(),
            "swatches": [{"id": "COLOR-TST-INK", "name": "墨色", "hex": "#20252B", "role": "轮廓"}, {"id": "COLOR-TST-JADE", "name": "青玉", "hex": "#6B9A8B", "role": "环境"}],
        })
        for palette in visual["color_script"]["episode_palettes"]:
            palette.update({"mood": "启程", "time_of_day": "清晨", "lighting": "柔和侧光", "swatch_ids": ["COLOR-TST-INK", "COLOR-TST-JADE"], "transition_note": "保持色温连续"})
        visual["composition"].update({"status": "READY", "human_review": approved(), "rules": [{"id": "COMPRULE-TST-SUBJECT", "name": "主体可读", "rule": "角色面部与动作不得落入字幕区", "applies_to": ["CHARACTER", "DIALOGUE"]}]})
        visual["negative_constraints"].update({"status": "READY", "human_review": approved()})
        return visual

    def test_create_four_files_and_episode_palette_skeleton(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            files = write_visual_bible(project_dir, build_visual_bible(project_dir))
            loaded = load_visual_bible(project_dir)
            result = summary(project_dir)
        self.assertEqual(len(files), 4)
        self.assertEqual(len(loaded["color_script"]["episode_palettes"]), 5)
        self.assertEqual(result["negative_constraint_count"], 9)

    def test_complete_ready_visual_direction_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            visual = validate_visual_bible(project_dir, self.ready_visual(project_dir))
        self.assertEqual(visual["style"]["status"], "READY")
        self.assertEqual(visual["composition"]["canvas"]["aspect_ratio"], "9:16")

    def test_canvas_and_palette_references_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            visual = self.ready_visual(project_dir)
            visual["composition"]["canvas"]["width"] = 1920
            with self.assertRaisesRegex(NovelVisualBibleError, "dimensions"):
                validate_visual_bible(project_dir, visual)
            visual = self.ready_visual(project_dir)
            visual["color_script"]["episode_palettes"][0]["swatch_ids"] = ["COLOR-TST-MISSING"]
            with self.assertRaisesRegex(NovelVisualBibleError, "unknown swatches"):
                validate_visual_bible(project_dir, visual)

    def test_ready_sections_must_advance_together(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            visual = build_visual_bible(project_dir)
            visual["style"]["status"] = "READY"
            with self.assertRaisesRegex(NovelVisualBibleError, "together"):
                validate_visual_bible(project_dir, visual)

    def test_upstream_script_revision_invalidates_visual_bible(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            write_visual_bible(project_dir, build_visual_bible(project_dir))
            package = load_script_package(project_dir)
            package["revision"] += 1
            package["updated_at"] = "2026-09-16T02:00:00Z"
            write_script_package(project_dir, package, overwrite=True)
            with self.assertRaisesRegex(NovelVisualBibleError, "stale"):
                load_visual_bible(project_dir)


if __name__ == "__main__":
    unittest.main()
