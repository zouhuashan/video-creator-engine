import unittest
from pathlib import Path

from scripts.assemble_local_episodes import (
    _aggregate_human_review,
    _merge_episode_results,
    _pending_human_review,
    _subtitle_blocks,
    _subtitle_entries,
    build_plan,
)


class AssembleLocalEpisodesTests(unittest.TestCase):
    def test_wraps_long_chinese_subtitles_inside_portrait_safe_lines(self):
        text = "上林苑的花光越过宫墙，与小蓬莱玉碑遥遥相映。真正的镜花缘，才刚刚开始。"
        blocks = _subtitle_blocks(text)
        self.assertEqual(len(blocks), 2)
        self.assertTrue(all(len(line) <= 16 for block in blocks for line in block.splitlines()))
        self.assertEqual("".join(blocks).replace("\n", ""), text)

    def test_distributes_subtitle_blocks_over_the_source_timing(self):
        entries = _subtitle_entries("甲" * 35, 2.0, 9.0)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0][0], 2.0)
        self.assertEqual(entries[-1][1], 9.0)
        self.assertEqual("".join(item[2].replace("\n", "") for item in entries), "甲" * 35)

    def test_partial_rerender_preserves_unselected_review_and_invalidates_rerendered_episode(self):
        approved = {
            "required": True,
            "status": "APPROVED",
            "checks": {"story": "PASS", "picture": "PASS", "audio": "PASS", "subtitles": "PASS"},
            "reviewed_at": "2026-09-18T10:00:00Z",
            "reviewed_by": "reviewer-a",
            "note": "approved",
        }
        existing = {
            "episodes": [
                {"episode_id": "S01E001", "status": "COMPLETED", "human_review": approved},
                {"episode_id": "S01E002", "status": "COMPLETED", "human_review": approved},
            ]
        }
        rendered = [{"episode_id": "S01E002", "status": "COMPLETED", "human_review": _pending_human_review()}]
        merged = _merge_episode_results(["S01E001", "S01E002"], rendered, existing)
        self.assertEqual([item["episode_id"] for item in merged], ["S01E001", "S01E002"])
        self.assertEqual(merged[0]["human_review"]["status"], "APPROVED")
        self.assertEqual(merged[1]["human_review"]["status"], "PENDING")
        self.assertTrue(all(value == "PENDING" for value in merged[1]["human_review"]["checks"].values()))
        self.assertEqual(_aggregate_human_review(merged)["status"], "PENDING")

    def test_aggregate_review_is_approved_only_when_every_episode_is_approved(self):
        episodes = []
        for episode_id in ("S01E001", "S01E002"):
            review = _pending_human_review()
            review.update({"status": "APPROVED", "reviewed_at": "2026-09-18T10:00:00Z", "reviewed_by": "reviewer-a"})
            episodes.append({"episode_id": episode_id, "status": "COMPLETED", "human_review": review})
        aggregate = _aggregate_human_review(episodes)
        self.assertEqual(aggregate["status"], "APPROVED")
        self.assertEqual(aggregate["reviewed_by"], "reviewer-a")

    def test_builds_five_episode_unit_plan_from_registered_media(self):
        project = Path("projects/jinghua-yuan-series").resolve()
        plan = build_plan(project)
        self.assertEqual(len(plan["episodes"]), 5)
        segments = [segment for episode in plan["episodes"] for segment in episode["segments"]]
        self.assertEqual(len(segments), 48)
        self.assertEqual(sum(item["source"] == "dialogue_final" for item in segments), 16)
        self.assertEqual(sum(item["source"] == "narration_render" for item in segments), 12)
        self.assertTrue(all((project / item["background"]).is_file() for item in segments))


if __name__ == "__main__":
    unittest.main()
