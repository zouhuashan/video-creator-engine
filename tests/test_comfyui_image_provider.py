import json
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from support.providers.comfyui_image_provider import ComfyUIImageError, ComfyUIImageProvider


class FakeComfyHandler(BaseHTTPRequestHandler):
    workflow = None
    client_id = None

    def log_message(self, *_args):
        pass

    def _json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/system_stats":
            return self._json({"system": {"comfyui_version": "test"}, "devices": [{"name": "test-gpu"}]})
        if parsed.path == "/object_info/CheckpointLoaderSimple":
            return self._json({"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["guofeng-test.safetensors"], {}]}}}})
        if parsed.path == "/history/prompt-1":
            return self._json({"prompt-1": {"outputs": {"7": {"images": [{"filename": "frame.png", "subfolder": "videocreator", "type": "output"}]}}}})
        if parsed.path == "/view":
            body = b"\x89PNG\r\n\x1a\nfake-local-image"
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self):  # noqa: N802
        if self.path != "/prompt":
            return self.send_error(404)
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode())
        type(self).workflow = payload["prompt"]
        type(self).client_id = payload.get("client_id")
        self._json({"prompt_id": "prompt-1", "number": 1})


class ComfyUIImageProviderTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeComfyHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_health_checkpoint_workflow_and_download(self):
        provider = ComfyUIImageProvider(self.base_url, timeout_seconds=2)
        health = provider.health()
        self.assertTrue(health["connected"])
        self.assertEqual(health["device_count"], 1)
        self.assertEqual(provider.available_checkpoints(), ["guofeng-test.safetensors"])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "frame.png"
            result = provider.generate(
                "premium guofeng animation frame",
                output,
                size="1024x1536",
                client_id="videocreator-test-client",
            )
            self.assertEqual(result["provider"], "comfyui_image")
            self.assertEqual(result["model"], "guofeng-test.safetensors")
            self.assertEqual(result["prompt_id"], "prompt-1")
            self.assertEqual(result["client_id"], "videocreator-test-client")
            self.assertEqual(FakeComfyHandler.client_id, "videocreator-test-client")
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 8)

        workflow = FakeComfyHandler.workflow
        self.assertEqual(workflow["1"]["class_type"], "CheckpointLoaderSimple")
        self.assertEqual(workflow["4"]["inputs"]["width"], 1024)
        self.assertEqual(workflow["4"]["inputs"]["height"], 1536)
        self.assertEqual(workflow["7"]["class_type"], "SaveImage")

    def test_image_payload_magic_validation(self):
        self.assertTrue(ComfyUIImageProvider._valid_image_payload(b"\x89PNG\r\n\x1a\nrest"))
        self.assertTrue(ComfyUIImageProvider._valid_image_payload(b"\xff\xd8\xffrest"))
        self.assertTrue(ComfyUIImageProvider._valid_image_payload(b"RIFF1234WEBPrest"))
        self.assertFalse(ComfyUIImageProvider._valid_image_payload(b"<html>proxy error</html>"))
        self.assertFalse(ComfyUIImageProvider._valid_image_payload(b""))

    def test_history_error_includes_comfyui_node_exception(self):
        provider = ComfyUIImageProvider(self.base_url, timeout_seconds=2)
        history = {
            "prompt-1": {
                "status": {
                    "status_str": "error",
                    "messages": [
                        [
                            "execution_error",
                            {
                                "node_type": "KSampler",
                                "exception_message": "MPS out of memory",
                            },
                        ]
                    ],
                }
            }
        }
        with self.assertRaisesRegex(ComfyUIImageError, "KSampler: MPS out of memory"):
            provider._first_output_image(history, "prompt-1")

    def test_default_generation_timeout_covers_recorded_mps_baseline(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "providers" / "comfyui-image-provider.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(float(config["timeout_seconds"]), 300.0)

    def test_generate_rejects_invalid_client_id(self):
        provider = ComfyUIImageProvider(self.base_url, timeout_seconds=2)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "frame.png"
            with self.assertRaisesRegex(Exception, "client_id"):
                provider.generate(
                    "test",
                    output,
                    size="1024x1024",
                    client_id="bad client id with spaces",
                )


if __name__ == "__main__":
    unittest.main()
