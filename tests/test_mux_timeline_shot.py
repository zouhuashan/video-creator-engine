import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.mux_timeline_shot import mux


class MuxTimelineShotTests(unittest.TestCase):
    @patch("scripts.mux_timeline_shot.subprocess.run")
    def test_pads_short_audio_to_preserve_video_timeline(self, run):
        mux(Path("draft.mp4"), Path("voice.wav"), Path("final.mp4"))
        command = run.call_args.args[0]
        self.assertIn("[1:a]apad[a]", command)
        self.assertIn("-shortest", command)
        self.assertEqual(command[command.index("-map") + 1], "0:v:0")


if __name__ == "__main__":
    unittest.main()
