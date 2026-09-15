import unittest
import json
import tempfile
from pathlib import Path

from scripts.asset_router import choose_route, load_config, recover_missing_asset
from scripts.asset_manifest import write_asset_manifest
from scripts import project_state


class AssetRouterTests(unittest.TestCase):
    def test_uses_declared_priority(self):
        self.assertEqual(choose_route("real_video", ["generative_media", "licensed_media", "real_media"])["route"], "real_media")
        self.assertEqual(choose_route("real_video", ["generative_media", "licensed_media"])["route"], "licensed_media")

    def test_routes_hyperframes_and_returns_missing_when_unavailable(self):
        self.assertEqual(choose_route("chart", ["hyperframes", "generative_media"])["route"], "hyperframes")
        self.assertEqual(choose_route("ai_video", ["real_media"])["status"], "MISSING_ASSET")

    def test_missing_asset_recovery_uses_first_available_action(self):
        self.assertEqual(recover_missing_asset(["generate", "replace_with_infographic"])["next_action"], "generate")
        self.assertEqual(recover_missing_asset([])["next_action"], "request_user_material")

    def test_config_is_complete(self):
        config = load_config()
        self.assertEqual(config["priority"][0], "real_media")
        self.assertEqual(config["priority"][-1], "generative_media")

    def test_asset_manifest_computes_checksum_and_validates_scene(self):
        with tempfile.TemporaryDirectory() as temp:
            project_id = "20260915-assets-test"
            directory = Path(temp) / project_id
            directory.mkdir()
            project_state.initialize_run_state(directory, project_id)
            for target in ("RESEARCHED", "SCRIPTED", "STORYBOARDED"):
                project_state.transition_project(directory, project_id, target)
            (directory / "storyboard.json").write_text(json.dumps({"scenes": [{"scene_id": "SC001"}]}))
            (directory / "shot.png").write_bytes(b"asset")
            payload = {"schema_version": 1, "assets": [{"asset_id": "A001", "scene_id": "SC001", "type": "real_image", "path": "shot.png", "source": "user", "license": "owned", "generated": False, "provider": None}]}
            result = write_asset_manifest(directory, project_id, payload)
            manifest = json.loads((directory / "asset-manifest.json").read_text())
            self.assertEqual(result["asset_count"], 1)
            self.assertTrue(manifest["assets"][0]["checksum"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
