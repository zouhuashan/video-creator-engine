import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.rig_v2_auto_draft import propose_upper_body


class RigV2AutoDraftTests(unittest.TestCase):
    def test_proposal_contains_all_upper_body_layers_inside_canvas(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / "character.png"
            image = Image.new("RGBA", (200, 320), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.ellipse((70, 20, 130, 90), fill=(255, 220, 200, 255))
            draw.rectangle((55, 80, 145, 235), fill=(180, 120, 180, 255))
            draw.rectangle((20, 95, 180, 220), fill=(180, 120, 180, 255))
            image.save(source)

            result = propose_upper_body(project, "character.png")
            self.assertEqual(result["status"], "DRAFT")
            self.assertFalse(result["generative"])
            self.assertFalse(result["remote"])
            expected = {
                "head", "torso",
                "upper_arm_l", "forearm_l", "hand_l",
                "upper_arm_r", "forearm_r", "hand_r",
            }
            self.assertEqual(set(result["layers"]), expected)
            for layer in result["layers"].values():
                self.assertGreaterEqual(len(layer["polygon"]), 4)
                for x, y in layer["polygon"]:
                    self.assertGreaterEqual(x, 0)
                    self.assertLessEqual(x, 200)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(y, 320)
                self.assertIn(layer["confidence"], {"HIGH", "MEDIUM", "LOW"})


if __name__ == "__main__":
    unittest.main()
