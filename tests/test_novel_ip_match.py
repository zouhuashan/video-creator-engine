import unittest
from pathlib import Path

from scripts.novel_ip_match import (
    NovelIpMatchError,
    analyze_snapshot_coverage,
    build_match_report,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_topic_pool():
    return {
        "schema_version": 1,
        "date": "2026-09-16",
        "candidates": [
            {"topic": "古代言情"},
            {"topic": "历史冒险"},
            {"topic": "玄幻仙侠"},
        ],
    }


def fixture_catalog():
    return {
        "schema_version": 1,
        "research_date": "2026-09-16",
        "target_territory": "CN-Mainland",
        "market_signals": [
            {"trend_tags": ["historical_romance", "fantasy_adventure"]},
        ],
        "works": [
            {
                "work_id": "JHY",
                "title": "镜花缘",
                "author": "李汝珍",
                "author_death_year": 1830,
                "source_edition": "1818 original",
                "edition_source_url": "https://example.org/scan",
                "territory": "CN-Mainland",
                "rights_gate": "pass_for_human_decision",
                "rights_evidence_urls": ["https://example.org/law"],
                "shortlist_eligible": True,
                "preproduction_scan_match_required": True,
                "topic_alignments": {"historical_romance": "adjacent", "fantasy_adventure": "direct"},
                "format_fit": {
                    "continuous_arc": 4,
                    "episode_hooks": 5,
                    "visual_worldbuilding": 5,
                    "adaptation_crowding_risk": 2,
                },
                "match_inference": "an editorial inference",
                "known_expression_risks": ["Use an independent design."],
            },
            {
                "work_id": "UNKNOWN",
                "title": "权利未知作品",
                "author": "未知",
                "author_death_year": None,
                "source_edition": "unknown edition",
                "edition_source_url": "https://example.org/unknown",
                "territory": "CN-Mainland",
                "rights_gate": "hold_for_exact_text_and_authorship_review",
                "rights_evidence_urls": [],
                "shortlist_eligible": False,
                "topic_alignments": {},
                "format_fit": {
                    "continuous_arc": 3,
                    "episode_hooks": 3,
                    "visual_worldbuilding": 3,
                    "adaptation_crowding_risk": 3,
                },
            },
        ],
    }


def fixture_snapshots():
    return {
        "schema_version": 1,
        "required_consecutive_periods_per_platform": 3,
        "platforms": [
            {
                "platform": "Qidian",
                "period_unit": "calendar_month",
                "snapshots": [
                    {"period": "2026-06", "scope_id": "m-ticket"},
                    {"period": "2026-07", "scope_id": "m-ticket"},
                    {"period": "2026-08", "scope_id": "m-ticket"},
                ],
            },
            {
                "platform": "Fanqie",
                "period_unit": "day",
                "snapshots": [
                    {"period": "2026-09-14", "scope_id": "read-a"},
                    {"period": "2026-09-15", "scope_id": "read-b"},
                ],
            },
        ],
    }


class NovelIpMatchTests(unittest.TestCase):
    def test_current_catalog_passes_only_rights_gate_candidates(self):
        catalog = __import__("json").loads((ROOT / "validation/classic-ip-catalog.json").read_text(encoding="utf-8"))
        shortlist = [work["work_id"] for work in catalog["works"] if work.get("shortlist_eligible")]
        self.assertEqual(shortlist, ["CLASSIC-JHY-001", "CLASSIC-LZ-001", "CLASSIC-MDT-001"])

    def test_only_verified_old_texts_enter_shortlist_and_no_ip_is_auto_selected(self):
        report = build_match_report(fixture_topic_pool(), fixture_catalog(), fixture_snapshots())
        self.assertEqual([item["work_id"] for item in report["shortlist"]], ["JHY"])
        self.assertEqual([item["work_id"] for item in report["excluded_pending_rights_or_source_review"]], ["UNKNOWN"])
        self.assertIsNone(report["main_ip_selected"])
        self.assertFalse(report["publication_allowed"])
        self.assertFalse(report["shortlist"][0]["production_allowed"])

    def test_snapshot_coverage_requires_three_consecutive_same_scope_periods(self):
        coverage = analyze_snapshot_coverage(fixture_snapshots())
        self.assertEqual(coverage["platforms"][0]["longest_consecutive_periods"], 3)
        self.assertEqual(coverage["platforms"][1]["longest_consecutive_periods"], 1)
        self.assertFalse(coverage["complete"])

    def test_gap_breaks_a_snapshot_series(self):
        snapshots = fixture_snapshots()
        qidian = snapshots["platforms"][0]
        qidian["snapshots"].pop(1)
        coverage = analyze_snapshot_coverage(snapshots)
        self.assertEqual(coverage["platforms"][0]["longest_consecutive_periods"], 1)

    def test_author_near_current_expiry_is_not_automatically_cleared(self):
        catalog = fixture_catalog()
        catalog["works"][0]["author_death_year"] = 1976
        with self.assertRaisesRegex(NovelIpMatchError, "claims shortlist eligibility"):
            build_match_report(fixture_topic_pool(), catalog, fixture_snapshots())

    def test_missing_source_evidence_cannot_claim_shortlist_eligibility(self):
        catalog = fixture_catalog()
        catalog["works"][0]["rights_evidence_urls"] = []
        with self.assertRaisesRegex(NovelIpMatchError, "claims shortlist eligibility"):
            build_match_report(fixture_topic_pool(), catalog, fixture_snapshots())


if __name__ == "__main__":
    unittest.main()
