import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import scripts.comfyui_model_manager as manager


class ComfyUIModelManagerTests(unittest.TestCase):
    def _fixture(self, root: Path, payload: bytes = b"checkpoint"):
        comfy = root / ".dependencies" / "ComfyUI"
        checkpoint_dir = comfy / "models" / "checkpoints"
        checkpoint_dir.mkdir(parents=True)
        (comfy / "main.py").write_text("fixture\n", encoding="utf-8")
        model = {
            "id": "fixture",
            "label": "Fixture",
            "purpose": "test",
            "filename": "fixture.safetensors",
            "source": "fixture",
            "source_page": "https://example.invalid/model",
            "download_url": "https://example.invalid/fixed.safetensors",
            "license": "test",
            "expected_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        return comfy, checkpoint_dir, model, payload

    def test_status_does_not_rehash_previously_verified_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comfy, checkpoint_dir, model, payload = self._fixture(root)
            target = checkpoint_dir / model["filename"]
            target.write_bytes(payload)
            state_path = root / "logs" / "state.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(
                '{"status":"PASS","step":"COMPLETE","model_id":"fixture","sha256":"%s"}\n' % model["sha256"],
                encoding="utf-8",
            )
            with patch.object(manager, "ROOT", root), \
                 patch.object(manager, "COMFYUI_DIR", comfy), \
                 patch.object(manager, "CHECKPOINT_DIR", checkpoint_dir), \
                 patch.object(manager, "LOG_DIR", root / "logs"), \
                 patch.object(manager, "LOG_PATH", root / "logs" / "model.log"), \
                 patch.object(manager, "STATE_PATH", state_path), \
                 patch.object(manager, "MODEL_CATALOG", {"fixture": model}), \
                 patch.object(manager, "_sha256", side_effect=AssertionError("status must not rehash")):
                result = manager.status("fixture")
            self.assertTrue(result["installed"])
            self.assertEqual(result["progress_percent"], 100.0)

    def test_install_verifies_checksum_before_atomic_move(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comfy, checkpoint_dir, model, payload = self._fixture(root)
            log_dir = root / "logs"

            def fake_download(current, log):
                (checkpoint_dir / (current["filename"] + ".part")).write_bytes(payload)

            with patch.object(manager, "ROOT", root), \
                 patch.object(manager, "COMFYUI_DIR", comfy), \
                 patch.object(manager, "CHECKPOINT_DIR", checkpoint_dir), \
                 patch.object(manager, "LOG_DIR", log_dir), \
                 patch.object(manager, "LOG_PATH", log_dir / "model.log"), \
                 patch.object(manager, "STATE_PATH", log_dir / "state.json"), \
                 patch.object(manager, "MODEL_CATALOG", {"fixture": model}), \
                 patch.object(manager.shutil, "disk_usage", return_value=Mock(free=10 * 1024**3)), \
                 patch.object(manager, "_download_with_curl", side_effect=fake_download):
                result = manager.install("fixture")

            target = checkpoint_dir / model["filename"]
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_bytes(), payload)
            self.assertFalse((checkpoint_dir / (model["filename"] + ".part")).exists())

    def test_bad_checksum_is_quarantined_and_never_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comfy, checkpoint_dir, model, payload = self._fixture(root)
            log_dir = root / "logs"

            def fake_download(current, log):
                bad = b"x" * len(payload)
                (checkpoint_dir / (current["filename"] + ".part")).write_bytes(bad)

            with patch.object(manager, "ROOT", root), \
                 patch.object(manager, "COMFYUI_DIR", comfy), \
                 patch.object(manager, "CHECKPOINT_DIR", checkpoint_dir), \
                 patch.object(manager, "LOG_DIR", log_dir), \
                 patch.object(manager, "LOG_PATH", log_dir / "model.log"), \
                 patch.object(manager, "STATE_PATH", log_dir / "state.json"), \
                 patch.object(manager, "MODEL_CATALOG", {"fixture": model}), \
                 patch.object(manager.shutil, "disk_usage", return_value=Mock(free=10 * 1024**3)), \
                 patch.object(manager, "_download_with_curl", side_effect=fake_download):
                with self.assertRaises(manager.ComfyUIModelError):
                    manager.install("fixture")

            self.assertFalse((checkpoint_dir / model["filename"]).exists())
            self.assertTrue(list(checkpoint_dir.glob("*.invalid-*")))

    def test_macos_system_proxy_is_detected_for_https_downloads(self):
        scutil_output = """<dictionary> {
  HTTPEnable : 1
  HTTPPort : 7897
  HTTPProxy : 127.0.0.1
  HTTPSEnable : 1
  HTTPSPort : 7897
  HTTPSProxy : 127.0.0.1
}
"""
        completed = Mock(returncode=0, stdout=scutil_output)
        with patch.object(manager.sys, "platform", "darwin"), \
             patch.object(manager.shutil, "which", side_effect=lambda name: "/usr/sbin/scutil" if name == "scutil" else None), \
             patch.object(manager.subprocess, "run", return_value=completed):
            proxies = manager._macos_system_proxies()
        self.assertIn("http://127.0.0.1:7897", proxies)

    def test_clash_verge_proxy_is_discovered_from_unix_socket(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verge_dir = root / "verge"
            verge_dir.mkdir()
            socket_path = verge_dir / "verge-mihomo.sock"
            socket_path.write_text("", encoding="utf-8")
            completed = Mock(
                returncode=0,
                stdout='{"mixed-port":7897,"port":0,"socks-port":7898}',
            )

            original_path = manager.Path
            def fake_path(value):
                if str(value) == "/tmp/verge":
                    return verge_dir
                if str(value) == "/tmp/verge/verge-mihomo.sock":
                    return socket_path
                if str(value) == "/tmp/verge/mihomo.sock":
                    return verge_dir / "mihomo.sock"
                return original_path(value)

            with patch.object(manager, "Path", side_effect=fake_path), \
                 patch.object(manager.shutil, "which", return_value="/usr/bin/curl"), \
                 patch.object(manager.subprocess, "run", return_value=completed) as run:
                proxies = manager._clash_verge_proxies()

            self.assertIn("http://127.0.0.1:7897", proxies)
            self.assertIn("socks5h://127.0.0.1:7898", proxies)
            command = run.call_args.args[0]
            self.assertIn("--unix-socket", command)
            self.assertIn("http://localhost/configs", command)

    def test_proxy_candidates_prefer_environment_and_dedupe_system_proxy(self):
        with patch.dict(manager.os.environ, {
            "HTTPS_PROXY": "http://127.0.0.1:7897",
            "ALL_PROXY": "socks5h://127.0.0.1:7898",
        }, clear=True), \
             patch.object(manager, "_clash_verge_proxies", return_value=["http://127.0.0.1:7897"]), \
             patch.object(manager, "_macos_system_proxies", return_value=["http://127.0.0.1:7897"]):
            proxies = manager._proxy_candidates()
        self.assertEqual(proxies, [
            "http://127.0.0.1:7897",
            "socks5h://127.0.0.1:7898",
        ])

    def test_proxy_logging_redacts_credentials(self):
        self.assertEqual(
            manager._redact_proxy("http://user:secret@127.0.0.1:7897"),
            "http://127.0.0.1:7897",
        )

    def test_download_route_prefers_detected_proxy_before_direct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []

            def fake_probe(curl, url, proxy, log):
                calls.append(proxy)
                return proxy == "http://127.0.0.1:7897"

            with patch.object(manager, "ROOT", root), \
                 patch.object(manager, "_proxy_candidates", return_value=["http://127.0.0.1:7897"]), \
                 patch.object(manager, "_probe_download_route", side_effect=fake_probe):
                with (root / "probe.log").open("wb") as log:
                    selected = manager._select_download_proxy("/usr/bin/curl", "https://example.invalid/file", log)

            self.assertEqual(selected, "http://127.0.0.1:7897")
            self.assertEqual(calls, ["http://127.0.0.1:7897"])

    def test_curl_download_is_fixed_allowlist_and_resumable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comfy, checkpoint_dir, model, payload = self._fixture(root)
            partial = checkpoint_dir / (model["filename"] + ".part")
            partial.write_bytes(payload[:3])
            completed = Mock(returncode=0)

            with patch.object(manager, "ROOT", root), \
                 patch.object(manager, "COMFYUI_DIR", comfy), \
                 patch.object(manager, "CHECKPOINT_DIR", checkpoint_dir), \
                 patch.object(manager.shutil, "which", return_value="/usr/bin/curl"), \
                 patch.object(manager, "_select_download_proxy", return_value="http://127.0.0.1:7897"), \
                 patch.object(manager.subprocess, "run", return_value=completed) as run:
                with (root / "download.log").open("wb") as log:
                    manager._download_with_curl(model, log)

            command = run.call_args.args[0]
            self.assertIn("--continue-at", command)
            self.assertEqual(command[command.index("--continue-at") + 1], "3")
            self.assertIn("--proxy", command)
            self.assertEqual(command[command.index("--proxy") + 1], "http://127.0.0.1:7897")
            self.assertEqual(command[-1], model["download_url"])
            self.assertNotIn("shell", run.call_args.kwargs)

    def test_background_installer_never_accepts_arbitrary_url(self):
        process = Mock()
        process.pid = 24680
        model = dict(manager.MODEL_CATALOG[manager.DEFAULT_MODEL_ID])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_dir = root / "logs"
            with patch.object(manager, "ROOT", root), \
                 patch.object(manager, "LOG_DIR", log_dir), \
                 patch.object(manager, "LOG_PATH", log_dir / "model.log"), \
                 patch.object(manager, "STATE_PATH", log_dir / "state.json"), \
                 patch.object(manager, "status", return_value={"status": "FAIL", "installed": False}), \
                 patch.object(manager.subprocess, "Popen", return_value=process) as popen:
                result = manager.start_background_install()

            command = popen.call_args.args[0]
            self.assertEqual(command[0], manager.sys.executable)
            self.assertEqual(command[1], str(Path(manager.__file__).resolve()))
            self.assertEqual(command[2:], ["--install", manager.DEFAULT_MODEL_ID])
            self.assertNotIn(model["download_url"], command)
            self.assertEqual(result["action"], "STARTED")


if __name__ == "__main__":
    unittest.main()
