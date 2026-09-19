import os
import stat
import tempfile
import unittest
from pathlib import Path

from scripts.pipeline_media_executor import PipelineMediaError, assemble, build_ffmpeg_command


class PipelineMediaExecutorTests(unittest.TestCase):
    def test_command_uses_known_voice_and_subtitle_without_asr(self):
        command = build_ffmpeg_command(
            Path("/tmp/input.mp4"),
            Path("/tmp/final.mp4"),
            voice_path=Path("/tmp/voice.wav"),
            subtitles_path=Path("/tmp/subtitles.srt"),
            ffmpeg="/usr/bin/ffmpeg",
        )
        joined = " ".join(command)
        self.assertIn("/tmp/voice.wav", joined)
        self.assertIn("subtitles=", joined)
        self.assertNotIn("whisper", joined.lower())
        self.assertIn("-shortest", command)

    def test_assemble_executes_ffmpeg_binary_and_atomically_writes_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "input.mp4"
            voice = root / "voice.wav"
            subtitles = root / "subtitles.srt"
            output = root / "final.mp4"
            fake = root / "ffmpeg"
            video.write_bytes(b"video")
            voice.write_bytes(b"voice")
            subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
            fake.write_text("#!/bin/sh\nlast=''\nfor arg in \"$@\"; do last=\"$arg\"; done\nprintf 'assembled' > \"$last\"\n", encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            result = assemble(video, output, voice_path=voice, subtitles_path=subtitles, ffmpeg=str(fake))
            self.assertTrue(output.is_file())
            self.assertEqual(output.read_bytes(), b"assembled")
            self.assertEqual(result["output"], str(output.resolve()))

    def test_missing_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PipelineMediaError):
                assemble(Path(directory) / "missing.mp4", Path(directory) / "out.mp4", ffmpeg="/bin/false")


if __name__ == "__main__":
    unittest.main()
