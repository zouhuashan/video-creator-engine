import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.render_godot_25d_preview import build_preview_config


class Godot25DPreviewTests(unittest.TestCase):
    def test_preview_config_requires_and_maps_upper_body_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            visual = project / "visual-bible"
            visual.mkdir(parents=True)
            layers = []
            names = (
                "head", "torso",
                "upper_arm_l", "forearm_l", "hand_l",
                "upper_arm_r", "forearm_r", "hand_r",
            )
            parents = {
                "head": "torso",
                "torso": None,
                "upper_arm_l": "torso",
                "forearm_l": "upper_arm_l",
                "hand_l": "forearm_l",
                "upper_arm_r": "torso",
                "forearm_r": "upper_arm_r",
                "hand_r": "forearm_r",
            }
            for index, name in enumerate(names):
                path = project / f"assets/{name}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGBA", (100, 160), (255, 255, 255, 255)).save(path)
                layers.append(
                    {
                        "name": name,
                        "path": path.relative_to(project).as_posix(),
                        "parent": parents[name],
                        "pivot": {"x": 50, "y": 60},
                        "z_index": index,
                    }
                )
            (visual / "character-rigs-v2.json").write_text(
                json.dumps(
                    {
                        "rigs": [
                            {
                                "id": "RIG2-TEST",
                                "character_id": "CHR-TEST",
                                "profile": "GODOT_UPPER_BODY_IK",
                                "canvas": {"width": 100, "height": 160},
                                "layers": layers,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            config = build_preview_config(project, "CHR-TEST", 4)
            self.assertEqual(config["rig_id"], "RIG2-TEST")
            self.assertEqual(len(config["layers"]), 8)
            self.assertIn("layer_parallax", config["visual_features"])
            self.assertGreater(config["layers"][4]["depth"], config["layers"][1]["depth"])


if __name__ == "__main__":
    unittest.main()
