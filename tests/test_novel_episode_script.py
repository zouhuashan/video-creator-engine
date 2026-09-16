import copy
import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_episode_planning import build_episode_planning, write_episode_planning
from scripts.novel_episode_script import (
    NovelEpisodeScriptError,
    build_script_package,
    load_script_package,
    preview_continuity_snapshot,
    summary,
    validate_script_package,
    write_script_package,
)
from scripts.novel_series_plan import build_plan, write_plan
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import build_bible, write_bible


def review(status="APPROVED"):
    return {"required": True, "status": status, "reviewed_at": "2026-09-16T00:00:00Z" if status == "APPROVED" else None, "reviewed_by": "reviewer" if status == "APPROVED" else None, "note": "test"}


def bible_original():
    return {"kind": "ORIGINAL", "source_refs": [], "note": "测试原创"}


def script_original():
    return {"kind": "ORIGINAL", "source_refs": [], "story_refs": [], "note": "测试原创"}


class NovelEpisodeScriptTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        project_dir = root / "project-test"
        write_project(project_dir, build_project("project-test", "TST", "测试故事"))
        write_catalog(project_dir, build_catalog("project-test", "IP-TST", "测试故事"))
        bible = build_bible(project_dir)
        bible["world"].update({"status": "READY", "premise": "主角启程。", "provenance": bible_original(), "human_review": review()})
        bible["characters"] = [{
            "id": "CHR-TST-HERO", "name": "主角", "aliases": [], "role": "protagonist", "description": "旅人", "goals": ["启程"], "traits": ["勇敢"],
            "baseline_state": {"location_id": None, "costume_id": None, "carried_prop_ids": [], "injuries": [], "knowledge": [], "emotional_state": "期待"},
            "provenance": bible_original(), "human_review": review(),
        }]
        bible["timeline"] = [{"id": "TL-TST-DEPART", "order": 1, "label": "启程", "description": "旅程开始", "character_ids": ["CHR-TST-HERO"], "location_id": None, "provenance": bible_original(), "human_review": review()}]
        baseline = bible["continuity_ledger"]["snapshots"][0]
        baseline["character_states"] = [{"character_id": "CHR-TST-HERO", **bible["characters"][0]["baseline_state"]}]
        baseline["timeline_position_id"] = "TL-TST-DEPART"
        baseline["human_review"] = review()
        write_bible(project_dir, bible)
        write_plan(project_dir, build_plan(project_dir))
        planning = build_episode_planning(project_dir)
        episode_ids = [item["episode_id"] for item in planning["episode_cards"]]
        planning["story_arcs"] = [{"id": "S01-ARC01", "season_id": "S01", "status": "READY", "title": "启程", "objective": "出发", "escalation": "受阻", "climax": "选择", "resolution": "上路", "episode_ids": episode_ids, "character_arc_ids": [], "foreshadowing_ids": [], "provenance": script_original(), "human_review": review()}]
        for card in planning["episode_cards"]:
            card.update({
                "arc_id": "S01-ARC01", "status": "READY", "premise": "启程", "hook": "异象", "goal": "出发", "obstacle": "受阻", "turn": "发现", "climax": "选择", "ending_hook": "远方",
                "beats": [
                    {"id": f"BEAT-{card['episode_id']}-01", "type": "HOOK", "description": "异象", "provenance": script_original()},
                    {"id": f"BEAT-{card['episode_id']}-02", "type": "ENDING_HOOK", "description": "远方", "provenance": script_original()},
                ],
                "character_ids": ["CHR-TST-HERO"], "provenance": script_original(), "human_review": review(),
            })
        write_episode_planning(project_dir, planning)
        return project_dir

    def ready_first_script(self, project_dir: Path):
        package = build_script_package(project_dir)
        script = package["episode_scripts"][0]
        script.update({"status": "READY", "human_review": review()})
        script["scenes"] = [{
            "id": "S01E001-SC001", "sequence": 1, "title": "启程", "purpose": "主角作出选择", "location_id": None, "time_of_day": "清晨", "character_ids": ["CHR-TST-HERO"],
            "units": [
                {"id": "UNIT-S01E001-SC001-001", "sequence": 1, "kind": "ACTION", "text": "主角望向远方。", "speaker_character_id": None, "emotion": None, "sound": None, "estimated_duration_seconds": 2, "beat_ref": "BEAT-S01E001-01", "provenance": script_original()},
                {"id": "UNIT-S01E001-SC001-002", "sequence": 2, "kind": "DIALOGUE", "text": "我该出发了。", "speaker_character_id": "CHR-TST-HERO", "emotion": {"label": "坚定", "intensity": 0.7, "performance_note": "由轻到重"}, "sound": None, "estimated_duration_seconds": 2, "beat_ref": None, "provenance": script_original()},
                {"id": "UNIT-S01E001-SC001-003", "sequence": 3, "kind": "NARRATION", "text": "旅程由此开始。", "speaker_character_id": None, "emotion": {"label": "悠远", "intensity": 0.4, "performance_note": "舒缓"}, "sound": None, "estimated_duration_seconds": 2, "beat_ref": None, "provenance": script_original()},
                {"id": "UNIT-S01E001-SC001-004", "sequence": 4, "kind": "SFX", "text": "船帆张开。", "speaker_character_id": None, "emotion": None, "sound": {"cue": "船帆鼓风", "timing": "ON_ACTION", "mix_note": "近景"}, "estimated_duration_seconds": 1, "beat_ref": "BEAT-S01E001-02", "provenance": script_original()},
            ],
            "provenance": script_original(), "human_review": review(),
        }]
        delta = package["continuity_deltas"][0]
        delta.update({"status": "READY", "timeline_position_id": "TL-TST-DEPART", "human_review": review()})
        delta["character_changes"] = [{"character_id": "CHR-TST-HERO", "set_location_id": None, "set_costume_id": None, "add_carried_prop_ids": [], "remove_carried_prop_ids": [], "add_injuries": [], "remove_injuries": [], "add_knowledge": ["已经决定启程"], "set_emotional_state": "坚定"}]
        return package

    def test_skeleton_writes_two_files_per_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            files = write_script_package(project_dir, build_script_package(project_dir))
            loaded = load_script_package(project_dir)
            result = summary(project_dir)
        self.assertEqual(len(files), 10)
        self.assertEqual(len(loaded["episode_scripts"]), 5)
        self.assertEqual(result["available_input_count"], 1)

    def test_script_units_and_delta_preview_preserve_continuity(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            package = validate_script_package(project_dir, self.ready_first_script(project_dir))
            write_script_package(project_dir, package)
            preview = preview_continuity_snapshot(project_dir, "S01E001")
        kinds = {item["kind"] for item in package["episode_scripts"][0]["scenes"][0]["units"]}
        self.assertEqual(kinds, {"ACTION", "DIALOGUE", "NARRATION", "SFX"})
        self.assertEqual(preview["id"], "CNT-S01E001-END")
        self.assertEqual(preview["character_states"][0]["knowledge"], ["已经决定启程"])
        self.assertEqual(preview["character_states"][0]["emotional_state"], "坚定")

    def test_dialogue_requires_scene_character_and_emotion(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            package = self.ready_first_script(project_dir)
            unit = package["episode_scripts"][0]["scenes"][0]["units"][1]
            unit["speaker_character_id"] = "CHR-TST-MISSING"
            with self.assertRaisesRegex(NovelEpisodeScriptError, "in-scene speaker"):
                validate_script_package(project_dir, package)
            unit["speaker_character_id"] = "CHR-TST-HERO"
            unit["emotion"] = None
            with self.assertRaisesRegex(NovelEpisodeScriptError, "requires an in-scene speaker and emotion"):
                validate_script_package(project_dir, package)

    def test_ready_second_episode_is_blocked_without_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            package = self.ready_first_script(project_dir)
            second = package["episode_scripts"][1]
            second["status"] = "READY"
            second["scenes"] = copy.deepcopy(package["episode_scripts"][0]["scenes"])
            second["scenes"][0]["id"] = "S01E002-SC001"
            for index, unit in enumerate(second["scenes"][0]["units"], start=1):
                unit["id"] = f"UNIT-S01E002-SC001-{index:03d}"
                unit["beat_ref"] = None
            with self.assertRaisesRegex(NovelEpisodeScriptError, "lacks its continuity input"):
                validate_script_package(project_dir, package)

    def test_duration_budget_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            package = self.ready_first_script(project_dir)
            package["episode_scripts"][0]["scenes"][0]["units"][0]["estimated_duration_seconds"] = 60
            package["episode_scripts"][0]["scenes"][0]["units"][1]["estimated_duration_seconds"] = 60
            with self.assertRaisesRegex(NovelEpisodeScriptError, "duration budget"):
                validate_script_package(project_dir, package)


if __name__ == "__main__":
    unittest.main()
