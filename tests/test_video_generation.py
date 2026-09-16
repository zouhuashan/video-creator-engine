from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adapters.video_generation import (
    LocalKenBurnsVideo,
    VideoGenerationError,
    VideoGenerationRequest,
    choose_video_generation_provider,
)


class VideoGenerationTests(unittest.TestCase):
    def test_provider_selection_prefers_explicit_enabled_provider(self):
        self.assertEqual(choose_video_generation_provider({"local_ken_burns": True, "runway": False}, "local_ken_burns"), "local_ken_burns")

    def test_provider_selection_rejects_unknown_provider(self):
        with self.assertRaises(VideoGenerationError):
            choose_video_generation_provider({"unknown": True})

    def test_request_requires_existing_images_and_mp4(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(VideoGenerationError):
                VideoGenerationRequest((root / "missing.png",), root / "out.mp4").validate()
            image = root / "one.png"
            image.write_bytes(b"png")
            with self.assertRaises(VideoGenerationError):
                VideoGenerationRequest((image,), root / "out.mov").validate()

    def test_local_provider_builds_and_runs_ffmpeg_command(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            images = []
            for index in range(2):
                image = root / f"{index}.png"
                image.write_bytes(b"png")
                images.append(image)
            output = root / "out.mp4"

            def runner(command, **kwargs):
                output.write_bytes(b"video")
                return type("Completed", (), {"returncode": 0, "stderr": ""})()

            result = LocalKenBurnsVideo(runner=runner).generate(
                VideoGenerationRequest(tuple(images), output, shot_duration_seconds=2.0, transition_seconds=0.25)
            )
            self.assertEqual(result.provider, "local_ken_burns")
            self.assertEqual(result.image_count, 2)
            self.assertAlmostEqual(result.duration_seconds, 3.75)
            self.assertTrue(output.is_file())

    def test_local_provider_offsets_chained_crossfades_from_accumulated_duration(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            images = []
            for index in range(3):
                image = root / f"{index}.png"
                image.write_bytes(b"png")
                images.append(image)
            request = VideoGenerationRequest(tuple(images), root / "out.mp4", shot_duration_seconds=3.1, transition_seconds=0.4)
            command = LocalKenBurnsVideo()._command(request, root / "out.mp4")
            filter_complex = command[command.index("-filter_complex") + 1]
            self.assertIn("xfade=transition=fade:duration=0.4:offset=2.7", filter_complex)
            self.assertIn("xfade=transition=fade:duration=0.4:offset=5.4", filter_complex)


if __name__ == "__main__":
    unittest.main()
