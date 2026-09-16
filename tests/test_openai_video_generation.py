from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from adapters.video_generation import OpenAISoraVideo, VideoGenerationError, VideoGenerationRequest


class _Response:
    def __init__(self, payload=None, data=b""):
        self.payload = payload
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode() if self.payload is not None else self.data


class OpenAISoraVideoTests(unittest.TestCase):
    def test_requires_explicit_api_key(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "frame.png"
            image.write_bytes(b"png")
            with self.assertRaisesRegex(VideoGenerationError, "OPENAI_API_KEY"):
                OpenAISoraVideo(api_key="", sleeper=lambda _: None).generate(
                    VideoGenerationRequest((image,), Path(directory) / "out.mp4", model="sora-2")
                )

    def test_creates_polls_and_downloads_reference_video(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "frame.png"
            image.write_bytes(b"png")
            output = root / "out.mp4"
            calls = []

            def opener(request):
                if isinstance(request, str):
                    return _Response(data=b"video")
                payload = json.loads(request.data.decode()) if request.data else None
                calls.append((request.method, request.full_url, payload))
                if request.method == "POST":
                    return _Response({"id": "video-1", "status": "queued"})
                if request.full_url.endswith("/content"):
                    return _Response(data=b"video")
                return _Response({"id": "video-1", "status": "completed", "seconds": "4"})

            result = OpenAISoraVideo(api_key="test", opener=opener, sleeper=lambda _: None).generate(
                VideoGenerationRequest((image,), output, shot_duration_seconds=3.0, prompt_text="move gently")
            )
            self.assertEqual(result.provider, "openai_sora")
            self.assertEqual(result.task_id, "video-1")
            self.assertEqual(output.read_bytes(), b"video")
            self.assertEqual([call[0] for call in calls], ["POST", "GET", "GET"])
            self.assertEqual(calls[0][2]["model"], "sora-2")
            self.assertEqual(calls[0][2]["seconds"], "4")
            self.assertIn("input_reference", calls[0][2])


if __name__ == "__main__":
    unittest.main()
