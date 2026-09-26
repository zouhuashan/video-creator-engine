"""Exercise the actual Web path from empty scenes through one local Shot preview."""

import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import scripts.web_server as web_server


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "projects/novel-0dbc8f5836"


class ModernHTTPWorkflowTest(unittest.TestCase):
    def test_web_rebuild_profile_split_edit_and_rerender(self):
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            project = project_root / PILOT.name
            for source in PILOT.rglob("*.json"):
                target = project / source.relative_to(PILOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            for path in (project / "writing-room/episodes").glob("*/script.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["episode_script"]["scenes"] = []
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            (project / "storyboard/shot-breakdown.json").unlink(missing_ok=True)
            with patch.object(web_server, "PROJECTS_ROOT", project_root):
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.VideoCreatorHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}/api/novel-anime/projects/{project.name}"

                def post(suffix, payload=None):
                    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
                    request = urllib.request.Request(base + suffix, data=body, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(request, timeout=20) as response:
                        return json.load(response)

                try:
                    rebuilt = post("/cost-first-routing/rebuild")
                    self.assertTrue(rebuilt["auto_backfilled_episode_scenes"])
                    self.assertTrue(rebuilt["auto_rebuilt_shot_breakdown"])
                    self.assertEqual(len(rebuilt["routes"]), 15)
                    profiled = post("/cost-first-routing/profile", {"render_profile": "modern_low_cost"})
                    self.assertEqual(profiled["render_profile"], "modern_low_cost")
                    split = post("/cost-first-routing/modern-split")
                    self.assertGreater(split["split"]["shot_count"], 15)
                    shot_id = split["plan"]["routes"][0]["shot_id"]
                    edit = post(f"/modern-timeline/shots/{shot_id}/edit", {"motion_strategy": "SCREEN_MG", "screen_mg": {"template": "chat", "title": "消息", "lines": ["今晚见"]}})
                    self.assertEqual(edit["shot"]["status"], "DIRTY")
                    rendered = post(f"/modern-timeline/shots/{shot_id}/rerender")
                    self.assertEqual(rendered["shot"]["status"], "PREVIEW_READY")
                    self.assertTrue((project / rendered["shot"]["preview"]["output"]).is_file())
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
