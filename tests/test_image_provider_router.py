import unittest
from pathlib import Path

from support.providers.image_provider_router import ImageProviderRouteError, ImageProviderRouter

ROOT = Path(__file__).resolve().parents[1]


class ImageProviderRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = ImageProviderRouter(ROOT / "config" / "visual-generation-routes.json")

    def test_final_visual_defaults_to_openai_image_fallback(self):
        route = self.router.route("shot_keyframe", confirm_billable=True)
        self.assertEqual(route["route_id"], "IMAGE_PROVIDER_ROUTER")
        self.assertEqual(route["provider_id"], "OPENAI_IMAGE")
        self.assertEqual(route["adapter"], "openai_image")
        self.assertEqual(route["role"], "HIGH_QUALITY_FALLBACK")
        self.assertTrue(route["human_review_required"])

    def test_billable_remote_route_is_blocked_without_confirmation(self):
        with self.assertRaisesRegex(ImageProviderRouteError, "confirmation"):
            self.router.route("character_bible")

    def test_reference_upload_is_blocked_without_authorization(self):
        with self.assertRaisesRegex(ImageProviderRouteError, "upload"):
            self.router.route("hero_frame", confirm_billable=True, reference_image=True)

    def test_unimplemented_comfyui_slot_cannot_be_selected(self):
        with self.assertRaises(ImageProviderRouteError):
            self.router.route("shot_keyframe", preferred_provider="COMFYUI_IMAGE")

    def test_blender_is_auxiliary_not_final_visual_provider(self):
        description = self.router.describe()
        self.assertEqual(description["blender_role"], "AUXILIARY_3D_CONTROL")
        self.assertFalse(description["blender_final_visual_allowed"])
        with self.assertRaises(ImageProviderRouteError):
            self.router.route("hero_frame", preferred_provider="BLENDER_ANIME", confirm_billable=True)


if __name__ == "__main__":
    unittest.main()
