from pathlib import Path
import unittest

from scripts.local_storyboard_pipeline import build_mux_command


class LocalStoryboardPipelineTests(unittest.TestCase):
    def test_mux_command_keeps_video_voice_and_subtitles(self):
        command = build_mux_command(Path("visual.mp4"), Path("voice.wav"), Path("captions.srt"), Path("final.mp4"))
        self.assertIn("-map", command)
        self.assertIn("0:v:0", command)
        self.assertIn("1:a:0", command)
        self.assertIn("subtitles=captions.srt", command[command.index("-vf") + 1])
        self.assertIn("-shortest", command)


if __name__ == "__main__":
    unittest.main()
