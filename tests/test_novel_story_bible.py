import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.novel_anime_project import build_project, write_project
from scripts.novel_source_catalog import build_catalog, write_catalog
from scripts.novel_story_bible import (
    NovelStoryBibleError,
    build_bible,
    continuity_input,
    load_bible,
    record_snapshot,
    readiness,
    replace_bible,
    summary,
    validate_bible,
    write_bible,
)


def review():
    return {"required": True, "status": "PENDING", "reviewed_at": None, "reviewed_by": None, "note": ""}


def original(note="测试原创设定"):
    return {"kind": "ORIGINAL", "source_refs": [], "note": note}


class NovelStoryBibleTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        project_dir = root / "project-test"
        write_project(project_dir, build_project("project-test", "TST", "测试故事"))
        write_catalog(project_dir, build_catalog("project-test", "IP-TST", "测试故事"))
        return project_dir

    def populate(self, bible):
        bible["world"].update({"status": "READY", "premise": "一场测试旅程。", "provenance": original()})
        bible["locations"] = [{
            "id": "LOCN-TST-HARBOR", "name": "海港", "description": "出发地", "region": "东岸",
            "visual_traits": ["木船"], "provenance": original(), "human_review": review(),
        }]
        bible["characters"] = [{
            "id": "CHR-TST-HERO", "name": "主角", "aliases": [], "role": "protagonist", "description": "旅人",
            "goals": ["出海"], "traits": ["果断"],
            "baseline_state": {"location_id": "LOCN-TST-HARBOR", "costume_id": None, "carried_prop_ids": ["PROP-TST-COMPASS"], "injuries": [], "knowledge": ["知道航路"], "emotional_state": "期待"},
            "provenance": original(), "human_review": review(),
        }, {
            "id": "CHR-TST-GUIDE", "name": "向导", "aliases": [], "role": "supporting", "description": "向导",
            "goals": [], "traits": [],
            "baseline_state": {"location_id": "LOCN-TST-HARBOR", "costume_id": None, "carried_prop_ids": [], "injuries": [], "knowledge": [], "emotional_state": "平静"},
            "provenance": original(), "human_review": review(),
        }]
        bible["relationships"] = [{
            "id": "REL-TST-HERO-GUIDE", "from_character_id": "CHR-TST-HERO", "to_character_id": "CHR-TST-GUIDE",
            "type": "同伴", "status": "初识", "description": "共同出海", "provenance": original(), "human_review": review(),
        }]
        bible["props"] = [{
            "id": "PROP-TST-COMPASS", "name": "罗盘", "description": "导航", "owner_character_id": "CHR-TST-HERO",
            "home_location_id": None, "story_function": "引路", "provenance": original(), "human_review": review(),
        }]
        bible["rules"] = [{"id": "RULE-TST-NAV", "name": "航行规则", "description": "需依罗盘", "scope": "海上", "exceptions": [], "provenance": original(), "human_review": review()}]
        bible["timeline"] = [{"id": "TL-TST-DEPART", "order": 1, "label": "出发", "description": "从海港出发", "character_ids": ["CHR-TST-HERO", "CHR-TST-GUIDE"], "location_id": "LOCN-TST-HARBOR", "provenance": original(), "human_review": review()}]
        bible["foreshadowing"] = [{"id": "FSH-TST-COMPASS", "label": "罗盘异动", "setup_timeline_id": "TL-TST-DEPART", "status": "OPEN", "target_episode_id": "S01E002", "payoff_episode_id": None, "description": "指针异常", "provenance": original(), "human_review": review()}]
        baseline = bible["continuity_ledger"]["snapshots"][0]
        baseline.update({
            "timeline_position_id": "TL-TST-DEPART",
            "character_states": [
                {"character_id": "CHR-TST-HERO", **bible["characters"][0]["baseline_state"]},
                {"character_id": "CHR-TST-GUIDE", **bible["characters"][1]["baseline_state"]},
            ],
            "relationship_states": [{"relationship_id": "REL-TST-HERO-GUIDE", "status": "初识", "note": ""}],
            "prop_states": [{"prop_id": "PROP-TST-COMPASS", "location_id": None, "holder_character_id": "CHR-TST-HERO", "condition": "完好"}],
            "open_foreshadowing_ids": ["FSH-TST-COMPASS"],
        })
        return bible

    def test_create_split_files_and_load_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            paths = write_bible(project_dir, build_bible(project_dir))
            loaded = load_bible(project_dir)
            result = summary(project_dir)
        self.assertEqual(len(paths), 9)
        self.assertEqual(loaded["world"]["id"], "WORLD-TST")
        self.assertEqual(result["continuity_snapshot_count"], 1)
        self.assertEqual(result["character_count"], 0)

    def test_original_entities_and_cross_references_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            bible = validate_bible(project_dir, self.populate(build_bible(project_dir)))
            write_bible(project_dir, bible)
            state = readiness(project_dir)
        self.assertEqual(bible["relationships"][0]["to_character_id"], "CHR-TST-GUIDE")
        self.assertEqual(bible["continuity_ledger"]["snapshots"][0]["prop_states"][0]["holder_character_id"], "CHR-TST-HERO")
        self.assertFalse(state["ready"])
        self.assertTrue(any("awaiting approval" in blocker for blocker in state["blockers"]))

    def test_provenance_and_reference_errors_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            bible = build_bible(project_dir)
            bible["world"].update({"status": "READY", "premise": "有内容", "provenance": {"kind": "SOURCE", "source_refs": ["CH-TST-0001"], "note": ""}})
            with self.assertRaisesRegex(NovelStoryBibleError, "unknown source"):
                validate_bible(project_dir, bible)
            bible = self.populate(build_bible(project_dir))
            bible["relationships"][0]["to_character_id"] = "CHR-TST-MISSING"
            with self.assertRaisesRegex(NovelStoryBibleError, "invalid character"):
                validate_bible(project_dir, bible)
            bible = self.populate(build_bible(project_dir))
            bible["characters"][0]["provenance"] = {"kind": "UNSET", "source_refs": [], "note": ""}
            with self.assertRaisesRegex(NovelStoryBibleError, "source-backed"):
                validate_bible(project_dir, bible)

    def test_next_episode_reads_previous_end_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            bible = self.populate(build_bible(project_dir))
            write_bible(project_dir, bible)
            first = continuity_input(project_dir, "S01E001")
            with self.assertRaisesRegex(NovelStoryBibleError, "previous episode"):
                continuity_input(project_dir, "S01E002")
            snapshot = copy.deepcopy(first["snapshot"])
            snapshot.update({"id": "CNT-S01E001-END", "episode_id": "S01E001", "sequence": 1, "prior_snapshot_id": first["input_snapshot_id"], "continuity_delta_ref": "episodes/S01E001/continuity-delta.json"})
            snapshot_file = Path(directory) / "snapshot.json"
            snapshot_file.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            record_snapshot(project_dir, snapshot_file)
            second = continuity_input(project_dir, "S01E002")
        self.assertEqual(first["input_snapshot_id"], "CNT-S01E000-END")
        self.assertEqual(second["input_snapshot_id"], "CNT-S01E001-END")
        self.assertEqual(second["snapshot"]["character_states"][0]["knowledge"], ["知道航路"])

    def test_split_file_metadata_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = self.make_project(Path(directory))
            write_bible(project_dir, build_bible(project_dir))
            path = project_dir / "story-bible" / "rules.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["revision"] = 2
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(NovelStoryBibleError, "inconsistent metadata"):
                load_bible(project_dir)


if __name__ == "__main__":
    unittest.main()
