import tempfile
import unittest
from pathlib import Path

from adapters.motion.godot_cutout import (
    GodotCutoutError,
    parse_version,
    smoke_command,
)
from scripts.godot_rig_readiness import assess_rig


class GodotCutoutTests(unittest.TestCase):
    def test_parse_stable_and_prerelease_versions(self):
        stable = parse_version("4.7.2.stable.official")
        self.assertEqual(stable.tuple, (4, 7, 2))
        self.assertTrue(stable.stable)

        preview = parse_version("4.8.dev6.official")
        self.assertEqual(preview.tuple, (4, 8, 0))
        self.assertFalse(preview.stable)

    def test_smoke_command_requires_project_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(GodotCutoutError, "missing project.godot"):
                smoke_command(root, "/tmp/godot")

            (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
            command = smoke_command(root, "/tmp/godot")
            self.assertEqual(command[0], "/tmp/godot")
            self.assertIn("--headless", command)
            self.assertIn("res://main.tscn", command)

    def test_existing_v1_rig_is_cutout_ready_but_not_ik_ready(self):
        rig = {
            "id": "RIG-1",
            "character_id": "CHR-1",
            "layers": [{"name": name} for name in ("full", "head", "torso", "lower")],
        }
        result = assess_rig(rig)
        self.assertTrue(result["profiles"]["LOCAL_CUTOUT_RIG"]["ready"])
        self.assertFalse(result["profiles"]["GODOT_UPPER_BODY_IK"]["ready"])
        self.assertIn("upper_arm_l", result["profiles"]["GODOT_UPPER_BODY_IK"]["missing_layers"])
        self.assertEqual(result["recommended_next_profile"], "RIG_V2_SEGMENTATION")

    def test_segmented_upper_body_rig_is_ik_ready(self):
        layers = (
            "head",
            "torso",
            "upper_arm_l",
            "forearm_l",
            "hand_l",
            "upper_arm_r",
            "forearm_r",
            "hand_r",
        )
        result = assess_rig({"id": "RIG-2", "layers": [{"name": name} for name in layers]})
        self.assertTrue(result["profiles"]["GODOT_UPPER_BODY_IK"]["ready"])
        self.assertFalse(result["profiles"]["GODOT_FULL_BODY_IK"]["ready"])


if __name__ == "__main__":
    unittest.main()
