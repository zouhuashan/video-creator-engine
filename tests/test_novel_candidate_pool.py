import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "validation" / "novel-candidate-catalog.json"
sys.path.insert(0, str(ROOT))

from scripts import novel_candidate_pool


def catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


class NovelCandidatePoolTests(unittest.TestCase):
    def test_ranked_platform_snapshots_flow_through_p15_and_p16_without_blending_raw_counts(self):
        result = novel_candidate_pool.build_novel_candidate_pool(catalog())

        self.assertEqual(result["trend_discovery"]["stats"]["signals_accepted"], 4)
        self.assertEqual(result["topic_pool"]["candidate_count"], 4)
        self.assertEqual(result["topic_pool_match_count"], 4)
        self.assertEqual(result["rights_blocked_count"], 5)
        self.assertEqual(result["human_adaptation_review_candidates"], [])
        self.assertFalse(result["main_ip_selected"])
        self.assertFalse(result["publication_allowed"])
        star = next(item for item in result["candidates"] if item["candidate_id"] == "CN-002")
        self.assertEqual(star["platform_signals"][0]["metric_value"], 212000)
        self.assertIn("缓存", star["platform_signals"][0]["evidence_note"])
        self.assertFalse(star["topic_pool_match"])
        top_ranked = result["topic_pool"]["candidates"][0]
        self.assertEqual(top_ranked["topic"], "高冷太子的克星")

    def test_rights_pass_needs_evidence_and_never_auto_selects_main_ip(self):
        source = catalog()
        source["candidates"].append({
            "candidate_id": "CN-PD",
            "title": "公版测试故事",
            "author": "古代作者",
            "genre": "志怪短篇",
            "work_status": "completed",
            "adaptation_source": {"source_url": "https://example.com/source", "edition_note": "测试底本"},
            "rights": {
                "status": "public_domain_source_verified",
                "basis": "测试用公版权利记录",
                "evidence_urls": ["https://example.com/rights"],
            },
            "platform_signals": [{
                "platform": "测试榜单",
                "chart_name": "测试榜",
                "chart_period": "2026-09",
                "observed_at": "2026-09-16",
                "rank": 1,
                "chart_size": 10,
                "metric_name": "榜单名次",
                "metric_value": 1,
                "metric_unit": "名",
                "source_url": "https://example.com/classic-rank",
            }],
            "pool_topic": "公版测试故事",
        })
        result = novel_candidate_pool.build_novel_candidate_pool(source)
        self.assertEqual(result["human_adaptation_review_candidates"], ["CN-PD"])
        self.assertFalse(next(item for item in result["candidates"] if item["candidate_id"] == "CN-PD")["main_ip_selected"])

        source = catalog()
        source["candidates"].append({
            "candidate_id": "CN-PD",
            "title": "公版测试故事",
            "author": "古代作者",
            "genre": "志怪短篇",
            "work_status": "completed",
            "adaptation_source": {"source_url": "https://example.com/source", "edition_note": "测试底本"},
            "rights": {"status": "public_domain_source_verified", "basis": "测试", "evidence_urls": []},
            "platform_signals": [],
            "pool_topic": "公版测试故事",
        })
        with self.assertRaisesRegex(novel_candidate_pool.NovelCandidatePoolError, "needs evidence URLs"):
            novel_candidate_pool.validate_catalog(source)

    def test_rejects_rank_without_chart_size_or_future_snapshot(self):
        source = catalog()
        signal = source["candidates"][0]["platform_signals"][1]
        signal["chart_size"] = None
        with self.assertRaisesRegex(novel_candidate_pool.NovelCandidatePoolError, "requires chart_size"):
            novel_candidate_pool.validate_catalog(source)

        source = catalog()
        source["candidates"][0]["platform_signals"][0]["observed_at"] = "2026-09-17"
        with self.assertRaisesRegex(novel_candidate_pool.NovelCandidatePoolError, "after snapshot_date"):
            novel_candidate_pool.validate_catalog(source)

    def test_rejects_duplicate_chart_snapshots_and_missing_source_links(self):
        source = catalog()
        signals = source["candidates"][0]["platform_signals"]
        signals.append(dict(signals[1]))
        with self.assertRaisesRegex(novel_candidate_pool.NovelCandidatePoolError, "duplicates a platform/chart snapshot"):
            novel_candidate_pool.validate_catalog(source)

        source = catalog()
        source["candidates"][0]["platform_signals"][1]["source_url"] = None
        with self.assertRaisesRegex(novel_candidate_pool.NovelCandidatePoolError, "source_url must be"):
            novel_candidate_pool.validate_catalog(source)

        source = catalog()
        source["candidates"][0]["adaptation_source"]["source_url"] = None
        with self.assertRaisesRegex(novel_candidate_pool.NovelCandidatePoolError, "adaptation_source.source_url must be"):
            novel_candidate_pool.validate_catalog(source)

    def test_cli_writes_traceable_bundle_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "candidate-pool"
            command = [
                sys.executable,
                str(ROOT / "scripts" / "novel_candidate_pool.py"),
                str(CATALOG_PATH),
                "--output-dir",
                str(output_dir),
            ]
            first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue((output_dir / "trend-discovery.json").is_file())
            self.assertTrue((output_dir / "topic-pool.json").is_file())
            self.assertTrue((output_dir / "novel-candidate-pool.md").is_file())
            payload = json.loads((output_dir / "novel-candidate-pool.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["candidate_count"], 5)
            self.assertFalse(payload["main_ip_selected"])

            second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("refusing to overwrite", second.stderr)


if __name__ == "__main__":
    unittest.main()
