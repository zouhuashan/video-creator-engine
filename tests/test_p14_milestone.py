import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.package_project import REQUIRED_FILES
from scripts.p14_milestone import evaluate_p14_03
from scripts.pilot_cover_rerun import rerun_cover
from scripts.project_state import STAGES, initialize_run_state, transition_project


class P14MilestoneTests(unittest.TestCase):
    def _fixture(self, root):
        ids, project_rows = [], []
        for number in range(20):
            project_id = f"20260916-p14-milestone-{number + 1}"
            directory = root / project_id
            directory.mkdir()
            initialize_run_state(directory, project_id)
            for stage in STAGES[1:STAGES.index("READY_FOR_REVIEW") + 1]:
                transition_project(directory, project_id, stage)
            files, package_rows = {}, []
            for name in REQUIRED_FILES:
                data = f"{project_id}-{name}".encode()
                files[name] = data
                (directory / name).write_bytes(data)
                package_rows.append({"name": name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            package_dir = directory / "publish-package"
            package_dir.mkdir()
            for name, data in files.items():
                (package_dir / name).write_bytes(data)
            package_rows_by_name = {item["name"]: item for item in package_rows}
            (directory / "package.json").write_text(json.dumps({"project_id": project_id, "auto_publish": False,
                                                                  "files": package_rows}))
            covers = directory / "covers"
            covers.mkdir()
            (covers / "cover_a.png").write_bytes(b"cover-a")
            (covers / "cover_b.png").write_bytes(b"cover-b")
            candidates = [{"candidate_id": candidate_id, "file": f"{candidate_id.lower()}.png",
                           "sha256": hashlib.sha256(data).hexdigest()}
                          for candidate_id, data in (("COVER_A", b"cover-a"), ("COVER_B", b"cover-b"))]
            (directory / "cover.png").write_bytes(b"cover-a")
            (package_dir / "cover.png").write_bytes(b"cover-a")
            package_rows_by_name["cover.png"].update({"size_bytes": len(b"cover-a"), "sha256": hashlib.sha256(b"cover-a").hexdigest()})
            (directory / "package.json").write_text(json.dumps({"project_id": project_id, "auto_publish": False,
                                                                  "files": list(package_rows_by_name.values())}))
            (directory / "cover-candidates.json").write_text(json.dumps({"schema_version": 1, "project_id": project_id,
                                                                           "selected": "COVER_A", "selected_sha256": hashlib.sha256(b"cover-a").hexdigest(),
                                                                           "candidates": candidates}))
            ids.append(project_id)
            project_rows.append({"project_id": project_id, "final_sha256": hashlib.sha256(files["final.mp4"]).hexdigest(),
                                 "production_elapsed_seconds": 18.0})
        rerun_cover(root / ids[0], ids[0], "COVER_B")
        report = {"status": "PASS", "verified_projects": 20, "projects": project_rows}
        review = {"projects": [{"project_id": project_id, "engineering_repair_required": False,
                                 "evidence": "QC passed without a project-specific engineering correction."} for project_id in ids]}
        return report, review

    def test_all_p14_gates_pass_with_twenty_ready_projects_and_real_rerun(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report, review = self._fixture(root)
            result = evaluate_p14_03(report, review, root)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["engineering_repairs"]["no_repair_ratio"], 1.0)
            self.assertEqual(result["partial_rerun"]["rerun_type"], "cover-only")

    def test_fails_when_repair_rate_or_average_production_time_misses_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report, review = self._fixture(root)
            for item in report["projects"]:
                item["production_elapsed_seconds"] = 31.0
            for item in review["projects"][:3]:
                item["engineering_repair_required"] = True
            result = evaluate_p14_03(report, review, root)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["production_time"]["status"], "FAIL")
            self.assertEqual(result["engineering_repairs"]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
