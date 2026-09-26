import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.render_godot_25d_preview import (
    Godot25DPreviewError,
    _resolve_background,
    build_preview_config,
)


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

            background = project / "scene.png"
            Image.new("RGB", (720, 1280), (12, 24, 48)).save(background)

            config = build_preview_config(
                project,
                "CHR-TEST",
                4,
                background_path=background,
                framing="closeup",
            )
            self.assertEqual(config["rig_id"], "RIG2-TEST")
            self.assertEqual(len(config["layers"]), 8)
            self.assertEqual(config["schema_version"], 2)
            self.assertEqual(config["framing"]["profile"], "CLOSEUP")
            self.assertEqual(config["background"]["path"], str(background.resolve()))
            self.assertEqual(config["framing"]["content_bounds"]["body_bottom"], 160)
            self.assertIn("real_scene_background", config["visual_features"])
            self.assertIn("restrained_breathing", config["visual_features"])
            self.assertNotIn("arm_raise_hold_return", config["visual_features"])
            self.assertGreater(config["layers"][4]["depth"], config["layers"][1]["depth"])

    def test_preview_config_rejects_missing_explicit_background(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with self.assertRaisesRegex(Godot25DPreviewError, "background image not found"):
                _resolve_background(project, project / "missing.png")


if __name__ == "__main__":
    unittest.main()
