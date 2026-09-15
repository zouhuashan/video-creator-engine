import unittest

from scripts.hyperframes_motion import (
    CONTENT_TYPES,
    HyperFramesMotionError,
    STYLE_PRESET_NAMES,
    apply_style_preset,
    build_motion_plan,
    load_motion_config,
    load_style_preset,
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

    def test_loads_all_six_style_presets(self):
        loaded = [load_style_preset(name) for name in STYLE_PRESET_NAMES]

        self.assertEqual([preset["name"] for preset in loaded], list(STYLE_PRESET_NAMES))
        self.assertTrue(all(preset["palette"]["accent"].startswith("#") for preset in loaded))

    def test_applies_preset_without_mutating_base_plan(self):
        base = build_motion_plan([{"id": "headline", "content_type": "title"}])
        styled = apply_style_preset(base, "warning")

        self.assertEqual(styled["style_preset"], "warning")
        self.assertEqual(styled["elements"][0]["motion"]["duration_frames"], 14)
        self.assertEqual(base["elements"][0]["motion"]["duration_frames"], 18)
        self.assertEqual(styled["style"]["transition"], "impact_cut")

    def test_rejects_unknown_style_preset(self):
        with self.assertRaisesRegex(HyperFramesMotionError, "unsupported"):
            load_style_preset("cinematic")


if __name__ == "__main__":
    unittest.main()
