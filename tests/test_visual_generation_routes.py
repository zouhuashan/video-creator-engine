import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VisualGenerationRouteTests(unittest.TestCase):
    def test_final_visual_is_provider_routed_and_blender_is_auxiliary(self):
        payload = json.loads((ROOT / "config" / "visual-generation-routes.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["policy"]["final_visual_route"], "IMAGE_PROVIDER_ROUTER")
        self.assertEqual(payload["policy"]["provider_mode"], "FALLBACK_OR_MANUAL")
        self.assertEqual(payload["policy"]["high_quality_fallback_provider"], "OPENAI_IMAGE")
        self.assertTrue(payload["policy"]["human_review_required"])
        providers = {item["id"]: item for item in payload["providers"]}
        self.assertEqual(providers["OPENAI_IMAGE"]["role"], "HIGH_QUALITY_FALLBACK")
        self.assertEqual(providers["BLENDER_ANIME"]["role"], "AUXILIARY_3D_CONTROL")
        self.assertFalse(providers["BLENDER_ANIME"]["remote"])

    def test_remote_image_generation_keeps_confirmation_gates(self):
        payload = json.loads((ROOT / "config" / "visual-generation-routes.json").read_text(encoding="utf-8"))
        policy = payload["policy"]
        self.assertTrue(policy["billable_remote_call_requires_confirmation"])
        self.assertTrue(policy["reference_image_upload_requires_authorization"])


if __name__ == "__main__":
    unittest.main()
