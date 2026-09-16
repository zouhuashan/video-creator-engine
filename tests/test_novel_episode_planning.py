import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_episode_planning import NovelEpisodePlanningError, build_episode_planning, load_episode_planning, validate_episode_planning, write_episode_planning
from scripts.novel_series_plan import build_plan, load_plan, replace_plan, write_plan
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible


def approved():
    return {"required": True, "status": "APPROVED", "reviewed_at": "2026-09-16T00:00:00Z", "reviewed_by": "reviewer", "note": "test"}


def original():
    return {"kind": "ORIGINAL", "source_refs": [], "story_refs": [], "note": "测试原创增补"}


class NovelEpisodePlanningTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        project_dir = root / "project-test"
        write_project(project_dir, build_project("project-test", "TST", "测试故事"))
        write_catalog(project_dir, build_catalog("project-test", "IP-TST", "测试故事"))
        write_bible(project_dir, build_bible(project_dir))
        write_plan(project_dir, build_plan(project_dir))
        return project_dir

    def ready_planning(self, project_dir: Path):
        planning = build_episode_planning(project_dir)
        episode_ids = [card["episode_id"] for card in planning["episode_cards"]]
        planning["story_arcs"] = [{
            "id": "S01-ARC01", "season_id": "S01", "status": "READY", "title": "出发",
            "objective": "完成启程", "escalation": "阻碍增加", "climax": "作出选择", "resolution": "驶向远方",
            "episode_ids": episode_ids, "character_arc_ids": [], "foreshadowing_ids": [], "provenance": original(), "human_review": approved(),
        }]
        for index, card in enumerate(planning["episode_cards"], start=1):
            card.update({
                "arc_id": "S01-ARC01", "status": "READY", "premise": f"第{index}集推进旅程", "hook": "突发异象",
                "goal": "继续前进", "obstacle": "道路受阻", "turn": "发现线索", "climax": "解决眼前危机", "ending_hook": "远处出现新目标",
                "beats": [
                    {"id": f"BEAT-{card['episode_id']}-01", "type": "HOOK", "description": "异象出现", "provenance": original()},
                    {"id": f"BEAT-{card['episode_id']}-02", "type": "ENDING_HOOK", "description": "新目标出现", "provenance": original()},
                ],
                "provenance": original(), "human_review": approved(),
            })
        return planning

    def test_skeleton_has_one_card_per_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            planning = build_episode_planning(project_dir)
            write_episode_planning(project_dir, planning)
            loaded = load_episode_planning(project_dir)
        self.assertEqual(len(loaded["episode_cards"]), 5)
        self.assertEqual(loaded["episode_cards"][0]["id"], "CARD-S01E001")

    def test_ready_arc_and_cards_validate_with_traceable_beats(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            planning = validate_episode_planning(project_dir, self.ready_planning(project_dir))
        self.assertEqual(len(planning["story_arcs"][0]["episode_ids"]), 5)
        self.assertEqual({beat["type"] for beat in planning["episode_cards"][0]["beats"]}, {"HOOK", "ENDING_HOOK"})

    def test_arc_length_and_ready_card_requirements_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            planning = self.ready_planning(project_dir)
            planning["story_arcs"][0]["episode_ids"] = planning["story_arcs"][0]["episode_ids"][:2]
            with self.assertRaisesRegex(NovelEpisodePlanningError, "3 to 8"):
                validate_episode_planning(project_dir, planning)
            planning = self.ready_planning(project_dir)
            planning["episode_cards"][0]["ending_hook"] = ""
            with self.assertRaisesRegex(NovelEpisodePlanningError, "incomplete"):
                validate_episode_planning(project_dir, planning)

    def test_upstream_series_revision_invalidates_episode_planning(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            write_episode_planning(project_dir, build_episode_planning(project_dir))
            replace_plan(project_dir, load_plan(project_dir))
            with self.assertRaisesRegex(NovelEpisodePlanningError, "stale"):
                load_episode_planning(project_dir)


if __name__ == "__main__":
    unittest.main()
