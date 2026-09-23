import subprocess
import tempfile
import unittest
from pathlib import Path

from adapters.video_generation.base import VideoGenerationRequest
from adapters.video_generation.local_scene_plate import LocalScenePlateVideo


class LocalScenePlateVideoTests(unittest.TestCase):
    def test_one_scene_plate_uses_local_camera_motion_and_exact_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "scene.png"
            output = root / "scene.mp4"
            image.write_bytes(b"image")
            captured = {}

            def runner(command, **kwargs):
                captured["command"] = command
                output.write_bytes(b"video")
                return subprocess.CompletedProcess(command, 0, "", "")

            result = LocalScenePlateVideo(runner=runner).generate(VideoGenerationRequest(
                image_paths=(image,),
                output_path=output,
                shot_duration_seconds=3.7,
                fps=24,
                width=720,
                height=1280,
            ))
            self.assertFalse(result.remote_generation)
            self.assertEqual(result.provider, "local_scene_plate")
            self.assertEqual(result.duration_seconds, 3.7)
            command = " ".join(captured["command"])
            self.assertIn("zoompan=", command)
            self.assertIn("trim=duration=3.700000", command)

    def test_rejects_more_than_one_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a, b = root / "a.png", root / "b.png"
            a.write_bytes(b"a"); b.write_bytes(b"b")
            with self.assertRaisesRegex(Exception, "exactly one"):
                LocalScenePlateVideo().generate(VideoGenerationRequest(
                    image_paths=(a, b), output_path=root / "out.mp4"
                ))


if __name__ == "__main__":
    unittest.main()
