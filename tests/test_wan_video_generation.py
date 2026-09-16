from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from adapters.video_generation import WanImageToVideo, VideoGenerationError, VideoGenerationRequest


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


class WanVideoGenerationTests(unittest.TestCase):
    def test_requires_fal_key(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "frame.png"
            image.write_bytes(b"png")
            with self.assertRaisesRegex(VideoGenerationError, "FAL_KEY"):
                WanImageToVideo(api_key="", sleeper=lambda _: None).generate(
                    VideoGenerationRequest((image,), Path(directory) / "out.mp4")
                )

    def test_submits_polls_and_downloads_wan_video(self):
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
                    return _Response({"request_id": "req-1", "status_url": "https://fal.test/status", "response_url": "https://fal.test/result"})
                if request.full_url.endswith("/status"):
                    return _Response({"status": "COMPLETED"})
                if request.full_url.endswith("/result"):
                    return _Response({"video": {"url": "https://fal.test/video.mp4"}})
                raise AssertionError(request.full_url)

            result = WanImageToVideo(api_key="test", opener=opener, sleeper=lambda _: None).generate(
                VideoGenerationRequest((image,), output, prompt_text="move gently")
            )
            self.assertEqual(result.provider, "wan")
            self.assertEqual(result.task_id, "req-1")
            self.assertEqual(output.read_bytes(), b"video")
            self.assertEqual([call[0] for call in calls], ["POST", "GET", "GET"])
            self.assertEqual(calls[0][2]["resolution"], "720p")


if __name__ == "__main__":
    unittest.main()
