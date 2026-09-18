import unittest
import json
import tempfile
from pathlib import Path

from scripts.batch_render_final_shots import _background_for_shot, _expression, _particle_effect


class BatchFinalShotTests(unittest.TestCase):
    def test_maps_dialogue_emotion_to_supported_expression(self):
        self.assertEqual(_expression("向往"), "soft_smile")
        self.assertEqual(_expression("疑惑"), "concerned")
        self.assertEqual(_expression("惊讶"), "surprised")
        self.assertEqual(_expression("笃定"), "neutral")

    def test_resolves_scene_specific_background_from_generation_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            background = project / "assets" / "locations" / "LOCN-JHY-NUANGE" / "plate.png"
            background.parent.mkdir(parents=True)
            background.write_bytes(b"png")
            manifest = project / "lookdev" / "generation-manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"assets": [{"asset_id": "AST-LOC-JHY-NUANGE-SNOW-NIGHT", "type": "environment_anchor_png", "path": background.relative_to(project).as_posix(), "references": ["S01E003-SC003"]}]}), encoding="utf-8")
            path, asset_id = _background_for_shot(project, "SHOT-S01E003-SC003-002")
            self.assertEqual(path, background)
            self.assertEqual(asset_id, "AST-LOC-JHY-NUANGE-SNOW-NIGHT")

    def test_disables_flower_petals_for_non_flower_scenes(self):
        self.assertEqual(_particle_effect("AST-LOC-JHY-BATTLEFIELD-AFTERMATH-DAY"), "none")
        self.assertEqual(_particle_effect("AST-LOC-JHY-MAGUDONG-SNOW-NIGHT"), "none")
        self.assertEqual(_particle_effect("AST-LOC-JHY-KUNLUN-NIGHT"), "petals")


if __name__ == "__main__":
    unittest.main()
