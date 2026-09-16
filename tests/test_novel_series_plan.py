import json
import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_series_plan import NovelSeriesPlanError, build_plan, load_plan, readiness, validate_plan, write_plan
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, replace_bible, write_bible


def approved():
    return {"required": True, "status": "APPROVED", "reviewed_at": "2026-09-16T00:00:00Z", "reviewed_by": "reviewer", "note": "test"}


def original():
    return {"kind": "ORIGINAL", "source_refs": [], "note": "测试原创设定"}


def story_ref(*refs):
    return {"kind": "SOURCE", "source_refs": [], "story_refs": list(refs), "note": ""}


class NovelSeriesPlanTests(unittest.TestCase):
    def make_project(self, root: Path, *, populated_bible=False) -> Path:
        project_dir = root / "project-test"
        write_project(project_dir, build_project("project-test", "TST", "测试故事"))
        write_catalog(project_dir, build_catalog("project-test", "IP-TST", "测试故事"))
        bible = build_bible(project_dir)
        if populated_bible:
            bible["world"].update({"status": "READY", "premise": "主角踏上旅程。", "provenance": original(), "human_review": approved()})
            bible["characters"] = [{
                "id": "CHR-TST-HERO", "name": "主角", "aliases": [], "role": "protagonist", "description": "旅人", "goals": ["抵达终点"], "traits": ["勇敢"],
                "baseline_state": {"location_id": None, "costume_id": None, "carried_prop_ids": [], "injuries": [], "knowledge": [], "emotional_state": "期待"},
                "provenance": original(), "human_review": approved(),
            }]
            bible["timeline"] = [{"id": "TL-TST-DEPART", "order": 1, "label": "出发", "description": "旅程开始", "character_ids": ["CHR-TST-HERO"], "location_id": None, "provenance": original(), "human_review": approved()}]
            baseline = bible["continuity_ledger"]["snapshots"][0]
            baseline["character_states"] = [{"character_id": "CHR-TST-HERO", **bible["characters"][0]["baseline_state"]}]
            baseline["timeline_position_id"] = "TL-TST-DEPART"
            baseline["human_review"] = approved()
        write_bible(project_dir, bible)
        return project_dir

    def ready_plan(self, project_dir: Path):
        plan = build_plan(project_dir)
        plan["series_plan"].update({
            "status": "READY", "logline": "主角跨海寻找终点。", "themes": ["成长"], "audience": "青少年", "format": "竖屏短剧", "ending": "完成第一阶段旅程", "adaptation_strategy": "聚焦主线",
            "character_arc_ids": ["CARC-TST-HERO-S01"], "provenance": story_ref("WORLD-TST"), "human_review": approved(),
        })
        season = plan["season_plans"][0]
        season.update({
            "status": "READY", "premise": "第一段旅程", "dramatic_question": "能否出发", "start_state": "尚未启程", "end_state": "驶向远方",
            "major_turns": [{"id": "TURN-S01-01", "episode_id": "S01E003", "label": "决定出发", "description": "主角接受挑战", "provenance": story_ref("TL-TST-DEPART")}],
            "character_arc_ids": ["CARC-TST-HERO-S01"], "provenance": story_ref("WORLD-TST"), "human_review": approved(),
        })
        plan["character_arcs"] = [{
            "id": "CARC-TST-HERO-S01", "character_id": "CHR-TST-HERO", "season_id": "S01", "status": "READY",
            "start_state": "犹豫", "want": "出发", "need": "承担选择", "internal_conflict": "害怕未知",
            "milestones": [{"id": "MILE-TST-HERO-01", "episode_id": "S01E003", "change": "作出决定", "provenance": story_ref("TL-TST-DEPART")}],
            "end_state": "坚定", "provenance": story_ref("CHR-TST-HERO"), "human_review": approved(),
        }]
        return plan

    def test_create_split_files_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            files = write_plan(project_dir, build_plan(project_dir))
            loaded = load_plan(project_dir)
        self.assertEqual(len(files), 3)
        self.assertEqual(loaded["series_plan"]["id"], "SERPLAN-TST-01")
        self.assertEqual(loaded["season_plans"][0]["episode_ids"], [f"S01E{index:03d}" for index in range(1, 6)])

    def test_ready_plan_links_story_and_character_arc(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory), populated_bible=True)
            plan = validate_plan(project_dir, self.ready_plan(project_dir))
            write_plan(project_dir, plan)
            state = readiness(project_dir)
        self.assertEqual(plan["character_arcs"][0]["character_id"], "CHR-TST-HERO")
        self.assertTrue(state["ready"])

    def test_season_coverage_and_turn_scope_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory), populated_bible=True)
            plan = self.ready_plan(project_dir)
            plan["season_plans"][0]["episode_ids"].pop()
            with self.assertRaisesRegex(NovelSeriesPlanError, "episode coverage"):
                validate_plan(project_dir, plan)
            plan = self.ready_plan(project_dir)
            plan["season_plans"][0]["major_turns"][0]["episode_id"] = "S02E001"
            with self.assertRaisesRegex(NovelSeriesPlanError, "outside its season"):
                validate_plan(project_dir, plan)

    def test_unknown_story_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory), populated_bible=True)
            plan = self.ready_plan(project_dir)
            plan["series_plan"]["provenance"] = story_ref("CHR-TST-MISSING")
            with self.assertRaisesRegex(NovelSeriesPlanError, "unknown provenance"):
                validate_plan(project_dir, plan)

    def test_plan_is_stale_after_story_bible_revision_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            write_plan(project_dir, build_plan(project_dir))
            bible_path = project_dir / "story-bible" / "world.json"
            before = json.loads(bible_path.read_text(encoding="utf-8"))["revision"]
            from scripts.novel_story_bible import load_bible
            replace_bible(project_dir, load_bible(project_dir))
            self.assertEqual(json.loads(bible_path.read_text(encoding="utf-8"))["revision"], before + 1)
            with self.assertRaisesRegex(NovelSeriesPlanError, "stale"):
                load_plan(project_dir)


if __name__ == "__main__":
    unittest.main()
