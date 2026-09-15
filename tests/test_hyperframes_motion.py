import unittest

from scripts.hyperframes_motion import (
    CONTENT_TYPES,
    HyperFramesMotionError,
    build_motion_plan,
    load_motion_config,
    motion_for,
)


class HyperFramesMotionTests(unittest.TestCase):
    def test_declares_defaults_for_all_required_content_types(self):
        config = load_motion_config()

        self.assertEqual(tuple(config["motions"]), CONTENT_TYPES)
        self.assertTrue(config["defaults"]["seekable"])
        self.assertEqual(config["runtime"], "gsap")

    def test_builds_deterministic_motion_plan(self):
        plan = build_motion_plan(
            [
                {"id": "headline", "content_type": "title", "start_frame": 0},
                {"id": "price", "content_type": "price", "start_frame": 18},
            ]
        )

        self.assertEqual(plan["fps"], 30)
        self.assertTrue(plan["seekable"])
        self.assertEqual(plan["elements"][0]["motion"]["pattern"], "mask_reveal_up")
        self.assertEqual(plan["elements"][1]["motion"]["pattern"], "digit_roll")

    def test_motion_result_is_not_shared_with_config(self):
        config = load_motion_config()
        selected = motion_for("card", config)
        selected["properties"].append("rotation")

        self.assertNotIn("rotation", config["motions"]["card"]["properties"])

    def test_rejects_unknown_content_type_and_duplicate_id(self):
        with self.assertRaisesRegex(HyperFramesMotionError, "unsupported"):
            motion_for("logo")
        with self.assertRaisesRegex(HyperFramesMotionError, "unique"):
            build_motion_plan(
                [
                    {"id": "same", "content_type": "title"},
                    {"id": "same", "content_type": "data"},
                ]
            )


if __name__ == "__main__":
    unittest.main()
