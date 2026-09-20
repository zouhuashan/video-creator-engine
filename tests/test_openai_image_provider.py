import json
import unittest
from pathlib import Path

from support.providers.openai_image_provider import character_bible_prompt, keyframe_prompt

ROOT = Path(__file__).resolve().parents[1]


class OpenAIImagePromptTests(unittest.TestCase):
    def _character(self):
        return {
            "name": "照骨灯角色",
            "role": "protagonist",
            "visual_lock": {
                "face": "refined stylized Chinese face",
                "hair": "dark tied hair",
                "costume": "layered ancient Chinese hanfu",
                "body": "balanced heroic proportions",
                "mood": "restrained and determined",
            },
            "render_lock": {
                "medium": "premium cinematic 3D Chinese donghua",
                "shading": "volumetric NPR/PBR character shading",
                "lighting": "cinematic three-point lighting",
                "palette": ["ivory", "ink black", "muted jade"],
            },
            "consistency_rules": ["same face", "same costume"],
        }

    def _shot(self):
        return {
            "action": "standing beside an ancient lantern",
            "environment": "misty ancient Chinese courtyard",
            "lighting": "moonlit volumetric atmosphere",
            "camera": {
                "framing": "medium full shot",
                "lens_language": "cinematic portrait lens",
                "angle": "slight low angle",
                "depth_of_field": "shallow",
            },
        }

    def test_cinematic_3d_character_bible_requires_rendered_turnaround_not_flat_art(self):
        prompt = character_bible_prompt(
            self._character(),
            style_direction=(
                "Premium cinematic 3D Chinese donghua, fully modeled character, "
                "NPR toon shading with PBR material response."
            ),
            forbidden_direction="flat illustration, watercolor, 2D cutout",
        )
        self.assertIn("3D production character-turnaround board", prompt)
        self.assertIn("fully modeled three-dimensional character", prompt)
        self.assertIn("true volume", prompt)
        self.assertIn("finished film character render", prompt)
        self.assertIn("flat illustration", prompt)

    def test_cinematic_3d_keyframe_requires_true_depth_and_material_volume(self):
        prompt = keyframe_prompt(
            self._character(),
            self._shot(),
            style_direction=(
                "Premium cinematic 3D Chinese donghua, stylized NPR/PBR film frame."
            ),
            forbidden_direction="flat 2D drawing, paper texture",
        )
        self.assertIn("cinematic 3D keyframe", prompt)
        self.assertIn("true 3D film frame", prompt)
        self.assertIn("cloth thickness", prompt)
        self.assertIn("real depth of field", prompt)
        self.assertIn("flat 2D drawing", prompt)

    def test_default_character_render_lock_is_cinematic_3d(self):
        payload = json.loads(
            (ROOT / "config" / "characters" / "char-child-001.json").read_text(encoding="utf-8")
        )
        self.assertIn("cinematic 3D Chinese donghua", payload["render_lock"]["medium"])
        self.assertIn("volumetric 3D forms", payload["render_lock"]["shading"])
        self.assertNotIn("2D/2.5D", payload["render_lock"]["medium"])


if __name__ == "__main__":
    unittest.main()
