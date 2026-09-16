import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import topic_pool
import trend_discovery


def trend(signal_id, source_type, topic, strength, observed_at="2026-09-16T00:00:00Z"):
    return {
        "signal_id": signal_id,
        "source_type": source_type,
        "topic": topic,
        "title": f"{topic} update",
        "source_name": f"Source {source_type}",
        "observed_at": observed_at,
        "strength": strength,
        "url": f"https://example.com/{signal_id}",
    }


def artifact():
    signals = [
        trend("a1", "wechat_ecosystem", "AI 助手实测", 92),
        trend("a2", "search_trend", "AI 助手实测", 88),
        trend("a3", "ai_digital_news", "ai助手实测", 80),
        trend("b1", "community", "旧手机清理技巧", 55, "2026-08-16T08:00:00Z"),
    ]
    return trend_discovery.discover_trends(
        [_Source(kind, signals) for kind in trend_discovery.SOURCE_TYPES],
        run_date="2026-09-16",
        collected_at="2026-09-16T10:00:00Z",
    )


class _Source:
    def __init__(self, source_type, all_signals):
        self.source_type = source_type
        self.all_signals = all_signals

    def fetch(self):
        return [item for item in self.all_signals if item["source_type"] == self.source_type]


class TopicPoolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_candidates_are_grouped_ranked_and_never_production_eligible(self):
        result = topic_pool.build_topic_pool(artifact())
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["candidates"][0]["topic"], "AI 助手实测")
        self.assertEqual(result["candidates"][0]["score_breakdown"]["source_diversity"], 60)
        self.assertEqual(result["candidates"][0]["score_breakdown"]["signal_strength"], 87)
        self.assertFalse(any(item["production_eligible"] for item in result["candidates"]))
        self.assertEqual(result["candidates"][0]["next_step"], "verify_sources_and_complete_research")

    def test_tie_order_is_stable_for_same_input_and_reference_ids_are_included(self):
        source = artifact()
        first = topic_pool.build_topic_pool(source, as_of="2026-09-16")
        second = topic_pool.build_topic_pool(copy.deepcopy(source), as_of="2026-09-16")
        self.assertEqual([item["topic"] for item in first["candidates"]], [item["topic"] for item in second["candidates"]])
        self.assertEqual(
            {item["signal_id"] for item in first["candidates"][0]["supporting_signals"]},
            {"a1", "a2", "a3"},
        )

    def test_invalid_artifact_or_as_of_is_rejected(self):
        with self.assertRaisesRegex(topic_pool.TopicPoolError, "duplicate signal_id"):
            broken = artifact()
            broken["signals"].append(broken["signals"][0])
            topic_pool.build_topic_pool(broken)
        with self.assertRaisesRegex(topic_pool.TopicPoolError, "YYYY-MM-DD"):
            topic_pool.build_topic_pool(artifact(), as_of="yesterday")

    def test_cli_writes_topics_date_json_and_refuses_overwrite(self):
        source = self.directory / "trends.json"
        source.write_text(json.dumps(artifact(), ensure_ascii=False), encoding="utf-8")
        output_dir = self.directory / "topics"
        command = [sys.executable, str(ROOT / "scripts" / "topic_pool.py"), str(source), "--output-dir", str(output_dir)]
        first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        output = output_dir / "2026-09-16.json"
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["candidate_count"], 2)
        second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("refusing to overwrite", second.stderr)

    def test_end_to_end_source_import_builds_review_only_topic_pool(self):
        source_files = []
        for index, source_type in enumerate(("search_trend", "ai_digital_news", "community")):
            source = self.directory / f"{source_type}.json"
            record = trend("e2e-" + source_type, source_type, "AI workflow", 70 + index * 5)
            source.write_text(json.dumps([record]), encoding="utf-8")
            source_files.append((source_type, source))

        trend_dir = self.directory / "trends"
        discovery_command = [sys.executable, str(ROOT / "scripts" / "trend_discovery.py"), "--date", "2026-09-16", "--output-dir", str(trend_dir)]
        for source_type, source in source_files:
            discovery_command.extend(("--source", f"{source_type}={source}"))
        discovery = subprocess.run(discovery_command, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(discovery.returncode, 0, discovery.stderr)

        pool_dir = self.directory / "pool"
        pool_command = [
            sys.executable, str(ROOT / "scripts" / "topic_pool.py"),
            str(trend_dir / "2026-09-16.json"), "--output-dir", str(pool_dir),
        ]
        pool = subprocess.run(pool_command, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(pool.returncode, 0, pool.stderr)
        payload = json.loads((pool_dir / "2026-09-16.json").read_text(encoding="utf-8"))
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["topic"], "AI workflow")
        self.assertEqual(candidate["score_breakdown"]["source_diversity"], 60)
        self.assertEqual(len(candidate["supporting_signals"]), 3)
        self.assertFalse(candidate["production_eligible"])


if __name__ == "__main__":
    unittest.main()
