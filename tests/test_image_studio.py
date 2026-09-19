import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.web_server as web_server
from support.providers.openai_image_provider import (
    OpenAIImageProvider,
    character_bible_prompt,
    keyframe_prompt,
)


class ImageStudioTests(unittest.TestCase):
    def tearDown(self):
        web_server.RUNTIME_KEYS.pop("openai_image", None)

    def test_openai_image_status_never_exposes_key(self):
        web_server.RUNTIME_KEYS["openai_image"] = "secret-image-key-123"
        status = web_server._openai_image_status()
        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], "session")
        self.assertNotIn("secret-image-key-123", json.dumps(status))

    def test_locked_prompts_keep_child_and_guofeng_direction(self):
        character = web_server._load_repo_json(web_server.IMAGE_CHARACTER_CONFIG_PATH)
        shot = web_server._load_repo_json(web_server.IMAGE_SHOT_CONFIG_PATH)
        bible = character_bible_prompt(character)
        keyframe = keyframe_prompt(character, shot)
        self.assertIn("young child", bible)
        self.assertIn("twin", bible.lower())
        self.assertIn("guofeng", bible.lower())
        self.assertIn("not an adult", keyframe.lower())
        self.assertIn("ancient chinese military camp", keyframe.lower())

    def test_generation_writes_project_asset_and_pending_metadata(self):
        web_server.RUNTIME_KEYS["openai_image"] = "test-image-key-123456"
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo-project"
            project.mkdir()

            def fake_generate(_self, prompt, output_path, *, size, quality="high"):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"fake-png" * 400)
                return {
                    "provider": "openai_image",
                    "model": "gpt-image-2",
                    "size": size,
                    "quality": quality,
                    "output": str(output_path),
                    "revised_prompt": "",
                }

            with patch.object(OpenAIImageProvider, "generate", fake_generate):
                result = web_server._generate_image_studio_asset(
                    project,
                    artifact_type="character_bible",
                    custom_prompt="more cinematic",
                )

            self.assertEqual(result["artifact_type"], "character_bible")
            self.assertEqual(result["review_status"], "PENDING")
            self.assertTrue((project / result["output"]).is_file())
            self.assertTrue((project / result["metadata"]).is_file())
            self.assertTrue(result["media_url"].startswith("/media/demo-project/"))


if __name__ == "__main__":
    unittest.main()
