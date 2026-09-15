import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from adapters.video import (
    VIDEO_USE_CAPABILITIES,
    VideoUseError,
    build_self_eval_plan,
    load_video_use_config,
    render_command,
    validate_edl,
    video_use_environment,
)


class VideoUseAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.edit_dir = self.root / "edit"
        self.edit_dir.mkdir()
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"source")
        self.overlay = self.edit_dir / "overlay.mp4"
        self.overlay.write_bytes(b"overlay")
        self.edl = {
            "version": 1,
            "sources": {"A": str(self.source)},
            "ranges": [
                {"source": "A", "start": 0.5, "end": 2.0, "reason": "remove opening pause"},
                {"source": "A", "start": 2.4, "end": 4.0, "reason": "remove filler"},
            ],
            "overlays": [
                {"file": str(self.overlay), "start_in_output": 1.0, "duration": 1.0}
            ],
            "total_duration_s": 3.1,
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_config_declares_all_required_editing_capabilities(self):
        config = load_video_use_config()

        self.assertEqual(tuple(config["capabilities"]), VIDEO_USE_CAPABILITIES)
        self.assertTrue(config["production_rules"]["subtitles_last"])
        self.assertEqual(config["production_rules"]["audio_fade_ms"], 30)

    def test_validates_edl_sources_ranges_overlay_and_duration(self):
        result = validate_edl(self.edl, self.edit_dir)

        self.assertEqual(result["range_count"], 2)
        self.assertEqual(result["duration_seconds"], 3.1)

    def test_rejects_overlay_outside_output_timeline(self):
        self.edl["overlays"][0]["start_in_output"] = 3.0

        with self.assertRaisesRegex(VideoUseError, "exceeds"):
            validate_edl(self.edl, self.edit_dir)

    def test_render_command_uses_pinned_helper_and_keeps_output_in_edit(self):
        edl_path = self.edit_dir / "edl.json"
        edl_path.write_text(json.dumps(self.edl), encoding="utf-8")
        video_use_dir = self.root / "video-use"
        command = render_command(
            edl_path,
            self.edit_dir / "preview.mp4",
            preview=True,
            video_use_dir=video_use_dir,
        )

        self.assertEqual(command[0], str(video_use_dir / ".venv" / "bin" / "python"))
        self.assertIn(str(video_use_dir / "helpers" / "render.py"), command)
        self.assertIn("--preview", command)
        self.assertIn("--build-subtitles", command)

    def test_builds_self_eval_windows_around_every_cut(self):
        plan = build_self_eval_plan(self.edl)

        self.assertEqual(plan["max_passes"], 3)
        self.assertEqual([window["reason"] for window in plan["windows"]], ["opening", "cut_boundary", "closing"])
        self.assertAlmostEqual(plan["windows"][1]["start"], 0.0)
        self.assertAlmostEqual(plan["windows"][1]["end"], 3.0)

    def test_video_use_environment_prefers_project_local_tools(self):
        environment = video_use_environment()

        self.assertTrue(environment["PATH"].split(":")[0].endswith(".dependencies/bin"))


if __name__ == "__main__":
    unittest.main()
