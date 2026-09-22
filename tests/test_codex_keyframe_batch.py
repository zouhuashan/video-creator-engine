import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import scripts.codex_keyframe_batch as batch


class CodexKeyframeBatchTests(unittest.TestCase):
    def manifest(self, project: Path):
        root = project / "graybox" / "gpt-keyframes" / "GB-SHOT-001"
        for directory in ("control", "generated", "normalized"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        char = project / "refs" / "character.png"
        scene = project / "refs" / "scene.png"
        char.parent.mkdir(parents=True, exist_ok=True)
        char.write_bytes(b"x" * 256)
        scene.write_bytes(b"x" * 256)
        frames = []
        for index in range(3):
            control = root / "control" / f"KF-{index:03d}.png"
            control.write_bytes(b"x" * 256)
            frames.append({
                "id": f"GPT-KF-{index:03d}",
                "index": index,
                "status": "CONTROL_READY",
                "reference_mode": "CANONICAL_RESET" if index in (0, 2) else "PREVIOUS_CONTINUITY",
                "previous_index": None if index in (0, 2) else 0,
                "control_path": control.relative_to(project).as_posix(),
                "generated_path": "",
                "prompt": f"frame {index}",
            })
        payload = {
            "schema_version": 1,
            "shot_spec_id": "GB-SHOT-001",
            "character_reference": char.relative_to(project).as_posix(),
            "scene_reference": scene.relative_to(project).as_posix(),
            "keyframe_count": 3,
            "generated_count": 0,
            "frames": frames,
        }
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def test_start_requires_usage_and_reference_upload_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.manifest(project)
            with patch.object(batch, "codex_executable", return_value="/usr/local/bin/codex"):
                with self.assertRaisesRegex(batch.CodexKeyframeBatchError, "套餐用量"):
                    batch.start(project, confirm_codex_usage=False, confirm_reference_upload=True)
                with self.assertRaisesRegex(batch.CodexKeyframeBatchError, "允许将人物"):
                    batch.start(project, confirm_codex_usage=True, confirm_reference_upload=False)

    def test_eligible_frames_runs_resets_before_continuity_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            manifest = self.manifest(project)
            self.assertEqual(batch._eligible_frames(manifest), [0, 2])
            manifest["frames"][0]["status"] = "READY"
            self.assertEqual(batch._eligible_frames(manifest), [1, 2])

    def test_codex_command_attaches_all_reference_images_before_exec(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            manifest = self.manifest(project)
            root = project / "graybox" / "gpt-keyframes" / "GB-SHOT-001"
            previous = root / "normalized" / "KF-000.png"
            previous.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 256)
            manifest["frames"][0]["status"] = "READY"
            manifest["frames"][0]["generated_path"] = previous.relative_to(project).as_posix()
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            captured = {}
            class FakeProcess:
                returncode = 0
                def poll(self): return 0

            def fake_popen(command, **kwargs):
                captured["command"] = command
                raw = root / batch.RAW_DIR_NAME / "KF-001.png"
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 256)
                return FakeProcess()

            fake_result = json.loads(json.dumps(manifest))
            fake_result["frames"][1]["status"] = "READY"
            fake_result["frames"][1]["generated_path"] = "graybox/gpt-keyframes/GB-SHOT-001/normalized/KF-001.png"
            cancel = threading.Event()
            run = {"processes": {}}
            with patch.object(batch, "codex_executable", return_value="/usr/local/bin/codex"), \
                 patch.object(batch.p35, "load_graybox_spec", return_value={"id": "GB-SHOT-001"}), \
                 patch.object(batch.subprocess, "Popen", side_effect=fake_popen), \
                 patch.object(batch.p35, "upload_generated_frame", return_value=fake_result):
                index, ok, _ = batch._run_one_frame(project, "GB-SHOT-001", 1, cancel, run)

            self.assertEqual(index, 1)
            self.assertTrue(ok)
            command = captured["command"]
            self.assertEqual(command[0], "/usr/local/bin/codex")
            self.assertEqual(command.count("--image"), 4)
            self.assertIn("exec", command)
            self.assertIn("--sandbox", command)
            self.assertIn("workspace-write", command)
            self.assertIn("--ephemeral", command)

    def test_status_marks_restarted_running_batch_interrupted_without_losing_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            manifest = self.manifest(project)
            manifest["frames"][0]["status"] = "READY"
            root = project / "graybox" / "gpt-keyframes" / "GB-SHOT-001"
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            batch._atomic_json(root / batch.STATUS_NAME, {"status": "RUNNING", "active_indices": [1]})
            with patch.object(batch, "codex_executable", return_value="/usr/local/bin/codex"), \
                 patch.object(batch.p35, "load_graybox_spec", return_value={"id": "GB-SHOT-001"}):
                result = batch.status(project)
            self.assertEqual(result["status"], "INTERRUPTED")
            self.assertEqual(result["completed_count"], 1)


if __name__ == "__main__":
    unittest.main()
