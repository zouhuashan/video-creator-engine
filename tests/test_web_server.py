import os
import unittest

import scripts.web_server as web_server


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

    def test_web_entrypoints_are_tracked_assets(self):
        self.assertTrue((web_server.WEB_ROOT / "index.html").is_file())
        self.assertTrue((web_server.WEB_ROOT / "app.js").is_file())
        self.assertTrue((web_server.WEB_ROOT / "styles.css").is_file())


if __name__ == "__main__":
    unittest.main()
