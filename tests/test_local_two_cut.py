import subprocess
import tempfile
import unittest
from pathlib import Path

from adapters.video_generation.base import VideoGenerationRequest
from adapters.video_generation.local_two_cut import LocalTwoCutVideo


class LocalTwoCutVideoTests(unittest.TestCase):
    def test_two_images_use_hard_concat_not_crossfade(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a, b = root / "a.png", root / "b.png"
            output = root / "two-cut.mp4"
            a.write_bytes(b"a"); b.write_bytes(b"b")
            captured = {}

            def runner(command, **kwargs):
                captured["command"] = command
                output.write_bytes(b"video")
                return subprocess.CompletedProcess(command, 0, "", "")

            result = LocalTwoCutVideo(runner=runner).generate(VideoGenerationRequest(
                image_paths=(a, b),
                output_path=output,
                shot_duration_seconds=5.25,
                fps=24,
                width=720,
                height=1280,
            ))
            self.assertFalse(result.remote_generation)
            self.assertEqual(result.provider, "local_two_cut")
            self.assertEqual(result.duration_seconds, 5.25)
            command = " ".join(captured["command"])
            self.assertIn("concat=n=2:v=1:a=0", command)
            self.assertNotIn("xfade", command)
            self.assertIn("trim=duration=5.250000", command)

    def test_requires_exactly_two_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "a.png"
            image.write_bytes(b"a")
            with self.assertRaisesRegex(Exception, "exactly two"):
                LocalTwoCutVideo().generate(VideoGenerationRequest(
                    image_paths=(image,), output_path=root / "out.mp4"
                ))


if __name__ == "__main__":
    unittest.main()
