import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from adapters.workspaces.arcreel import ArcReelError, ArcReelWorkspace


class Handler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *_args):
        pass

    def _send(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.__class__.requests.append(("GET", self.path, self.headers.get("Authorization"), None))
        self._send({"status": "ok"} if self.path == "/health" else {"projects": []})

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(raw) if raw else None
        self.__class__.requests.append(("POST", self.path, self.headers.get("Authorization"), payload))
        self._send({"success": True, "name": payload.get("name")})

    def do_PUT(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.__class__.requests.append(("PUT", self.path, self.headers.get("Authorization"), raw.decode()))
        self._send({"success": True, "path": self.path})


class ArcReelWorkspaceTests(unittest.TestCase):
    def setUp(self):
        Handler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = ArcReelWorkspace(f"http://127.0.0.1:{self.server.server_port}", api_key="arc-secret")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_health_and_auth_header(self):
        self.assertEqual(self.client.health(), {"status": "ok"})
        self.assertEqual(Handler.requests[0][:3], ("GET", "/health", "Bearer arc-secret"))

    def test_create_project_uses_drama_novel_storyboard_contract(self):
        result = self.client.create_project(name="jinghua-yuan-series", title="镜花缘", style="工笔国风")
        self.assertTrue(result["success"])
        payload = Handler.requests[0][3]
        self.assertEqual(payload["content_mode"], "drama")
        self.assertEqual(payload["source_kind"], "novel")
        self.assertEqual(payload["generation_mode"], "storyboard")
        self.assertEqual(payload["aspect_ratio"], "9:16")

    def test_project_names_normalizes_project_listing(self):
        self.assertEqual(self.client.project_names(), [])

    def test_put_source_text_uses_plain_text_endpoint(self):
        result = self.client.put_source_text("jinghua-yuan-series", "source.txt", "第一回")
        self.assertTrue(result["success"])
        method, path, authorization, payload = Handler.requests[0]
        self.assertEqual((method, path, authorization), ("PUT", "/api/v1/projects/jinghua-yuan-series/source/source.txt", "Bearer arc-secret"))
        self.assertEqual(payload, "第一回")

    def test_rejects_non_http_origin(self):
        with self.assertRaises(ArcReelError):
            ArcReelWorkspace("file:///tmp/arcreel")


if __name__ == "__main__":
    unittest.main()
