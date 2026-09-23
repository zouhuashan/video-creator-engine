import subprocess
import tempfile
import unittest
from pathlib import Path

from adapters.video_generation.base import VideoGenerationRequest
from adapters.video_generation.local_micro_motion import LocalMicroMotionVideo


class LocalMicroMotionVideoTests(unittest.TestCase):
    def test_single_still_generates_continuous_local_camera_motion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "frame.png"
            output = root / "shot.mp4"
            image.write_bytes(b"image")
            captured = {}

            def runner(command, **kwargs):
                captured["command"] = command
                output.write_bytes(b"video")
                return subprocess.CompletedProcess(command, 0, "", "")

            provider = LocalMicroMotionVideo(ffmpeg="ffmpeg", runner=runner)
            result = provider.generate(VideoGenerationRequest(
                image_paths=(image,),
                output_path=output,
                shot_duration_seconds=4.0,
                fps=24,
                width=720,
                height=1280,
            ))

            self.assertFalse(result.remote_generation)
            self.assertEqual(result.provider, "local_micro_motion")
            self.assertEqual(result.duration_seconds, 4.0)
            command = " ".join(captured["command"])
            self.assertIn("zoompan=", command)
            self.assertIn("sin(on/18)", command)
            self.assertIn("sin(on/24)", command)
            self.assertIn("trim=duration=4.000000", command)

    def test_rejects_multiple_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a, b = root / "a.png", root / "b.png"
            a.write_bytes(b"a"); b.write_bytes(b"b")
            provider = LocalMicroMotionVideo()
            with self.assertRaisesRegex(Exception, "exactly one"):
                provider.generate(VideoGenerationRequest(
                    image_paths=(a, b),
                    output_path=root / "out.mp4",
                ))


if __name__ == "__main__":
    unittest.main()
