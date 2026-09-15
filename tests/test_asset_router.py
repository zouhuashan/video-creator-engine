import unittest

from scripts.asset_router import choose_route, load_config


class AssetRouterTests(unittest.TestCase):
    def test_uses_declared_priority(self):
        self.assertEqual(choose_route("real_video", ["generative_media", "licensed_media", "real_media"])["route"], "real_media")
        self.assertEqual(choose_route("real_video", ["generative_media", "licensed_media"])["route"], "licensed_media")

    def test_routes_hyperframes_and_returns_missing_when_unavailable(self):
        self.assertEqual(choose_route("chart", ["hyperframes", "generative_media"])["route"], "hyperframes")
        self.assertEqual(choose_route("ai_video", ["real_media"])["status"], "MISSING_ASSET")

    def test_config_is_complete(self):
        config = load_config()
        self.assertEqual(config["priority"][0], "real_media")
        self.assertEqual(config["priority"][-1], "generative_media")


if __name__ == "__main__":
    unittest.main()
