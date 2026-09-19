import unittest
from pathlib import Path

from support.providers.image_provider_router import ImageProviderRouteError, ImageProviderRouter

ROOT = Path(__file__).resolve().parents[1]


class ImageProviderRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = ImageProviderRouter(ROOT / "config" / "visual-generation-routes.json")

    def test_final_visual_defaults_to_local_comfyui(self):
        route = self.router.route("shot_keyframe")
        self.assertEqual(route["route_id"], "IMAGE_PROVIDER_ROUTER")
        self.assertEqual(route["provider_id"], "COMFYUI_IMAGE")
        self.assertEqual(route["adapter"], "comfyui_image")
        self.assertEqual(route["role"], "LOCAL_VISUAL_FACTORY")
        self.assertFalse(route["remote"])
        self.assertEqual(route["fallback_chain"][0], "COMFYUI_IMAGE")

    def test_billable_remote_fallback_is_blocked_without_confirmation(self):
        with self.assertRaisesRegex(ImageProviderRouteError, "confirmation"):
            self.router.route("character_bible", available_provider_ids={"OPENAI_IMAGE"})

    def test_reference_upload_is_blocked_without_authorization(self):
        with self.assertRaisesRegex(ImageProviderRouteError, "upload"):
            self.router.route("hero_frame", confirm_billable=True, reference_image=True)

    def test_comfyui_can_be_selected_explicitly_without_billable_confirmation(self):
        route = self.router.route("shot_keyframe", preferred_provider="COMFYUI_IMAGE")
        self.assertEqual(route["provider_id"], "COMFYUI_IMAGE")
        self.assertFalse(route["remote"])

    def test_auto_falls_back_to_openai_when_only_remote_is_available(self):
        route = self.router.route("shot_keyframe", preferred_provider="AUTO", available_provider_ids={"OPENAI_IMAGE"}, confirm_billable=True)
        self.assertEqual(route["provider_id"], "OPENAI_IMAGE")
        self.assertTrue(route["remote"])

    def test_blender_is_auxiliary_not_final_visual_provider(self):
        description = self.router.describe()
        self.assertEqual(description["blender_role"], "AUXILIARY_3D_CONTROL")
        self.assertFalse(description["blender_final_visual_allowed"])
        with self.assertRaises(ImageProviderRouteError):
            self.router.route("hero_frame", preferred_provider="BLENDER_ANIME", confirm_billable=True)


if __name__ == "__main__":
    unittest.main()
