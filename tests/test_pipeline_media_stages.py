import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.pipeline_media_stages import assemble_final, ensure_subtitles, ensure_tts


class PipelineMediaStagesTests(unittest.TestCase):
    def test_existing_audio_is_reused_without_tts(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            audio = project / "audio" / "existing.wav"
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b"RIFF-existing")
            result = ensure_tts(project)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["reused"])
            self.assertEqual(result["asset"], "audio/existing.wav")

    def test_subtitles_are_built_from_known_timeline_without_asr(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            cues = project / "dynamic" / "mouth-cues.json"
            cues.parent.mkdir(parents=True)
            cues.write_text(
                '{"timeline":['
                '{"text":"第一句","start_seconds":0,"end_seconds":1.5},'
                '{"text":"第二句","start_seconds":0,"end_seconds":2.0}'
                ']}',
                encoding="utf-8",
            )
            result = ensure_subtitles(project)
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["asr_round_trip"])
            self.assertEqual(result["line_count"], 2)
            output = project / result["asset"]
            text = output.read_text(encoding="utf-8")
            self.assertIn("第一句", text)
            self.assertIn("第二句", text)
            self.assertIn("00:00:01,500 --> 00:00:03,500", text)

    def test_ffmpeg_assembly_maps_video_audio_and_subtitles(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            video = project / "generated" / "shot.mp4"
            audio = project / "audio" / "voice.wav"
            subtitles = project / "pipeline" / "subtitles" / "pipeline.srt"
            for path, data in ((video, b"video"), (audio, b"audio"), (subtitles, b"1\n00:00:00,000 --> 00:00:01,000\nhello\n")):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

            def fake_run(command, **kwargs):
                Path(command[-1]).write_bytes(b"final")
                class Result:
                    returncode = 0
                    stderr = ""
                return Result()

            with patch("scripts.pipeline_media_stages.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
                "scripts.pipeline_media_stages.subprocess.run", side_effect=fake_run
            ) as run:
                result = assemble_final(project, video, audio=audio, subtitles=subtitles)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["output"], "final.mp4")
            command = run.call_args.args[0]
            self.assertIn("mov_text", command)
            self.assertIn(str(audio), command)
            self.assertIn(str(subtitles), command)


if __name__ == "__main__":
    unittest.main()
