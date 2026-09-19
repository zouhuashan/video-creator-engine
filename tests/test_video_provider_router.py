import json
import tempfile
import unittest
from pathlib import Path

from support.providers.video_provider_router import VideoProviderRouteError, VideoProviderRouter


class VideoProviderRouterTests(unittest.TestCase):
    def test_local_default_never_requires_billable_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routes.json"
            path.write_text(json.dumps({
                "policy": {
                    "default_provider": "LOCAL",
                    "billable_remote_call_requires_confirmation": True,
                    "human_review_required": True,
                },
                "providers": [
                    {"id": "LOCAL", "adapter": "local", "role": "FREE", "remote": False, "status": "ACTIVE", "capabilities": ["image_to_video"]},
                    {"id": "REMOTE", "adapter": "remote", "role": "PAID", "remote": True, "status": "ACTIVE", "capabilities": ["image_to_video"]},
                ],
            }), encoding="utf-8")
            router = VideoProviderRouter(path)
            route = router.route("image_to_video")
            self.assertEqual(route["provider_id"], "LOCAL")
            self.assertFalse(route["remote"])
            with self.assertRaisesRegex(VideoProviderRouteError, "confirmation"):
                router.route("image_to_video", preferred_provider="REMOTE")
            paid = router.route("image_to_video", preferred_provider="REMOTE", confirm_billable=True)
            self.assertEqual(paid["provider_id"], "REMOTE")
            self.assertTrue(paid["human_review_required"])


if __name__ == "__main__":
    unittest.main()
