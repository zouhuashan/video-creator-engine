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


def research_payload():
    return {
        "topic": "Example device subscription",
        "source_mode": "provided_sources_only",
        "sources": [
            {
                "source_id": "S001",
                "title": "Official product page",
                "publisher": "Example Inc.",
                "url": "https://example.com/product",
                "source_type": "official",
                "published_at": "2026-01-01",
                "accessed_at": "2026-09-15",
            }
        ],
        "core_facts": [
            {
                "id": "F001",
                "claim": "The listed monthly price is 20 yuan.",
                "evidence": "The product page lists a monthly price of 20 yuan.",
                "source_ids": ["S001"],
            }
        ],
        "user_faqs": [
            {
                "question": "How much does it cost?",
                "answer": "The listed monthly price is 20 yuan.",
                "evidence": "The product page lists a monthly price of 20 yuan.",
                "source_ids": ["S001"],
            }
        ],
        "viewpoints": {
            "positive": [{"claim": "The plan is billed monthly.", "evidence": "Billing is monthly.", "source_ids": ["S001"]}],
            "negative": [],
        },
        "price_spec_versions": [
            {
                "item": "Monthly plan",
                "value": "20 yuan, checked 2026-09-15",
                "checked_at": "2026-09-15",
                "evidence": "The product page lists a monthly price of 20 yuan.",
                "source_ids": ["S001"],
            }
        ],
        "asset_directions": ["Show the official product pricing page on screen."],
        "risks": [
            {
                "risk": "The listed price may change.",
                "severity": "medium",
                "evidence": "The page states that current pricing may change.",
                "source_ids": ["S001"],
            }
        ],
    }


class ResearchModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.temp_dir.name) / "projects"
        self.project_id = project_id.reserve_project_id(
            "Example device subscription",
            "example-device-subscription",
            self.projects_dir,
            date_override="20260915",
        )
        self.directory = self.projects_dir / self.project_id

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_writes_all_artifacts_and_advances_state_after_validation(self):
        result = research_module.write_research_artifacts(self.directory, self.project_id, research_payload())

        self.assertEqual(result["status"], "RESEARCHED")
        self.assertEqual(result["outputs"], ["research.json", "research.md", "sources.md"])
        self.assertEqual(result["source_count"], 1)
        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "RESEARCHED")
        data = json.loads((self.directory / "research.json").read_text(encoding="utf-8"))
        self.assertEqual(data["core_facts"][0]["source_ids"], ["S001"])
        report = (self.directory / "research.md").read_text(encoding="utf-8")
        self.assertIn("正面观点", report)
        self.assertIn("价格、规格与版本", report)
        self.assertIn("风险信息", report)
        self.assertIn("[S001]", report)
        sources = (self.directory / "sources.md").read_text(encoding="utf-8")
        self.assertIn("https://example.com/product", sources)
        self.assertIn("查阅时间：2026-09-15", sources)

    def test_unknown_source_reference_fails_without_outputs_or_state_change(self):
        payload = research_payload()
        payload["core_facts"][0]["source_ids"] = ["S999"]

        with self.assertRaisesRegex(research_module.ResearchInputError, "unknown source ID"):
            research_module.write_research_artifacts(self.directory, self.project_id, payload)

        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "CREATED")
        for name in research_module.OUTPUT_NAMES:
            self.assertFalse((self.directory / name).exists())

    def test_unverifiable_source_and_missing_core_fact_are_rejected(self):
        payload = research_payload()
        payload["sources"][0]["url"] = "javascript:alert(1)"
        with self.assertRaisesRegex(research_module.ResearchInputError, "absolute http or https"):
            research_module.normalize_research_input(payload)

        payload = research_payload()
        payload["sources"][0]["url"] = "https://user:secret@example.com/product"
        with self.assertRaisesRegex(research_module.ResearchInputError, "embedded credentials"):
            research_module.normalize_research_input(payload)

        payload = research_payload()
        payload["core_facts"] = []
        with self.assertRaisesRegex(research_module.ResearchInputError, "at least one source-backed"):
            research_module.normalize_research_input(payload)

        payload = research_payload()
        payload["risks"][0]["severity"] = "urgent"
        with self.assertRaisesRegex(research_module.ResearchInputError, "severity must be one of"):
            research_module.normalize_research_input(payload)

    def test_source_priority_orders_citations_and_is_recorded(self):
        payload = research_payload()
        payload["sources"].insert(
            0,
            {
                "source_id": "S002",
                "title": "Community test report",
                "publisher": "Example Community",
                "url": "https://community.example.com/test",
                "source_type": "high_quality_community",
            },
        )
        payload["core_facts"][0]["source_ids"] = ["S002", "S001"]

        normalized = research_module.normalize_research_input(payload)

        self.assertEqual(normalized["core_facts"][0]["source_ids"], ["S001", "S002"])
        self.assertEqual(
            [(item["source_type"], item["priority_rank"]) for item in normalized["sources"]],
            [("official", 1), ("high_quality_community", 4)],
        )
        self.assertEqual([item["source_id"] for item in normalized["sources"]], ["S001", "S002"])
        self.assertEqual([item["rank"] for item in normalized["source_policy"]], [1, 2, 3, 4, 5])
        report = research_module.render_research_markdown(normalized)
        self.assertIn("官方来源 > 原始文档 > 权威媒体 > 高质量社区 > 搜索摘要", report)
        self.assertLess(report.index("[S001]"), report.index("[S002]"))
        source_list = research_module.render_sources_markdown(normalized)
        self.assertLess(source_list.index("官方来源"), source_list.index("高质量社区"))

    def test_search_summary_cannot_support_claims_and_unknown_tier_is_rejected(self):
        payload = research_payload()
        payload["sources"][0]["source_type"] = "search_summary"
        with self.assertRaisesRegex(research_module.ResearchInputError, "open a source page"):
            research_module.normalize_research_input(payload)

        payload = research_payload()
        payload["sources"][0]["source_type"] = "personal_blog"
        with self.assertRaisesRegex(research_module.ResearchInputError, "source_type must be one of"):
            research_module.normalize_research_input(payload)

    def test_existing_outputs_and_wrong_stage_are_not_overwritten(self):
        self.advance_to("RESEARCHED")
        with self.assertRaisesRegex(project_state.StateError, "requires status CREATED"):
            research_module.write_research_artifacts(self.directory, self.project_id, research_payload())

        fresh_id = project_id.reserve_project_id(
            "Second example",
            "second-example",
            self.projects_dir,
            date_override="20260915",
        )
        fresh_directory = self.projects_dir / fresh_id
        (fresh_directory / "research.md").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(project_state.StateError, "refusing to overwrite"):
            research_module.write_research_artifacts(fresh_directory, fresh_id, research_payload())
        self.assertEqual((fresh_directory / "research.md").read_text(encoding="utf-8"), "keep")

    def test_cli_reads_research_input_and_writes_project_files(self):
        input_file = Path(self.temp_dir.name) / "brief.json"
        input_file.write_text(json.dumps(research_payload()), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "video_creator.py"),
                "research",
                self.project_id,
                "--input-file",
                str(input_file),
                "--projects-dir",
                str(self.projects_dir),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        result_data = json.loads(result.stdout)
        self.assertEqual(result_data["status"], "RESEARCHED")
        self.assertTrue((self.directory / "research.json").is_file())

    def advance_to(self, status):
        for target in project_state.STAGES[1 : project_state.STAGES.index(status) + 1]:
            project_state.transition_project(self.directory, self.project_id, target)


if __name__ == "__main__":
    unittest.main()
