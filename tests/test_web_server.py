import os
import unittest
import json
import tempfile
import threading
import urllib.request
from pathlib import Path

import scripts.web_server as web_server
from scripts.novel_anime_project import build_project, write_project
from scripts.novel_anime_repository import NovelAnimeRepository
from scripts.novel_anime_runtime import NovelAnimeRuntime
from scripts.novel_source_catalog import build_catalog, write_catalog


class WebServerTests(unittest.TestCase):
    def test_provider_status_never_exposes_secret_values(self):
        previous = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "secret-value"
        try:
            providers = web_server._provider_status()
        finally:
            if previous is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous
        openai = next(provider for provider in providers if provider["id"] == "openai_sora")
        self.assertTrue(openai["configured"])
        self.assertNotIn("secret-value", str(openai))
        self.assertEqual(openai["env"], "OPENAI_API_KEY")

    def test_project_file_boundary_rejects_traversal(self):
        with self.assertRaises(ValueError):
            web_server._safe_project_file("jinghua-yuan-local-pilot", "../../.env.example")

    def test_project_file_resolves_known_asset(self):
        path = web_server._safe_project_file("jinghua-yuan-local-pilot", "assets/characters/tang-xiaoshan-portrait.png")
        self.assertTrue(path.is_file())

    def test_project_detail_exposes_local_episode_manifests(self):
        episodes = web_server._episode_metadata(web_server._safe_project("jinghua-yuan-local-pilot"))
        self.assertEqual([episode["episode_id"] for episode in episodes], [f"episode-{index:02d}" for index in range(1, 6)])
        self.assertTrue(all(str(episode["media_url"]).endswith("/final.mp4") for episode in episodes))

    def test_novel_anime_project_summary_uses_p18_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory) / "jinghua-yuan-series"
            write_project(project_dir, build_project("jinghua-yuan-series", "JHY", "镜花缘"))
            NovelAnimeRepository(project_dir).initialize()
            NovelAnimeRuntime(project_dir).initialize()
            write_catalog(project_dir, build_catalog("jinghua-yuan-series", "IP-JHY", "镜花缘"))
            projects = web_server._novel_anime_projects(Path(directory))
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["ip_id"], "IP-JHY")
        self.assertEqual(projects[0]["episode_ids"], [f"S01E{index:03d}" for index in range(1, 6)])
        self.assertEqual(projects[0]["repository"], {"entities": 8, "dependencies": 7, "asset_versions": 0, "snapshots": 0})
        self.assertEqual(projects[0]["runtime"]["migrations"], 0)
        self.assertEqual(projects[0]["source_catalog"]["status"], "UNASSESSED")
        self.assertFalse(projects[0]["source_catalog"]["publication_allowed"])

    def test_web_entrypoints_are_tracked_assets(self):
        self.assertTrue((web_server.WEB_ROOT / "index.html").is_file())
        self.assertTrue((web_server.WEB_ROOT / "app.js").is_file())
        self.assertTrue((web_server.WEB_ROOT / "styles.css").is_file())

    def test_key_settings_endpoint_returns_status_without_secret(self):
        web_server.RUNTIME_KEYS.pop("openai_sora", None)
        server = web_server.ThreadingHTTPServer(("127.0.0.1", 0), web_server.VideoCreatorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/api/settings/keys"
            request = urllib.request.Request(url, data=json.dumps({"provider": "openai_sora", "key": "test-key-123456"}).encode(), method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request) as response:
                result = json.loads(response.read().decode())
            self.assertEqual(result, {"provider": "openai_sora", "configured": True, "source": "session"})
            self.assertNotIn("test-key-123456", json.dumps(result))
        finally:
            web_server.RUNTIME_KEYS.pop("openai_sora", None)
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
