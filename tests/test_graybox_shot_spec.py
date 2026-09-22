import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.graybox_shot_spec as graybox


BASE_SPEC = {
    "id": "GB-SHOT-001",
    "project_id": "demo",
    "title": "照骨灯",
    "character": {"id": "CHR-001", "name": "主角", "role": "protagonist"},
    "duration_seconds": 8.0,
    "fps": 24,
    "width": 720,
    "height": 1280,
    "actor": {
        "start": [0.0, -4.5, 0.0],
        "stop": [0.0, -0.3, 0.0],
        "stop_time": 4.8,
        "look_up_time": 5.4,
        "hold_time": 7.2,
    },
    "camera_path": {
        "start": [5.8, -11.5, 3.8],
        "end": [4.1, -7.5, 3.2],
        "target": [0.0, -0.6, 1.45],
    },
    "review": {"required": True, "status": "PENDING", "note": ""},
}


class GrayboxShotSpecAdjustmentTests(unittest.TestCase):
    def _apply(self, instruction):
        captured = {}

        def fake_validate(_project, payload):
            return payload

        def fake_write(_project, payload, overwrite=False):
            captured["spec"] = copy.deepcopy(payload)
            captured["overwrite"] = overwrite
            return Path("/tmp/GB-SHOT-001.json")

        with patch.object(graybox, "load_spec", return_value=copy.deepcopy(BASE_SPEC)),              patch.object(graybox, "validate_spec", side_effect=fake_validate),              patch.object(graybox, "write_spec", side_effect=fake_write):
            result = graybox.apply_natural_language_adjustment(Path("/tmp/project"), instruction)
        return result, captured

    def test_camera_slow_and_final_hold_can_be_combined(self):
        result, captured = self._apply("镜头慢一点，最后多停 1 秒")
        self.assertEqual(result["status"], "UPDATED")
        self.assertTrue(any("duration_seconds" in item for item in result["changes"]))
        self.assertTrue(any("final_hold" in item for item in result["changes"]))
        self.assertGreater(captured["spec"]["duration_seconds"], 8.0)
        self.assertEqual(captured["spec"]["actor"]["hold_time"], captured["spec"]["duration_seconds"])
        self.assertTrue(captured["overwrite"])

    def test_reduce_camera_push_preserves_start_and_shortens_path(self):
        result, captured = self._apply("推进幅度变小")
        start = BASE_SPEC["camera_path"]["start"]
        old_end = BASE_SPEC["camera_path"]["end"]
        new_end = captured["spec"]["camera_path"]["end"]
        old_distance = sum((old_end[i] - start[i]) ** 2 for i in range(3))
        new_distance = sum((new_end[i] - start[i]) ** 2 for i in range(3))
        self.assertLess(new_distance, old_distance)
        self.assertIn("camera_dolly_distance ×0.55", result["changes"])

    def test_walk_smoother_delays_stop(self):
        _, captured = self._apply("人物走路再平缓")
        self.assertGreater(captured["spec"]["actor"]["stop_time"], BASE_SPEC["actor"]["stop_time"])
        self.assertLess(captured["spec"]["actor"]["stop_time"], captured["spec"]["actor"]["look_up_time"])

    def test_move_character_closer_to_gate(self):
        _, captured = self._apply("人物离建筑近一点")
        self.assertGreater(captured["spec"]["actor"]["stop"][1], BASE_SPEC["actor"]["stop"][1])

    def test_unknown_instruction_fails_instead_of_inventing_motion(self):
        with patch.object(graybox, "load_spec", return_value=copy.deepcopy(BASE_SPEC)):
            with self.assertRaisesRegex(graybox.GrayboxShotSpecError, "暂不支持"):
                graybox.apply_natural_language_adjustment(Path("/tmp/project"), "让它更有感觉")


if __name__ == "__main__":
    unittest.main()
