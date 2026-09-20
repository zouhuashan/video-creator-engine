import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import scripts.comfyui_installer as installer


class ComfyUIInstallerTests(unittest.TestCase):
    def test_choose_bootstrap_python_prefers_supported_versions(self):
        with patch.object(installer, "_python_candidates", return_value=["/opt/python3.13"]), \
             patch.object(installer, "_https_probe", return_value=(True, "")):
            self.assertEqual(installer.choose_bootstrap_python(), "/opt/python3.13")

    def test_runtime_recovers_tls_with_exported_macos_ca_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "macos-trust.pem"
            bundle.write_text("-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n", encoding="utf-8")
            probes = []

            def fake_probe(executable, env):
                probes.append(dict(env))
                return (bool(env.get("SSL_CERT_FILE")), "certificate verify failed")

            with patch.object(installer, "_python_candidates", return_value=["/opt/python3.13"]), \
                 patch.object(installer, "_export_macos_trust_bundle", return_value=bundle), \
                 patch.object(installer, "_candidate_ca_bundles", return_value=[bundle]), \
                 patch.object(installer, "_https_probe", side_effect=fake_probe):
                python, env, ca_source = installer.choose_bootstrap_runtime()

            self.assertEqual(python, "/opt/python3.13")
            self.assertEqual(env["SSL_CERT_FILE"], str(bundle))
            self.assertEqual(env["PIP_CERT"], str(bundle))
            self.assertEqual(env["REQUESTS_CA_BUNDLE"], str(bundle))
            self.assertEqual(ca_source, str(bundle))
            self.assertGreaterEqual(len(probes), 2)

    def test_start_background_install_never_uses_shell_or_user_command(self):
        process = Mock()
        process.pid = 24680
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(installer, "status", return_value={"status": "FAIL", "installed": False}), \
                 patch.object(installer, "LOG_DIR", root), \
                 patch.object(installer, "LOG_PATH", root / "install.log"), \
                 patch.object(installer, "STATE_PATH", root / "state.json"), \
                 patch.object(installer.subprocess, "Popen", return_value=process) as popen:
                result = installer.start_background_install()
        command = popen.call_args.args[0]
        self.assertEqual(command[0], installer.sys.executable)
        self.assertEqual(command[1], str(Path(installer.__file__).resolve()))
        self.assertEqual(command[2], "--install")
        self.assertNotIn("shell", popen.call_args.kwargs)
        self.assertEqual(result["action"], "STARTED")

    def test_install_flow_does_not_download_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / ".dependencies" / "ComfyUI"
            venv_python = install_dir / ".venv" / "bin" / "python"
            run_labels = []

            def fake_clone(log):
                install_dir.mkdir(parents=True)
                (install_dir / "main.py").write_text("print('fixture')\n", encoding="utf-8")
                (install_dir / "requirements.txt").write_text("requests\n", encoding="utf-8")

            def fake_venv(bootstrap_python, log, env):
                venv_python.parent.mkdir(parents=True)
                venv_python.write_text("", encoding="utf-8")
                return venv_python

            def fake_torch(python, log, env):
                run_labels.append("torch")

            def fake_requirements(python, log, env):
                run_labels.append("requirements")

            with patch.object(installer, "ROOT", root), \
                 patch.object(installer, "DEPENDENCIES", root / ".dependencies"), \
                 patch.object(installer, "INSTALL_DIR", install_dir), \
                 patch.object(installer, "LOG_DIR", root / "logs"), \
                 patch.object(installer, "LOG_PATH", root / "logs" / "install.log"), \
                 patch.object(installer, "STATE_PATH", root / "logs" / "state.json"), \
                 patch.object(installer.shutil, "which", return_value="/usr/bin/git"), \
                 patch.object(installer.shutil, "disk_usage", return_value=Mock(free=20 * 1024**3)), \
                 patch.object(installer, "choose_bootstrap_runtime", return_value=("/usr/bin/python3", {"PATH": "/usr/bin"}, "/etc/ssl/cert.pem")), \
                 patch.object(installer, "_clone_or_repair", side_effect=fake_clone), \
                 patch.object(installer, "_ensure_venv", side_effect=fake_venv), \
                 patch.object(installer, "_install_torch", side_effect=fake_torch), \
                 patch.object(installer, "_install_requirements", side_effect=fake_requirements), \
                 patch.object(installer, "_verify", return_value={"torch": "test", "mps_built": True, "mps_available": True}):
                result = installer.install()

            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["models_installed"])
            self.assertEqual(run_labels, ["torch", "requirements"])
            self.assertFalse((install_dir / "models" / "checkpoints").exists())

    def test_running_status_recovers_interrupted_installer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            log_path = root / "install.log"
            state_path.write_text('{"status":"RUNNING","step":"INSTALL_REQUIREMENTS","pid":12345}\n', encoding="utf-8")
            log_path.write_text("partial\n", encoding="utf-8")
            with patch.object(installer, "STATE_PATH", state_path), \
                 patch.object(installer, "LOG_PATH", log_path), \
                 patch.object(installer, "LOG_DIR", root), \
                 patch.object(installer, "INSTALL_DIR", root / "ComfyUI"), \
                 patch.object(installer, "_pid_alive", return_value=False):
                result = installer.status()
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["step"], "INTERRUPTED")


if __name__ == "__main__":
    unittest.main()
