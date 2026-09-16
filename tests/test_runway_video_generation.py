from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from adapters.video_generation import RunwayImageToVideo, VideoGenerationError, VideoGenerationRequest


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


class RunwayVideoGenerationTests(unittest.TestCase):
    def test_requires_explicit_api_key(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "frame.png"
            image.write_bytes(b"png")
            with self.assertRaisesRegex(VideoGenerationError, "RUNWAY_API_KEY"):
                RunwayImageToVideo(api_key="").generate(VideoGenerationRequest((image,), Path(directory) / "out.mp4"))

    def test_creates_task_polls_and_downloads_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "frame.png"
            image.write_bytes(b"png")
            output = root / "out.mp4"
            calls = []

            def opener(request):
                if isinstance(request, str):
                    return _Response(data=b"video")
                calls.append((request.method, request.full_url, json.loads(request.data.decode()) if request.data else None))
                if request.method == "POST":
                    return _Response({"id": "task-1"})
                return _Response({"status": "SUCCEEDED", "output": ["https://example.test/out.mp4"]})

            result = RunwayImageToVideo(api_key="test", opener=opener, sleeper=lambda _: None).generate(
                VideoGenerationRequest((image,), output, prompt_text="move gently")
            )
            self.assertEqual(result.provider, "runway")
            self.assertEqual(result.task_id, "task-1")
            self.assertEqual(output.read_bytes(), b"video")
            self.assertEqual([call[0] for call in calls], ["POST", "GET"])
            self.assertEqual(calls[0][2]["model"], "gen4.5")


if __name__ == "__main__":
    unittest.main()
