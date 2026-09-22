import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.graybox_manager as manager


class GrayboxManagerTelemetryTests(unittest.TestCase):
    def test_tail_log_returns_recent_lines_and_latest_blender_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_dir = root / "logs"
            log_dir.mkdir()
            project = root / "project-a"
            project.mkdir()
            path = log_dir / "graybox-project-a.log"
            path.write_text(
                "\n".join([
                    "Blender 4.x",
                    "Fra:1 Mem:12.00M | Time:00:00.10",
                    "Fra:17 Mem:12.10M | Time:00:01.70",
                    "Fra:42 Mem:12.20M | Time:00:04.20",
                ]) + "\n",
                encoding="utf-8",
            )
            with patch.object(manager, "LOG_DIR", log_dir):
                result = manager._tail_log(project, max_lines=10)
            self.assertEqual(result["frame_from_log"], 42)
            self.assertIn("Fra:42", result["text"])
            self.assertIsNotNone(result["updated_seconds_ago"])

    def test_blender_graybox_uses_blender_5_slotted_action_api(self):
        script = (manager.ROOT / "scripts" / "blender_graybox_scene.py").read_text(encoding="utf-8")
        self.assertIn("animdata_get_channelbag_for_assigned_slot", script)
        self.assertIn('getattr(action, "fcurves", None)', script)
        self.assertNotIn("obj.animation_data.action.fcurves", script)
        self.assertIn("keeping Blender default interpolation", script)

    def test_progress_reader_accepts_per_frame_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            progress = project / "graybox" / "render-progress.json"
            progress.parent.mkdir(parents=True)
            progress.write_text(
                '{"status":"RUNNING","current_frame":96,"total_frames":192,"updated_at_epoch":' + str(time.time()) + '}',
                encoding="utf-8",
            )
            result = manager._read_progress(project)
            self.assertEqual(result["current_frame"], 96)
            self.assertEqual(result["total_frames"], 192)


if __name__ == "__main__":
    unittest.main()
