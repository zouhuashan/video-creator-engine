import unittest

from adapters.video_generation.router import VIDEO_GENERATION_PROVIDER_PRIORITY, choose_video_generation_provider


class CostFirstVideoGenerationRouterTests(unittest.TestCase):
    def test_local_providers_precede_every_remote_provider(self):
        self.assertEqual(VIDEO_GENERATION_PROVIDER_PRIORITY[:4], (
            "local_scene_plate", "local_micro_motion", "local_two_cut", "local_ken_burns"
        ))
        selected = choose_video_generation_provider({
            "local_scene_plate": True,
            "local_micro_motion": True,
            "local_two_cut": True,
            "local_ken_burns": True,
            "minimax_h3": True,
            "openai_sora": True,
            "runway": True,
            "wan": True,
        })
        self.assertEqual(selected, "local_scene_plate")


if __name__ == "__main__":
    unittest.main()
