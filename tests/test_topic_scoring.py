import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import project_id
import project_state
import research_module
import topic_scoring


def sourced_research():
    return {
        "topic": "A practical example topic",
        "source_mode": "provided_sources_only",
        "sources": [
            {
                "source_id": "S001",
                "title": "Official source",
                "publisher": "Example Organization",
                "url": "https://example.com/source",
                "source_type": "official",
            }
        ],
        "core_facts": [
            {
                "claim": "The product has a monthly plan.",
                "evidence": "The official page lists a monthly plan.",
                "source_ids": ["S001"],
            }
        ],
        "risks": [
            {
                "risk": "Pricing may change.",
                "severity": "medium",
                "evidence": "The page says current pricing may change.",
                "source_ids": ["S001"],
            }
        ],
    }


def assessment(scores=None):
    scores = scores or {
        "traffic_value": 80,
        "commercial_value": 60,
        "evergreen_score": 90,
        "production_cost": 40,
        "originality": 70,
    }
    return {
        "schema_version": 1,
        "ratings": {
            field: {"score": score, "rationale": f"Assessment rationale for {field}."}
            for field, score in scores.items()
        },
    }


class TopicScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.temp_dir.name) / "projects"
        self.project_id = project_id.reserve_project_id(
            "A practical example topic",
            "practical-example-topic",
            self.projects_dir,
            date_override="20260915",
        )
        self.directory = self.projects_dir / self.project_id
        research_module.write_research_artifacts(self.directory, self.project_id, sourced_research())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_weighted_score_reverses_cost_and_derives_evidence_and_risk(self):
        research = json.loads((self.directory / "research.json").read_text(encoding="utf-8"))
        result = topic_scoring.calculate_topic_score(
            research,
            assessment(),
            created_at="2026-09-15T00:00:00Z",
        )

        self.assertEqual(result["evidence_strength"], 100)
        self.assertEqual(result["risk_score"], 45)
        self.assertEqual(result["production_cost"], 40)
        self.assertEqual(result["production_cost_weighted_value"], 60)
        self.assertEqual(result["total_score"], 78)
        self.assertEqual(result["decision"], "eligible_for_production")
        self.assertEqual(result["risk_filter"]["passed"], True)
        self.assertEqual(result["created_at"], "2026-09-15T00:00:00Z")

    def test_low_total_and_high_risk_are_independent_gates(self):
        research = json.loads((self.directory / "research.json").read_text(encoding="utf-8"))
        boundary_score = topic_scoring.calculate_topic_score(
            research,
            assessment({
                "traffic_value": 50,
                "commercial_value": 50,
                "evergreen_score": 50,
                "production_cost": 25,
                "originality": 50,
            }),
        )
        self.assertEqual(boundary_score["total_score"], 60)
        self.assertEqual(boundary_score["decision"], "eligible_for_production")

        low_total = topic_scoring.calculate_topic_score(
            research,
            assessment({
                "traffic_value": 20,
                "commercial_value": 20,
                "evergreen_score": 20,
                "production_cost": 90,
                "originality": 20,
            }),
        )
        self.assertEqual(low_total["decision"], "do_not_enter_production")
        self.assertLess(low_total["total_score"], 60)

        research["risks"][0]["severity"] = "high"
        high_risk = topic_scoring.calculate_topic_score(research, assessment())
        self.assertEqual(high_risk["risk_score"], 75)
        self.assertEqual(high_risk["decision"], "blocked_by_risk_filter")
        self.assertGreaterEqual(high_risk["total_score"], 60)

    def test_evidence_strength_uses_cited_source_tier_not_assessment(self):
        research = json.loads((self.directory / "research.json").read_text(encoding="utf-8"))
        research["sources"][0]["source_type"] = "high_quality_community"
        result = topic_scoring.calculate_topic_score(research, assessment())
        self.assertEqual(result["evidence_strength"], 60)
        self.assertEqual(result["evidence_details"]["source_type_coverage"]["high_quality_community"], 1)

    def test_invalid_scores_and_unverified_citations_are_rejected(self):
        research = json.loads((self.directory / "research.json").read_text(encoding="utf-8"))
        bad_scores = assessment()
        bad_scores["ratings"]["traffic_value"]["score"] = 101
        with self.assertRaisesRegex(topic_scoring.TopicScoringError, "0 to 100"):
            topic_scoring.calculate_topic_score(research, bad_scores)

        research["core_facts"][0]["source_ids"] = ["S999"]
        with self.assertRaisesRegex(topic_scoring.TopicScoringError, "unknown source"):
            topic_scoring.calculate_topic_score(research, assessment())

        research["core_facts"][0]["source_ids"] = ["S001"]
        del research["risks"]
        with self.assertRaisesRegex(topic_scoring.TopicScoringError, "research.risks must be present"):
            topic_scoring.calculate_topic_score(research, assessment())

        research["risks"] = []
        research["core_facts"][0]["source_ids"] = ["S001"]
        research["sources"][0]["source_type"] = "search_summary"
        with self.assertRaisesRegex(topic_scoring.TopicScoringError, "search summary"):
            topic_scoring.calculate_topic_score(research, assessment())

    def test_cli_writes_topic_json_without_advancing_lifecycle_state(self):
        assessment_file = Path(self.temp_dir.name) / "assessment.json"
        assessment_file.write_text(json.dumps(assessment()), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "video_creator.py"),
                "score",
                self.project_id,
                "--assessment-file",
                str(assessment_file),
                "--projects-dir",
                str(self.projects_dir),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )

        cli_result = json.loads(result.stdout)
        saved_score = json.loads((self.directory / "topic.json").read_text(encoding="utf-8"))
        self.assertEqual(cli_result["decision"], "eligible_for_production")
        self.assertEqual(saved_score["total_score"], 78)
        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "RESEARCHED")
        with self.assertRaisesRegex(project_state.StateError, "refusing to overwrite"):
            topic_scoring.write_topic_score(self.directory, self.project_id, assessment())


if __name__ == "__main__":
    unittest.main()
