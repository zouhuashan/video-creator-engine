import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import scripts.comfyui_service_manager as manager


class ComfyUIServiceManagerTests(unittest.TestCase):
    def test_managed_service_rejects_non_loopback_endpoint(self):
        with self.assertRaisesRegex(manager.ComfyUIServiceError, "local"):
            manager.start_service("http://192.168.1.20:8188")
        with self.assertRaisesRegex(manager.ComfyUIServiceError, "local"):
            manager.start_service("https://127.0.0.1:8188")

    def test_status_distinguishes_not_installed(self):
        with patch.object(manager, "discover_comfyui_home", return_value=None),              patch.object(manager, "_load_state", return_value={}),              patch.object(manager, "_endpoint_connected", return_value=False):
            result = manager.service_status("http://127.0.0.1:8188")
        self.assertEqual(result["state"], "NOT_INSTALLED")
        self.assertFalse(result["installed"])
        self.assertFalse(result["managed"])

    def test_start_uses_fixed_main_py_and_loopback_args(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "ComfyUI"
            home.mkdir()
            (home / "main.py").write_text("print('fixture')\n", encoding="utf-8")
            python = root / "python"
            python.write_text("", encoding="utf-8")
            python.chmod(0o755)

            process = Mock()
            process.pid = 43210
            process.poll.return_value = None
            captured = {}

            def fake_write_state(payload):
                captured.update(payload)

            with patch.object(manager, "discover_comfyui_home", return_value=home),                  patch.object(manager, "_python_for", return_value=python),                  patch.object(manager, "service_status", side_effect=[
                     {"connected": False, "managed": False, "state": "STOPPED"},
                     {"connected": False, "managed": True, "state": "STARTING"},
                 ]),                  patch.object(manager, "_write_state", side_effect=fake_write_state),                  patch.object(manager, "LOG_DIR", root / "logs"),                  patch.object(manager, "LOG_PATH", root / "logs" / "comfyui.log"),                  patch.object(manager.subprocess, "Popen", return_value=process) as popen,                  patch.object(manager.time, "sleep", return_value=None):
                result = manager.start_service("http://127.0.0.1:8188")

            command = popen.call_args.args[0]
            self.assertEqual(command[0], str(python))
            self.assertEqual(command[1], str(home / "main.py"))
            self.assertEqual(command[2:4], ["--listen", "127.0.0.1"])
            self.assertEqual(command[4:6], ["--port", "8188"])
            self.assertEqual(captured["pid"], 43210)
            self.assertEqual(captured["managed_by"], "videocreator")
            self.assertEqual(result["action"], "STARTED")

    def test_stop_refuses_external_comfyui_process(self):
        with patch.object(manager, "_load_state", return_value={}),              patch.object(manager, "_owned_process", return_value=False),              patch.object(manager.STATE_PATH, "unlink", return_value=None),              patch.object(manager, "service_status", return_value={"connected": True, "state": "RUNNING"}):
            with self.assertRaisesRegex(manager.ComfyUIServiceError, "外部 ComfyUI"):
                manager.stop_service("http://127.0.0.1:8188")


if __name__ == "__main__":
    unittest.main()
