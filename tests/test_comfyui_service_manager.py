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

    def test_python_for_preserves_venv_symlink_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "ComfyUI"
            venv_python = home / ".venv" / "bin" / "python"
            base_python = root / "managed-python" / "bin" / "python3.13"
            base_python.parent.mkdir(parents=True)
            base_python.write_text("", encoding="utf-8")
            base_python.chmod(0o755)
            venv_python.parent.mkdir(parents=True)
            venv_python.symlink_to(base_python)

            with patch.object(manager, "_desktop_base_path", return_value=(None, None)):
                selected = manager._python_for(home)

            self.assertEqual(selected, venv_python.absolute())
            self.assertNotEqual(selected, base_python.resolve())

    def test_project_venv_identity_rejects_base_interpreter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".dependencies" / "ComfyUI"
            python = home / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            completed = Mock(
                returncode=0,
                stdout=manager.json.dumps({
                    "prefix": "/managed/base",
                    "base_prefix": "/managed/base",
                    "executable": "/managed/base/bin/python3.13",
                }) + "\n",
                stderr="",
            )

            with patch.object(manager, "PROJECT_COMFYUI_HOME", home), \
                 patch.object(manager.subprocess, "run", return_value=completed):
                ok, detail = manager._venv_identity(python, home)

            self.assertFalse(ok)
            self.assertIn("not a virtual environment", detail)

    def test_project_venv_identity_accepts_exact_project_venv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".dependencies" / "ComfyUI"
            python = home / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            completed = Mock(
                returncode=0,
                stdout=manager.json.dumps({
                    "prefix": str(home / ".venv"),
                    "base_prefix": str(root / ".dependencies" / "python" / "base"),
                    "executable": str(python),
                }) + "\n",
                stderr="",
            )

            with patch.object(manager, "PROJECT_COMFYUI_HOME", home), \
                 patch.object(manager.subprocess, "run", return_value=completed):
                ok, detail = manager._venv_identity(python, home)

            self.assertTrue(ok)
            self.assertEqual(detail, "")

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

    def test_project_managed_start_repairs_missing_requirements_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".dependencies" / "ComfyUI"
            home.mkdir(parents=True)
            (home / "main.py").write_text("print('fixture')\n", encoding="utf-8")
            (home / "requirements.txt").write_text("filelock\n", encoding="utf-8")
            python = home / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            install_state_path = root / "logs" / "comfyui-install.json"
            install_state_path.parent.mkdir(parents=True)
            install_state_path.write_text(
                '{"status":"PASS","step":"COMPLETE","detail":"ok","ca_source":""}\n',
                encoding="utf-8",
            )

            with patch.object(manager, "PROJECT_COMFYUI_HOME", home), \
                 patch.object(manager, "INSTALL_STATE_PATH", install_state_path), \
                 patch.object(manager, "LOG_DIR", root / "logs"), \
                 patch.object(manager, "_venv_identity", return_value=(True, "")), \
                 patch.object(manager, "_runtime_dependency_smoke", side_effect=[
                     (False, "filelock: ModuleNotFoundError No module named filelock"),
                     (True, ""),
                 ]), \
                 patch.object(manager.subprocess, "run", return_value=Mock(returncode=0)) as run:
                with (root / "service.log").open("wb") as log:
                    result = manager._sync_project_dependencies(home, python, log)

            self.assertTrue(result["repaired"])
            command = run.call_args.args[0]
            self.assertEqual(command[:4], [str(python), "-m", "pip", "install"])
            self.assertIn(str(home / "requirements.txt"), command)
            updated = manager.json.loads(install_state_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["requirements_sha256"], manager._requirements_fingerprint(home))
            self.assertIn("dependencies_verified_at", updated)

    def test_project_dependency_sync_skips_when_hash_and_smoke_are_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / ".dependencies" / "ComfyUI"
            home.mkdir(parents=True)
            (home / "requirements.txt").write_text("filelock\n", encoding="utf-8")
            python = home / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            current_sha = manager._requirements_fingerprint(home)
            install_state_path = root / "logs" / "comfyui-install.json"
            install_state_path.parent.mkdir(parents=True)
            install_state_path.write_text(
                manager.json.dumps({"requirements_sha256": current_sha}) + "\n",
                encoding="utf-8",
            )

            with patch.object(manager, "PROJECT_COMFYUI_HOME", home), \
                 patch.object(manager, "INSTALL_STATE_PATH", install_state_path), \
                 patch.object(manager, "_venv_identity", return_value=(True, "")), \
                 patch.object(manager, "_runtime_dependency_smoke", return_value=(True, "")), \
                 patch.object(manager.subprocess, "run") as run:
                with (root / "service.log").open("wb") as log:
                    result = manager._sync_project_dependencies(home, python, log)

            self.assertFalse(result["repaired"])
            run.assert_not_called()

    def test_external_comfyui_dependencies_are_never_mutated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            managed_home = root / "managed" / "ComfyUI"
            external_home = root / "external" / "ComfyUI"
            managed_home.mkdir(parents=True)
            external_home.mkdir(parents=True)
            python = external_home / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")

            with patch.object(manager, "PROJECT_COMFYUI_HOME", managed_home), \
                 patch.object(manager.subprocess, "run") as run:
                with (root / "service.log").open("wb") as log:
                    result = manager._sync_project_dependencies(external_home, python, log)

            self.assertFalse(result["managed"])
            self.assertFalse(result["repaired"])
            run.assert_not_called()

    def test_stop_refuses_external_comfyui_process(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "comfyui-service.json"
            with patch.object(manager, "_load_state", return_value={}), patch.object(manager, "_owned_process", return_value=False), patch.object(manager, "STATE_PATH", state_path), patch.object(manager, "service_status", return_value={"connected": True, "state": "RUNNING"}):
                with self.assertRaisesRegex(manager.ComfyUIServiceError, "外部 ComfyUI"):
                    manager.stop_service("http://127.0.0.1:8188")


if __name__ == "__main__":
    unittest.main()
