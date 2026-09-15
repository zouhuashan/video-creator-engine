import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import project_state
from scripts.script_module import ScriptInputError, write_script_artifacts


ROOT = Path(__file__).resolve().parents[1]


class ScriptModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.temp_dir.name) / "projects"
        self.project_id = "20260915-script-test"
        self.directory = self.projects_dir / self.project_id
        self.directory.mkdir(parents=True)
        project_state.initialize_run_state(self.directory, self.project_id)
        project_state.transition_project(self.directory, self.project_id, "RESEARCHED")
        self.research = {
            "schema_version": 1,
            "topic": "可信主题",
            "research_status": "complete",
            "sources": [
                {
                    "source_id": "S001",
                    "title": "官方说明",
                    "url": "https://example.com/official",
                    "source_type": "official",
                },
                {
                    "source_id": "S002",
                    "title": "搜索摘要",
                    "url": "https://example.com/search",
                    "source_type": "search_summary",
                },
            ],
        }
        (self.directory / "research.json").write_text(json.dumps(self.research), encoding="utf-8")
        self.write_eligible_topic()
        self.payload = {
            "schema_version": 1,
            "sections": {
                "hook": {"narration": "开场。", "source_ids": []},
                "problem": {"narration": "问题。", "source_ids": []},
                "evidence": {"narration": "证据。", "source_ids": ["S001"]},
                "comparison": {"narration": "对比。", "source_ids": []},
                "conclusion": {"narration": "结论。", "source_ids": []},
                "cta": {"narration": "行动。", "source_ids": []},
            },
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_eligible_topic(self, **overrides):
        topic = {
            "schema_version": 1,
            "project_id": self.project_id,
            "topic": "可信主题",
            "total_score": 75,
            "minimum_total_score": 60,
            "decision": "eligible_for_production",
            "risk_filter": {"passed": True},
        }
        topic.update(overrides)
        (self.directory / "topic.json").write_text(json.dumps(topic), encoding="utf-8")

    def test_writes_six_sections_and_advances_to_scripted(self):
        result = write_script_artifacts(self.directory, self.project_id, self.payload)

        self.assertEqual(result["sections"], ["hook", "problem", "evidence", "comparison", "conclusion", "cta"])
        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "SCRIPTED")
        script = json.loads((self.directory / "script.json").read_text(encoding="utf-8"))
        self.assertEqual([section["title"] for section in script["sections"]], [
            "Hook", "Problem", "Evidence", "Comparison", "Conclusion", "CTA"
        ])
        self.assertEqual(script["sources"][0]["source_id"], "S001")
        markdown = (self.directory / "script.md").read_text(encoding="utf-8")
        self.assertLess(markdown.index("## Hook"), markdown.index("## Problem"))
        self.assertLess(markdown.index("## Problem"), markdown.index("## Evidence"))
        self.assertIn("依据（非口播）：[S001]", markdown)

    def test_rejects_missing_or_untrusted_evidence_without_mutation(self):
        self.payload["sections"]["evidence"]["source_ids"] = []
        with self.assertRaisesRegex(ScriptInputError, "must cite"):
            write_script_artifacts(self.directory, self.project_id, self.payload)
        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "RESEARCHED")
        self.assertFalse((self.directory / "script.json").exists())

        self.payload["sections"]["evidence"]["source_ids"] = ["S002"]
        with self.assertRaisesRegex(ScriptInputError, "search summary"):
            write_script_artifacts(self.directory, self.project_id, self.payload)

    def test_rejects_unknown_source_and_incomplete_sections(self):
        self.payload["sections"]["evidence"]["source_ids"] = ["S999"]
        with self.assertRaisesRegex(ScriptInputError, "unknown source"):
            write_script_artifacts(self.directory, self.project_id, self.payload)

        del self.payload["sections"]["cta"]
        with self.assertRaisesRegex(ScriptInputError, "exactly"):
            write_script_artifacts(self.directory, self.project_id, self.payload)

    def test_rejects_topic_gate_that_did_not_pass(self):
        self.write_eligible_topic(decision="do_not_enter_production")
        with self.assertRaisesRegex(ScriptInputError, "not eligible"):
            write_script_artifacts(self.directory, self.project_id, self.payload)
        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "RESEARCHED")

    def test_rejects_topic_score_below_declared_threshold(self):
        self.write_eligible_topic(total_score=59)
        with self.assertRaisesRegex(ScriptInputError, "does not meet"):
            write_script_artifacts(self.directory, self.project_id, self.payload)
        self.assertEqual(project_state.load_run_state(self.directory, self.project_id)["status"], "RESEARCHED")

    def test_requires_researched_project_stage(self):
        project_state.transition_project(self.directory, self.project_id, "SCRIPTED")
        with self.assertRaisesRegex(project_state.StateError, "requires status RESEARCHED"):
            write_script_artifacts(self.directory, self.project_id, self.payload)

    def test_refuses_to_overwrite_existing_script_artifact(self):
        existing = self.directory / "script.md"
        existing.write_text("保留", encoding="utf-8")
        with self.assertRaisesRegex(project_state.StateError, "refusing to overwrite"):
            write_script_artifacts(self.directory, self.project_id, self.payload)
        self.assertEqual(existing.read_text(encoding="utf-8"), "保留")

    def test_cli_writes_artifacts(self):
        input_file = Path(self.temp_dir.name) / "script-input.json"
        input_file.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "video_creator.py"),
                "script",
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
        self.assertEqual(json.loads(result.stdout)["state"], "SCRIPTED")
        self.assertTrue((self.directory / "script.json").is_file())
        self.assertTrue((self.directory / "script.md").is_file())


if __name__ == "__main__":
    unittest.main()
