import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import scripts.cost_first_local_renderer as renderer


class CostFirstLocalRendererTests(unittest.TestCase):
    def test_two_cut_uses_plan_duration_and_stays_non_billable(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            a = project / "a.png"
            b = project / "b.png"
            a.write_bytes(b"a")
            b.write_bytes(b"b")
            plan = {
                "policy": {"default_local_fps": 24, "local_preview_width": 720, "local_preview_height": 1280},
                "routes": [{
                    "shot_id": "SHOT-002",
                    "route": "LOCAL_TWO_CUT",
                    "required_new_stills": 2,
                    "duration_seconds": 3.25,
                    "timing_source": "ACTUAL_TTS",
                }],
            }

            def fake_generate(self, request):
                request.output_path.parent.mkdir(parents=True, exist_ok=True)
                request.output_path.write_bytes(b"video")
                return SimpleNamespace(
                    output_path=request.output_path,
                    provider="local_two_cut",
                    duration_seconds=request.shot_duration_seconds,
                )

            with patch.object(renderer, "load_plan", return_value=plan), \
                 patch.object(renderer.LocalTwoCutVideo, "generate", fake_generate):
                result = renderer.render_local_shot(project, "SHOT-002", [a, b])

            self.assertEqual(result["duration_seconds"], 3.25)
            self.assertEqual(result["timing_source"], "ACTUAL_TTS")
            self.assertFalse(result["billable"])
            self.assertFalse(result["remote_generation"])
            self.assertEqual(result["image_count"], 2)
            self.assertTrue((project / result["output"]).is_file())

    def test_h3_candidate_cannot_use_local_renderer(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            image = project / "a.png"
            image.write_bytes(b"a")
            plan = {
                "policy": {},
                "routes": [{
                    "shot_id": "SHOT-H3",
                    "route": "H3_CANDIDATE",
                    "required_new_stills": 0,
                    "duration_seconds": 4.0,
                }],
            }
            with patch.object(renderer, "load_plan", return_value=plan):
                with self.assertRaisesRegex(renderer.CostFirstLocalRenderError, "H3 candidates"):
                    renderer.render_local_shot(project, "SHOT-H3", [image])


if __name__ == "__main__":
    unittest.main()
