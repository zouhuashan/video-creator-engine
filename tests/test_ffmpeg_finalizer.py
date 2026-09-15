import tempfile
import unittest
from pathlib import Path

from adapters.video import (
    AudioTrack,
    FinalizerError,
    FinalMergeSpec,
    build_final_merge_command,
    load_finalizer_config,
)


class FFmpegFinalizerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.video_a = self.root / "a.mp4"
        self.video_b = self.root / "b.mp4"
        self.audio_a = self.root / "voice.wav"
        self.audio_b = self.root / "music.wav"
        for path in (self.video_a, self.video_b, self.audio_a, self.audio_b):
            path.write_bytes(b"media")
        self.spec = FinalMergeSpec(
            video_inputs=(self.video_a, self.video_b),
            audio_inputs=(AudioTrack(self.audio_a), AudioTrack(self.audio_b, volume=0.2, delay_ms=500)),
            output=self.root / "final.mp4",
            width=1280,
            height=720,
            fps=30,
            video_codec="libx264",
            audio_codec="aac",
            video_bitrate="8M",
            audio_bitrate="192k",
            container="mp4",
            transition="fade",
            transition_duration=0.25,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_command_covers_merge_mix_normalize_transition_and_encode(self):
        command = build_final_merge_command(self.spec, duration_probe=lambda path: 2.0)
        filter_graph = command[command.index("-filter_complex") + 1]

        self.assertIn("scale=1280:720", filter_graph)
        self.assertIn("fps=30", filter_graph)
        self.assertIn("xfade=transition=fade:duration=0.25", filter_graph)
        self.assertIn("adelay=500:all=1,volume=0.2", filter_graph)
        self.assertIn("amix=inputs=2", filter_graph)
        self.assertIn("loudnorm=I=-14:TP=-1:LRA=11", filter_graph)
        self.assertEqual(command[command.index("-c:v") + 1], "libx264")
        self.assertEqual(command[command.index("-c:a") + 1], "aac")
        self.assertIn("+faststart", command)

    def test_none_transition_uses_concat(self):
        spec = FinalMergeSpec(**{**self.spec.__dict__, "transition": "none", "transition_duration": 0.0})
        command = build_final_merge_command(spec)

        self.assertIn("concat=n=2:v=1:a=0", command[command.index("-filter_complex") + 1])

    def test_rejects_invalid_geometry_codec_and_transition(self):
        with self.assertRaisesRegex(FinalizerError, "even"):
            build_final_merge_command(FinalMergeSpec(**{**self.spec.__dict__, "width": 1279}))
        with self.assertRaisesRegex(FinalizerError, "video codec"):
            build_final_merge_command(FinalMergeSpec(**{**self.spec.__dict__, "video_codec": "copy"}))
        with self.assertRaisesRegex(FinalizerError, "transition_duration"):
            build_final_merge_command(FinalMergeSpec(**{**self.spec.__dict__, "transition_duration": 0.0}))

    def test_single_video_without_audio_disables_audio_output(self):
        spec = FinalMergeSpec(
            **{
                **self.spec.__dict__,
                "video_inputs": (self.video_a,),
                "audio_inputs": (),
                "transition": "none",
                "transition_duration": 0.0,
            }
        )
        command = build_final_merge_command(spec)

        self.assertIn("-an", command)
        self.assertNotIn("-c:a", command)

    def test_config_pins_audio_and_encoding_safeguards(self):
        config = load_finalizer_config()

        self.assertEqual(config["audio_normalization"]["integrated_lufs"], -14)
        self.assertEqual(config["pixel_format"], "yuv420p")
        self.assertTrue(config["faststart"])


if __name__ == "__main__":
    unittest.main()
