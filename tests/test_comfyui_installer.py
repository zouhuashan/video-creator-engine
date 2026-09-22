import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import scripts.comfyui_installer as installer


class ComfyUIInstallerTests(unittest.TestCase):
    def test_uv_managed_python_install_is_project_private_and_arm64(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            managed_dir = root / "python"
            managed_bin = root / "python-bin"
            installed_python = managed_dir / installer.MANAGED_PYTHON_REQUEST / "bin" / "python3.13"
            calls = []

            def fake_run(command, *, cwd, log, label, env=None):
                calls.append((command, label, dict(env or {})))
                installed_python.parent.mkdir(parents=True, exist_ok=True)
                installed_python.write_text("", encoding="utf-8")

            with patch.object(installer, "MANAGED_PYTHON_DIR", managed_dir), \
                 patch.object(installer, "MANAGED_PYTHON_BIN_DIR", managed_bin), \
                 patch.object(installer, "_apple_silicon_host", return_value=True), \
                 patch.object(installer, "_find_uv", return_value="/usr/local/bin/uv"), \
                 patch.object(installer, "_python_runtime_healthy", return_value=(True, "")), \
                 patch.object(installer, "_run", side_effect=fake_run):
                with (root / "install.log").open("wb") as log:
                    result = installer._ensure_managed_python(log, {"SSL_CERT_FILE": "/tmp/cert.pem"})

            self.assertEqual(result, installed_python)
            command, label, env = calls[0]
            self.assertEqual(label, "INSTALL_MANAGED_PYTHON")
            self.assertIn(installer.MANAGED_PYTHON_REQUEST, command)
            self.assertIn("--install-dir", command)
            self.assertEqual(env["UV_PYTHON_INSTALL_DIR"], str(managed_dir))
            self.assertNotIn("UV_MANAGED_PYTHON", env)
            self.assertNotIn("UV_PYTHON_PREFERENCE", env)
            self.assertNotIn("UV_NO_MANAGED_PYTHON", env)

    def test_uv_managed_venv_uses_seed_and_exact_private_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / "ComfyUI"
            managed_python = root / "python" / "cpython-3.13-macos-aarch64-none" / "bin" / "python3.13"
            managed_python.parent.mkdir(parents=True)
            managed_python.write_text("", encoding="utf-8")
            calls = []

            def fake_run(command, *, cwd, log, label, env=None):
                calls.append((command, label))
                venv_python = install_dir / ".venv" / "bin" / "python"
                venv_python.parent.mkdir(parents=True, exist_ok=True)
                venv_python.write_text("", encoding="utf-8")

            with patch.object(installer, "INSTALL_DIR", install_dir), \
                 patch.object(installer, "_find_uv", return_value="/usr/local/bin/uv"), \
                 patch.object(installer, "_python_runtime_healthy", return_value=(True, "")), \
                 patch.object(installer, "_run", side_effect=fake_run):
                with (root / "install.log").open("wb") as log:
                    result = installer._create_uv_managed_venv(managed_python, log, {})

            command, label = calls[0]
            self.assertEqual(label, "CREATE_UV_MANAGED_VENV")
            self.assertIn("--seed", command)
            self.assertIn("--clear", command)
            self.assertIn(str(managed_python), command)
            self.assertEqual(result, install_dir / ".venv" / "bin" / "python")

    def test_install_prefers_uv_managed_python_on_apple_silicon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / ".dependencies" / "ComfyUI"
            managed_python = root / ".dependencies" / "python" / "cpython-3.13-macos-aarch64-none" / "bin" / "python3.13"
            venv_python = install_dir / ".venv" / "bin" / "python"
            system_runtime = Mock(side_effect=AssertionError("system runtime should not be selected"))

            def fake_clone(log):
                install_dir.mkdir(parents=True)
                (install_dir / "main.py").write_text("fixture\n", encoding="utf-8")
                (install_dir / "requirements.txt").write_text("requests\n", encoding="utf-8")

            def fake_managed(log, env):
                managed_python.parent.mkdir(parents=True, exist_ok=True)
                managed_python.write_text("", encoding="utf-8")
                return managed_python

            def fake_managed_venv(python, log, env):
                venv_python.parent.mkdir(parents=True, exist_ok=True)
                venv_python.write_text("", encoding="utf-8")
                return venv_python

            with patch.object(installer, "ROOT", root), \
                 patch.object(installer, "DEPENDENCIES", root / ".dependencies"), \
                 patch.object(installer, "INSTALL_DIR", install_dir), \
                 patch.object(installer, "LOG_DIR", root / "logs"), \
                 patch.object(installer, "LOG_PATH", root / "logs" / "install.log"), \
                 patch.object(installer, "STATE_PATH", root / "logs" / "state.json"), \
                 patch.object(installer.shutil, "which", return_value="/usr/bin/git"), \
                 patch.object(installer.shutil, "disk_usage", return_value=Mock(free=20 * 1024**3)), \
                 patch.object(installer, "_apple_silicon_host", return_value=True), \
                 patch.object(installer, "_ensure_managed_python", side_effect=fake_managed), \
                 patch.object(installer, "_create_uv_managed_venv", side_effect=fake_managed_venv), \
                 patch.object(installer, "_default_ca_bundle", return_value=None), \
                 patch.object(installer, "choose_bootstrap_runtime", system_runtime), \
                 patch.object(installer, "_clone_or_repair", side_effect=fake_clone), \
                 patch.object(installer, "_probe_requirements", return_value=None), \
                 patch.object(installer, "_install_torch", return_value="nightly"), \
                 patch.object(installer, "_install_requirements", return_value=None), \
                 patch.object(installer, "_verify", return_value={"torch": "test", "mps_built": True, "mps_available": True}):
                result = installer.install()

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["python_source"], "uv-managed-project-private")
            system_runtime.assert_not_called()

    def test_managed_uv_env_scrubs_mutually_exclusive_python_policy(self):
        env = installer._managed_uv_env({
            "UV_MANAGED_PYTHON": "1",
            "UV_PYTHON_PREFERENCE": "only-managed",
            "UV_NO_MANAGED_PYTHON": "1",
            "PATH": "/usr/bin",
        })
        self.assertNotIn("UV_MANAGED_PYTHON", env)
        self.assertNotIn("UV_PYTHON_PREFERENCE", env)
        self.assertNotIn("UV_NO_MANAGED_PYTHON", env)
        self.assertEqual(env["UV_NO_MODIFY_PATH"], "1")

    def test_apple_silicon_rejects_broken_arm64_system_python(self):
        with patch.object(installer.shutil, "which", side_effect=lambda name: "/opt/homebrew/python3.14" if name == "python3.14" else None), \
             patch.object(installer, "_python_version", return_value=(3, 14)), \
             patch.object(installer, "_apple_silicon_host", return_value=True), \
             patch.object(installer, "_python_machine", return_value="arm64"), \
             patch.object(installer, "_python_runtime_healthy", return_value=(False, "platform.mac_ver() returned empty value")), \
             patch.object(installer.sys, "executable", "/opt/homebrew/python3.14"):
            candidates = installer._python_candidates()
        self.assertNotIn("/opt/homebrew/python3.14", candidates)

    def test_apple_silicon_rejects_x86_python_candidate(self):
        with patch.object(installer.shutil, "which", side_effect=lambda name: {
                 "python3.13": "/opt/local/python3.13",
                 "python3.14": "/opt/homebrew/python3.14",
             }.get(name)), \
             patch.object(installer, "_python_version", return_value=(3, 13)), \
             patch.object(installer, "_apple_silicon_host", return_value=True), \
             patch.object(installer, "_python_machine", side_effect=lambda executable: "x86_64" if "opt/local" in executable else "arm64"), \
             patch.object(installer, "_python_runtime_healthy", return_value=(True, "")), \
             patch.object(installer.sys, "executable", "/opt/homebrew/python3.14"):
            candidates = installer._python_candidates()

        self.assertNotIn("/opt/local/python3.13", candidates)
        self.assertIn("/opt/homebrew/python3.14", candidates)

    def test_non_apple_host_does_not_apply_arm64_filter(self):
        with patch.object(installer.shutil, "which", side_effect=lambda name: "/usr/local/python3.13" if name == "python3.13" else None), \
             patch.object(installer, "_python_version", return_value=(3, 13)), \
             patch.object(installer, "_apple_silicon_host", return_value=False), \
             patch.object(installer.sys, "executable", "/usr/local/python3.13"):
            candidates = installer._python_candidates()
        self.assertIn("/usr/local/python3.13", candidates)

    def test_choose_bootstrap_python_prefers_supported_versions(self):
        with patch.object(installer, "_python_candidates", return_value=["/opt/python3.13"]), \
             patch.object(installer, "_https_probe", return_value=(True, "")), \
             patch.object(installer, "_default_ca_bundle", return_value=None):
            self.assertEqual(installer.choose_bootstrap_python(), "/opt/python3.13")

    def test_verified_default_python_ca_is_pinned_into_pip_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "cert.pem"
            bundle.write_text("fixture\n", encoding="utf-8")
            with patch.object(installer, "_python_candidates", return_value=["/opt/homebrew/python3.14"]), \
                 patch.object(installer, "_https_probe", return_value=(True, "")), \
                 patch.object(installer, "_default_ca_bundle", return_value=bundle):
                python, env, ca_source = installer.choose_bootstrap_runtime()
            self.assertEqual(python, "/opt/homebrew/python3.14")
            self.assertEqual(ca_source, str(bundle))
            self.assertEqual(env["SSL_CERT_FILE"], str(bundle))
            self.assertEqual(env["PIP_CERT"], str(bundle))
            self.assertEqual(env["REQUESTS_CA_BUNDLE"], str(bundle))

    def test_prefers_repaired_python_313_over_default_python_314(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "macos-trust.pem"
            bundle.write_text("fixture\n", encoding="utf-8")

            def fake_probe(executable, env):
                if executable.endswith("python3.13"):
                    return (bool(env.get("SSL_CERT_FILE")), "certificate verify failed")
                return (True, "")

            with patch.object(installer, "_python_candidates", return_value=["/opt/local/python3.13", "/opt/homebrew/python3.14"]), \
                 patch.object(installer, "_export_macos_trust_bundle", return_value=bundle), \
                 patch.object(installer, "_candidate_ca_bundles", return_value=[bundle]), \
                 patch.object(installer, "_https_probe", side_effect=fake_probe), \
                 patch.object(installer, "_default_ca_bundle", return_value=None):
                python, env, ca_source = installer.choose_bootstrap_runtime()

            self.assertEqual(python, "/opt/local/python3.13")
            self.assertEqual(env["PIP_CERT"], str(bundle))
            self.assertEqual(ca_source, str(bundle))

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

    def test_venv_runtime_drift_is_detected_even_when_version_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            venv_python = Path(directory) / "venv" / "bin" / "python"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_text("", encoding="utf-8")
            with patch.object(installer, "_python_identity", side_effect=[
                (3, 13, "/opt/homebrew/Frameworks/Python.framework/Versions/3.13"),
                (3, 13, "/opt/local/Library/Frameworks/Python.framework/Versions/3.13"),
            ]):
                matches, reason = installer._venv_matches_bootstrap(
                    venv_python,
                    "/opt/homebrew/bin/python3.13",
                    {},
                )
        self.assertFalse(matches)
        self.assertIn("runtime changed", reason)

    def test_create_venv_falls_back_to_without_pip_when_ensurepip_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / "ComfyUI"
            labels = []
            commands = []

            def fake_run(command, *, cwd, log, label, env=None):
                labels.append(label)
                commands.append(command)
                if label == "CREATE_VENV":
                    partial = install_dir / ".venv" / "bin" / "python"
                    partial.parent.mkdir(parents=True, exist_ok=True)
                    partial.write_text("partial", encoding="utf-8")
                    raise installer.ComfyUIInstallError("ensurepip failed")
                if label == "CREATE_VENV_NO_PIP":
                    python = install_dir / ".venv" / "bin" / "python"
                    python.parent.mkdir(parents=True, exist_ok=True)
                    python.write_text("new", encoding="utf-8")

            with patch.object(installer, "INSTALL_DIR", install_dir), \
                 patch.object(installer, "_run", side_effect=fake_run), \
                 patch.object(installer, "_bootstrap_venv_pip", return_value=None) as bootstrap:
                with (root / "install.log").open("wb") as log:
                    installer._create_venv("/opt/homebrew/python3.14", log, {"PATH": "/usr/bin"})

            self.assertEqual(labels, ["CREATE_VENV", "CREATE_VENV_NO_PIP"])
            self.assertIn("--without-pip", commands[1])
            bootstrap.assert_called_once()
            self.assertTrue((install_dir / ".venv" / "bin" / "python").is_file())

    def test_external_pip_bootstrap_targets_only_the_venv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / "ComfyUI"
            venv_python = install_dir / ".venv" / "bin" / "python"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_text("", encoding="utf-8")
            calls = []

            def fake_run(command, *, cwd, log, label, env=None):
                calls.append((command, label))

            with patch.object(installer, "INSTALL_DIR", install_dir), \
                 patch.object(installer, "_run", side_effect=fake_run):
                with (root / "install.log").open("wb") as log:
                    installer._bootstrap_venv_pip(
                        "/opt/homebrew/python3.14",
                        venv_python,
                        log,
                        {"PIP_CERT": "/tmp/cert.pem"},
                    )

            command, label = calls[0]
            self.assertEqual(label, "BOOTSTRAP_VENV_PIP")
            self.assertEqual(command[:5], [
                "/opt/homebrew/python3.14", "-m", "pip", "--python", str(venv_python)
            ])
            self.assertIn("install", command)

    def test_existing_venv_without_pip_is_bootstrapped_externally(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / "ComfyUI"
            python = install_dir / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            labels = []

            def fake_run(command, *, cwd, log, label, env=None):
                labels.append(label)

            with patch.object(installer, "INSTALL_DIR", install_dir), \
                 patch.object(installer, "_venv_matches_bootstrap", return_value=(True, "")), \
                 patch.object(installer, "_https_probe", return_value=(True, "")), \
                 patch.object(installer, "_pip_available", return_value=False), \
                 patch.object(installer, "_bootstrap_venv_pip", return_value=None) as bootstrap, \
                 patch.object(installer, "_run", side_effect=fake_run):
                with (root / "install.log").open("wb") as log:
                    result = installer._ensure_venv("/opt/homebrew/python3.14", log, {})

            self.assertEqual(result, python)
            bootstrap.assert_called_once_with("/opt/homebrew/python3.14", python, unittest.mock.ANY, {})
            self.assertEqual(labels, ["UPGRADE_PIP"])

    def test_stale_venv_is_deleted_and_recreated_before_pip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / "ComfyUI"
            old_python = install_dir / ".venv" / "bin" / "python"
            old_python.parent.mkdir(parents=True)
            old_python.write_text("stale", encoding="utf-8")
            marker = install_dir / ".venv" / "stale-marker"
            marker.write_text("old", encoding="utf-8")
            labels = []

            def fake_run(command, *, cwd, log, label, env=None):
                labels.append(label)
                if label == "CREATE_VENV":
                    python = install_dir / ".venv" / "bin" / "python"
                    python.parent.mkdir(parents=True, exist_ok=True)
                    python.write_text("new", encoding="utf-8")

            with patch.object(installer, "INSTALL_DIR", install_dir), \
                 patch.object(installer, "_venv_matches_bootstrap", return_value=(False, "Python version changed")), \
                 patch.object(installer, "_https_probe", return_value=(True, "")), \
                 patch.object(installer, "_pip_available", return_value=True), \
                 patch.object(installer, "_run", side_effect=fake_run):
                with (root / "install.log").open("wb") as log:
                    python = installer._ensure_venv("/opt/homebrew/python3.14", log, {})

            self.assertEqual(python, install_dir / ".venv" / "bin" / "python")
            self.assertFalse(marker.exists())
            self.assertEqual(labels, ["CREATE_VENV", "UPGRADE_PIP"])

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

    def test_install_falls_back_before_torch_when_requirements_are_incompatible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / ".dependencies" / "ComfyUI"
            venv_python = install_dir / ".venv" / "bin" / "python"
            runtime_calls = []
            torch_calls = []
            requirement_calls = []

            def fake_clone(log):
                install_dir.mkdir(parents=True)
                (install_dir / "main.py").write_text("print('fixture')\n", encoding="utf-8")
                (install_dir / "requirements.txt").write_text("comfy-angle\n", encoding="utf-8")

            def fake_runtime(excluded=None):
                excluded = set(excluded or set())
                runtime_calls.append(excluded)
                if "/opt/local/python3.12" not in excluded:
                    return "/opt/local/python3.12", {"PATH": "/usr/bin"}, "/tmp/macos-trust.pem"
                return "/opt/homebrew/python3.14", {"PATH": "/usr/bin"}, "/opt/homebrew/cert.pem"

            def fake_venv(bootstrap_python, log, env):
                venv_python.parent.mkdir(parents=True, exist_ok=True)
                venv_python.write_text(bootstrap_python, encoding="utf-8")
                return venv_python

            def fake_probe_requirements(python, log, env):
                current = python.read_text(encoding="utf-8")
                requirement_calls.append(current)
                if current == "/opt/local/python3.12":
                    raise installer.ComfyUIRequirementsUnavailable("No matching distribution found for comfy-angle")

            def fake_torch(python, log, env):
                torch_calls.append(python.read_text(encoding="utf-8"))
                return "nightly"

            with patch.object(installer, "ROOT", root), \
                 patch.object(installer, "DEPENDENCIES", root / ".dependencies"), \
                 patch.object(installer, "INSTALL_DIR", install_dir), \
                 patch.object(installer, "LOG_DIR", root / "logs"), \
                 patch.object(installer, "LOG_PATH", root / "logs" / "install.log"), \
                 patch.object(installer, "STATE_PATH", root / "logs" / "state.json"), \
                 patch.object(installer.shutil, "which", return_value="/usr/bin/git"), \
                 patch.object(installer.shutil, "disk_usage", return_value=Mock(free=20 * 1024**3)), \
                 patch.object(installer, "choose_bootstrap_runtime", side_effect=fake_runtime), \
                 patch.object(installer, "_clone_or_repair", side_effect=fake_clone), \
                 patch.object(installer, "_ensure_venv", side_effect=fake_venv), \
                 patch.object(installer, "_probe_requirements", side_effect=fake_probe_requirements), \
                 patch.object(installer, "_install_torch", side_effect=fake_torch), \
                 patch.object(installer, "_install_requirements", return_value=None), \
                 patch.object(installer, "_verify", return_value={"torch": "2.15.0.dev", "mps_built": True, "mps_available": True}):
                result = installer.install()

            self.assertEqual(requirement_calls, ["/opt/local/python3.12", "/opt/homebrew/python3.14"])
            self.assertEqual(torch_calls, ["/opt/homebrew/python3.14"])
            self.assertIn("/opt/local/python3.12", runtime_calls[1])
            self.assertEqual(result["status"], "PASS")

    def test_install_falls_back_to_next_python_when_torch_wheel_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / ".dependencies" / "ComfyUI"
            venv_python = install_dir / ".venv" / "bin" / "python"
            runtime_calls = []
            torch_calls = []

            def fake_clone(log):
                install_dir.mkdir(parents=True)
                (install_dir / "main.py").write_text("print('fixture')\n", encoding="utf-8")
                (install_dir / "requirements.txt").write_text("requests\n", encoding="utf-8")

            def fake_runtime(excluded=None):
                excluded = set(excluded or set())
                runtime_calls.append(excluded)
                if "/opt/local/python3.13" not in excluded:
                    return "/opt/local/python3.13", {"PATH": "/usr/bin"}, "/tmp/macos-trust.pem"
                return "/opt/homebrew/python3.14", {"PATH": "/usr/bin"}, "/opt/homebrew/cert.pem"

            def fake_venv(bootstrap_python, log, env):
                venv_python.parent.mkdir(parents=True, exist_ok=True)
                venv_python.write_text(bootstrap_python, encoding="utf-8")
                return venv_python

            def fake_torch(python, log, env):
                current = python.read_text(encoding="utf-8")
                torch_calls.append(current)
                if current == "/opt/local/python3.13":
                    raise installer.ComfyUITorchUnavailable("no compatible wheel")
                return "nightly"

            with patch.object(installer, "ROOT", root), \
                 patch.object(installer, "DEPENDENCIES", root / ".dependencies"), \
                 patch.object(installer, "INSTALL_DIR", install_dir), \
                 patch.object(installer, "LOG_DIR", root / "logs"), \
                 patch.object(installer, "LOG_PATH", root / "logs" / "install.log"), \
                 patch.object(installer, "STATE_PATH", root / "logs" / "state.json"), \
                 patch.object(installer.shutil, "which", return_value="/usr/bin/git"), \
                 patch.object(installer.shutil, "disk_usage", return_value=Mock(free=20 * 1024**3)), \
                 patch.object(installer, "choose_bootstrap_runtime", side_effect=fake_runtime), \
                 patch.object(installer, "_clone_or_repair", side_effect=fake_clone), \
                 patch.object(installer, "_ensure_venv", side_effect=fake_venv), \
                 patch.object(installer, "_probe_requirements", return_value=None), \
                 patch.object(installer, "_install_torch", side_effect=fake_torch), \
                 patch.object(installer, "_install_requirements", return_value=None), \
                 patch.object(installer, "_verify", return_value={"torch": "2.15.0.dev", "mps_built": True, "mps_available": True}):
                result = installer.install()

            self.assertEqual(torch_calls, ["/opt/local/python3.13", "/opt/homebrew/python3.14"])
            self.assertIn("/opt/local/python3.13", runtime_calls[1])
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["torch_channel"], "nightly")
            self.assertEqual(result["ca_source"], "/opt/homebrew/cert.pem")

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
                return "nightly"

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
                 patch.object(installer, "_probe_requirements", return_value=None), \
                 patch.object(installer, "_install_torch", side_effect=fake_torch), \
                 patch.object(installer, "_install_requirements", side_effect=fake_requirements), \
                 patch.object(installer, "_verify", return_value={"torch": "test", "mps_built": True, "mps_available": True}):
                result = installer.install()

            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["models_installed"])
            self.assertEqual(run_labels, ["torch", "requirements"])
            self.assertFalse((install_dir / "models" / "checkpoints").exists())

    def test_status_reports_models_installed_from_verified_model_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / "ComfyUI"
            venv_python = install_dir / ".venv" / "bin" / "python"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_text("", encoding="utf-8")
            (install_dir / "main.py").write_text("fixture\n", encoding="utf-8")
            checkpoint = install_dir / "models" / "checkpoints" / "fixture.safetensors"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_bytes(b"x")
            state_path = root / "install.json"
            model_state_path = root / "model.json"
            state_path.write_text('{"status":"PASS","step":"COMPLETE","models_installed":false}\n', encoding="utf-8")
            model_state_path.write_text(
                '{"status":"PASS","filename":"fixture.safetensors","sha256":"%s"}\n' % ("a" * 64),
                encoding="utf-8",
            )

            with patch.object(installer, "INSTALL_DIR", install_dir), \
                 patch.object(installer, "STATE_PATH", state_path), \
                 patch.object(installer, "MODEL_STATE_PATH", model_state_path), \
                 patch.object(installer, "LOG_DIR", root), \
                 patch.object(installer, "LOG_PATH", root / "install.log"):
                result = installer.status()

            self.assertTrue(result["models_installed"])
            self.assertTrue(result["model_checkpoint_present"])

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
