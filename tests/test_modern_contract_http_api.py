import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import scripts.web_server as web_server


class ModernContractHTTPAPITest(unittest.TestCase):
    def test_build_get_and_review_contract_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "demo-modern"
            project.mkdir()
            built = {
                "schema_version": 1,
                "project_id": project.name,
                "render_profile": "modern_low_cost",
                "freshness": "FRESH",
                "summary": {"shot_count": 1, "stages": {}},
                "shots": [{"shot_id": "SHOT-001"}],
            }
            reviewed = {**built, "shots": [{"shot_id": "SHOT-001", "reviewed": True}]}

            with (
                patch.object(web_server, "PROJECTS_ROOT", root),
                patch.object(web_server, "write_modern_drama_contract", return_value=built) as build_mock,
                patch.object(web_server, "load_modern_drama_contract", return_value=built) as load_mock,
                patch.object(web_server, "review_modern_drama_shot", return_value=reviewed) as review_mock,
            ):
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.VideoCreatorHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}/api/novel-anime/projects/{project.name}/modern-production-contract"

                def post(url: str, payload: dict) -> dict:
                    request = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(request, timeout=10) as response:
                        self.assertEqual(response.status, 201)
                        return json.load(response)

                try:
                    with urllib.request.urlopen(base, timeout=10) as response:
                        self.assertEqual(json.load(response)["freshness"], "FRESH")
                    created = post(base + "/build", {})
                    self.assertEqual(created["project_id"], project.name)
                    result = post(base + "/review", {
                        "shot_id": "SHOT-001",
                        "stage": "storyboard",
                        "status": "APPROVED",
                        "note": "web smoke",
                    })
                    self.assertTrue(result["shots"][0]["reviewed"])
                    build_mock.assert_called_once_with(project)
                    load_mock.assert_called_once_with(project)
                    review_mock.assert_called_once_with(
                        project,
                        shot_id="SHOT-001",
                        stage="storyboard",
                        status="APPROVED",
                        note="web smoke",
                    )
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
