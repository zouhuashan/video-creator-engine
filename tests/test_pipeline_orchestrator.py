import json
import tempfile
import unittest
from pathlib import Path

from scripts.pipeline_orchestrator import pipeline_status, run_pipeline, update_pipeline_review, PipelineError


class PipelineOrchestratorTests(unittest.TestCase):
    def test_dry_run_builds_machine_manifest_without_remote_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            projects = Path(directory)
            project = projects / "demo-project"
            project.mkdir()
            (project / "novel-anime-project.json").write_text('{"project_id":"demo-project"}\n', encoding="utf-8")

            result = run_pipeline("demo-project", dry_run=True, projects_root=projects)

            self.assertEqual(result["status"], "DRY_RUN_PASS")
            self.assertEqual(result["execution_mode"], "DRY_RUN")
            self.assertEqual(result["routing"]["blender_role"], "AUXILIARY_3D_CONTROL")
            self.assertTrue((project / "pipeline" / "run.json").is_file())
            self.assertTrue((project / "pipeline" / "prompts" / "SHOT-DEMO-001.txt").is_file())
            control = json.loads((project / "pipeline" / "scene-control" / "SHOT-DEMO-001.json").read_text(encoding="utf-8"))
            self.assertFalse(control["final_visual_allowed"])
            stages = {item["id"]: item for item in result["stages"]}
            self.assertEqual(stages["image"]["status"], "PLANNED")
            self.assertFalse(stages["subtitles"]["asr_round_trip"])
            self.assertTrue(stages["review"]["human_required"])

            status = pipeline_status("demo-project", projects)
            self.assertEqual(status["run_manifest"], "pipeline/run.json")
            with self.assertRaisesRegex(PipelineError, "not ready"):
                update_pipeline_review("demo-project", "APPROVED", projects_root=projects)


if __name__ == "__main__":
    unittest.main()
