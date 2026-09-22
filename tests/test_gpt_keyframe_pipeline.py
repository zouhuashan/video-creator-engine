import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.gpt_keyframe_pipeline as p35


class GPTKeyframePipelineTests(unittest.TestCase):
    def fixture(self, root: Path):
        project = root / "project-test"
        video = project / "graybox" / "renders" / "GB-SHOT-001.mp4"
        character = project / "lookdev" / "character.png"
        scene = project / "graybox" / "references" / "scenes" / "gate.png"
        video.parent.mkdir(parents=True)
        character.parent.mkdir(parents=True)
        scene.parent.mkdir(parents=True)
        video.write_bytes(b"v" * 2048)
        character.write_bytes(b"c" * 2048)
        scene.write_bytes(b"s" * 2048)
        render = {
            "output_ready": True,
            "render_stale": False,
            "output_path": "graybox/renders/GB-SHOT-001.mp4",
        }
        spec = {
            "id": "GB-SHOT-001",
            "duration_seconds": 8,
            "fps": 24,
            "width": 720,
            "height": 1280,
            "review": {"status": "APPROVED"},
        }
        binding = {
            "character_reference": {"path": "lookdev/character.png"},
            "scene_reference": {"path": "graybox/references/scenes/gate.png"},
        }
        return project, video, character, scene, render, spec, binding

    def fake_image_run(self, command, label):
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_bytes(b"x" * 512)

    def test_prepare_extracts_nine_even_control_frames_and_anchor_resets(self):
        with tempfile.TemporaryDirectory() as directory:
            project, _, character, scene, render, spec, binding = self.fixture(Path(directory))
            with patch.object(p35, "graybox_render_status", return_value=render),                  patch.object(p35, "load_graybox_spec", return_value=spec),                  patch.object(p35, "resolve_graybox_reference_paths", return_value=(character, scene, binding)),                  patch.object(p35, "_require_ffmpeg", return_value="/usr/bin/ffmpeg"),                  patch.object(p35, "_run", side_effect=self.fake_image_run):
                result = p35.prepare(project, keyframe_count=9)

            self.assertEqual(result["status"], "CONTROL_READY")
            self.assertEqual(result["keyframe_count"], 9)
            self.assertEqual([item["timestamp_seconds"] for item in result["frames"]], [0,1,2,3,4,5,6,7,8])
            self.assertEqual(result["frames"][0]["reference_mode"], "CANONICAL_RESET")
            self.assertEqual(result["frames"][1]["reference_mode"], "PREVIOUS_CONTINUITY")
            self.assertEqual(result["frames"][2]["reference_mode"], "CANONICAL_RESET")
            self.assertIn("CURRENT BLENDER CONTROL FRAME", result["frames"][0]["prompt"])
            self.assertIn("central 84%", result["frames"][0]["prompt"])

    def test_upload_normalizes_chatgpt_frame_to_project_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            project, _, character, scene, render, spec, binding = self.fixture(Path(directory))
            with patch.object(p35, "graybox_render_status", return_value=render),                  patch.object(p35, "load_graybox_spec", return_value=spec),                  patch.object(p35, "resolve_graybox_reference_paths", return_value=(character, scene, binding)),                  patch.object(p35, "_require_ffmpeg", return_value="/usr/bin/ffmpeg"),                  patch.object(p35, "_run", side_effect=self.fake_image_run):
                p35.prepare(project, keyframe_count=9)
                content = b"\x89PNG\r\n\x1a\n" + b"p" * 512
                result = p35.upload_generated_frame(project, index=0, filename="chatgpt.png", content=content)

            self.assertEqual(result["generated_count"], 1)
            self.assertEqual(result["frames"][0]["status"], "READY")
            self.assertTrue((project / result["frames"][0]["generated_path"]).is_file())

    def test_interpolate_requires_all_frames_and_uses_24fps_motion_interpolation(self):
        with tempfile.TemporaryDirectory() as directory:
            project, _, character, scene, render, spec, binding = self.fixture(Path(directory))
            with patch.object(p35, "graybox_render_status", return_value=render),                  patch.object(p35, "load_graybox_spec", return_value=spec),                  patch.object(p35, "resolve_graybox_reference_paths", return_value=(character, scene, binding)),                  patch.object(p35, "_require_ffmpeg", return_value="/usr/bin/ffmpeg"),                  patch.object(p35, "_run", side_effect=self.fake_image_run):
                payload = p35.prepare(project, keyframe_count=9)

            with patch.object(p35, "load_graybox_spec", return_value=spec):
                with self.assertRaisesRegex(p35.GPTKeyframeError, "全部 AI"):
                    p35.interpolate(project)

            root = project / p35.ROOT_RELATIVE / "GB-SHOT-001"
            for frame in payload["frames"]:
                normalized = root / "normalized" / f"KF-{frame['index']:03d}.png"
                normalized.parent.mkdir(parents=True, exist_ok=True)
                normalized.write_bytes(b"x" * 512)
                frame["generated_path"] = normalized.relative_to(project).as_posix()
                frame["status"] = "READY"
            payload["generated_count"] = 9
            payload["status"] = "READY"
            p35._atomic_json(root / p35.MANIFEST_NAME, payload)

            captured = {}
            def fake_video_run(command, label):
                captured["command"] = command
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_bytes(b"v" * 4096)

            with patch.object(p35, "load_graybox_spec", return_value=spec),                  patch.object(p35, "_require_ffmpeg", return_value="/usr/bin/ffmpeg"),                  patch.object(p35, "_run", side_effect=fake_video_run):
                result = p35.interpolate(project)

            self.assertEqual(result["status"], "VIDEO_READY")
            self.assertEqual(result["interpolation"]["target_fps"], 24)
            command = " ".join(captured["command"])
            self.assertIn("minterpolate=fps=24", command)
            self.assertIn("trim=duration=8.000000", command)


if __name__ == "__main__":
    unittest.main()
