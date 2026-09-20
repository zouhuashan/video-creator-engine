import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import scripts.comfyui_lora_manager as manager


class ComfyUILoraManagerTests(unittest.TestCase):
    def _fixture(self, root: Path, payload: bytes = b"lora-fixture"):
        comfy = root / ".dependencies" / "ComfyUI"
        lora_dir = comfy / "models" / "loras"
        lora_dir.mkdir(parents=True)
        (comfy / "main.py").write_text("fixture\n", encoding="utf-8")
        lora = {
            "id": "fixture",
            "label": "Fixture LoRA",
            "purpose": "test",
            "filename": "fixture.safetensors",
            "source": "fixture",
            "source_page": "https://example.invalid/model",
            "download_url": "https://example.invalid/fixed.safetensors",
            "license": "test",
            "base_model": "SDXL 1.0",
            "trigger_words": ["fixture"],
            "expected_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "default_strength": 0.7,
        }
        return comfy, lora_dir, lora, payload

    def test_catalog_uses_fixed_reviewed_guofeng_lora(self):
        lora = manager.LORA_CATALOG[manager.DEFAULT_LORA_ID]
        self.assertEqual(lora["filename"], "sdxl-chinese-style-illustration.safetensors")
        self.assertEqual(lora["expected_bytes"], 340768396)
        self.assertEqual(
            lora["sha256"],
            "5bc9ce5e0767a1dc2973056d32b1ca604408ff2c7cca38d145ae74d3742df584",
        )
        self.assertTrue(str(lora["download_url"]).startswith("https://huggingface.co/Muapi/"))

    def test_install_verifies_checksum_before_atomic_move(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comfy, lora_dir, lora, payload = self._fixture(root)
            log_dir = root / "logs"

            def fake_download(current, log):
                (lora_dir / (current["filename"] + ".part")).write_bytes(payload)

            with patch.object(manager, "ROOT", root), \
                 patch.object(manager, "COMFYUI_DIR", comfy), \
                 patch.object(manager, "LORA_DIR", lora_dir), \
                 patch.object(manager, "LOG_DIR", log_dir), \
                 patch.object(manager, "LOG_PATH", log_dir / "lora.log"), \
                 patch.object(manager, "STATE_PATH", log_dir / "state.json"), \
                 patch.object(manager, "LORA_CATALOG", {"fixture": lora}), \
                 patch.object(manager.shutil, "disk_usage", return_value=Mock(free=2 * 1024**3)), \
                 patch.object(manager, "_download_with_curl", side_effect=fake_download):
                result = manager.install("fixture")

            target = lora_dir / lora["filename"]
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_bytes(), payload)
            self.assertFalse((lora_dir / (lora["filename"] + ".part")).exists())

    def test_bad_checksum_is_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comfy, lora_dir, lora, payload = self._fixture(root)
            log_dir = root / "logs"

            def fake_download(current, log):
                (lora_dir / (current["filename"] + ".part")).write_bytes(b"x" * len(payload))

            with patch.object(manager, "ROOT", root), \
                 patch.object(manager, "COMFYUI_DIR", comfy), \
                 patch.object(manager, "LORA_DIR", lora_dir), \
                 patch.object(manager, "LOG_DIR", log_dir), \
                 patch.object(manager, "LOG_PATH", log_dir / "lora.log"), \
                 patch.object(manager, "STATE_PATH", log_dir / "state.json"), \
                 patch.object(manager, "LORA_CATALOG", {"fixture": lora}), \
                 patch.object(manager.shutil, "disk_usage", return_value=Mock(free=2 * 1024**3)), \
                 patch.object(manager, "_download_with_curl", side_effect=fake_download):
                with self.assertRaises(manager.ComfyUILoraError):
                    manager.install("fixture")

            self.assertFalse((lora_dir / lora["filename"]).exists())
            self.assertTrue(list(lora_dir.glob("*.invalid-*")))

    def test_background_installer_accepts_catalog_id_not_url(self):
        process = Mock(pid=24680)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_dir = root / "logs"
            with patch.object(manager, "ROOT", root), \
                 patch.object(manager, "LOG_DIR", log_dir), \
                 patch.object(manager, "LOG_PATH", log_dir / "lora.log"), \
                 patch.object(manager, "STATE_PATH", log_dir / "state.json"), \
                 patch.object(manager, "status", return_value={"status": "FAIL", "installed": False}), \
                 patch.object(manager.subprocess, "Popen", return_value=process) as popen:
                result = manager.start_background_install()

            command = popen.call_args.args[0]
            self.assertEqual(command[2:], ["--install", manager.DEFAULT_LORA_ID])
            self.assertNotIn(manager.LORA_CATALOG[manager.DEFAULT_LORA_ID]["download_url"], command)
            self.assertEqual(result["action"], "STARTED")


if __name__ == "__main__":
    unittest.main()
