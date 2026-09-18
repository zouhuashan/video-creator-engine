import copy
import unittest

from scripts.validate_animation_routes import (
    AnimationRouteConfigError,
    load_config,
    summary,
    validate_config,
)


class AnimationRouteConfigTests(unittest.TestCase):
    def test_default_route_is_local_non_generative_cutout(self):
        payload = load_config()
        self.assertEqual(payload["policy"]["default_route"], "LOCAL_CUTOUT_RIG")
        route = next(item for item in payload["routes"] if item["id"] == "LOCAL_CUTOUT_RIG")
        self.assertTrue(route["implemented"])
        self.assertFalse(route["remote"])
        self.assertFalse(route["generative"])
        self.assertEqual(summary(payload)["remote_generation_default_enabled"], False)

    def test_remote_ai_cannot_become_active_default(self):
        payload = load_config()
        broken = copy.deepcopy(payload)
        broken["policy"]["default_route"] = "REMOTE_AI_VIDEO"
        with self.assertRaisesRegex(AnimationRouteConfigError, "local and non-generative"):
            validate_config(broken)

    def test_remote_generation_requires_upload_and_billing_confirmation(self):
        payload = load_config()
        broken = copy.deepcopy(payload)
        broken["policy"]["remote_generation_requires"] = ["upload_authorized"]
        with self.assertRaisesRegex(AnimationRouteConfigError, "upload and billing confirmation"):
            validate_config(broken)


if __name__ == "__main__":
    unittest.main()
