import json
import tempfile
import unittest
from pathlib import Path

from adapters.video_generation.base import VideoGenerationRequest
from adapters.video_generation.minimax_h3 import MiniMaxH3Video


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


class MiniMaxH3ReferenceTests(unittest.TestCase):
    def test_payload_contains_video_then_character_and_scene_reference_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "graybox.mp4"
            character = root / "character.png"
            scene = root / "scene.png"
            output = root / "out.mp4"
            video.write_bytes(b"v" * 2048)
            character.write_bytes(b"c" * 2048)
            scene.write_bytes(b"s" * 2048)
            calls = []
            created = {"task_id": "task-001"}
            completed = {
                "task": {
                    "status": "completed",
                    "duration": 8,
                    "content": {"url": "https://result.example/video.mp4"},
                }
            }

            def opener(request):
                calls.append(request)
                if isinstance(request, str):
                    self.assertEqual(request, "https://result.example/video.mp4")
                    return _Response(b"o" * 4096)
                if request.full_url.endswith("/v2/video_generation"):
                    return _Response(json.dumps(created).encode("utf-8"))
                if request.full_url.endswith("/v2/query/video_generation/task-001"):
                    return _Response(json.dumps(completed).encode("utf-8"))
                raise AssertionError(f"unexpected request: {request.full_url}")

            provider = MiniMaxH3Video(
                api_key="secret",
                opener=opener,
                sleeper=lambda _seconds: None,
                poll_interval_seconds=0,
                timeout_polls=2,
                resolution="768P",
            )
            result = provider.generate(VideoGenerationRequest(
                image_paths=(character, scene),
                reference_video_paths=(video,),
                output_path=output,
                shot_duration_seconds=8,
                fps=24,
                width=720,
                height=1280,
                prompt_text=(
                    "Reference image 1 = character identity. "
                    "Reference image 2 = scene environment. "
                    "Follow the graybox motion."
                ),
                model="MiniMax-H3",
            ))

            self.assertEqual(result.image_count, 2)
            self.assertTrue(output.is_file())
            create_request = calls[0]
            payload = json.loads(create_request.data.decode("utf-8"))
            content = payload["content"]
            self.assertEqual([item["type"] for item in content], [
                "text",
                "video_url",
                "image_url",
                "image_url",
            ])
            self.assertEqual(content[1]["role"], "reference_video")
            self.assertEqual(content[2]["role"], "reference_image")
            self.assertEqual(content[3]["role"], "reference_image")
            self.assertTrue(content[1]["video_url"]["url"].startswith("data:video/mp4;base64,"))
            self.assertTrue(content[2]["image_url"]["url"].startswith("data:image/png;base64,"))
            self.assertTrue(content[3]["image_url"]["url"].startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
