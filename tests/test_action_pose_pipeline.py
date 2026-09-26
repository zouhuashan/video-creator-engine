from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.prepare_action_pose_sheet import split_sheet
from scripts.render_action_pilot import DURATION, FPS, _shadow_from_pose


class ActionPosePipelineTests(unittest.TestCase):
    def test_split_removes_disconnected_cross_cell_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sheet = Image.new("RGBA", (200, 320), (0, 0, 0, 0))
            draw = ImageDraw.Draw(sheet)
            for column, row in ((0, 0), (1, 0), (0, 1), (1, 1)):
                x = column * 100
                y = row * 160
                draw.rounded_rectangle((x + 25, y + 15, x + 75, y + 150), radius=12, fill=(80, 40, 30, 255))
            draw.rectangle((8, 160, 20, 168), fill=(80, 40, 30, 255))
            source = root / "sheet.png"
            sheet.save(source)

            result = split_sheet(source, root / "poses", prefix="test")
            bottom_left = Image.open(root / "poses" / "test-pose-03.png").convert("RGBA")

            self.assertEqual(len(result["poses"]), 4)
            self.assertEqual(bottom_left.getchannel("A").getbbox(), (25, 15, 76, 151))

    def test_shadow_disappears_and_duration_is_frame_aligned(self) -> None:
        pose = Image.new("RGBA", (240, 360), (0, 0, 0, 0))
        ImageDraw.Draw(pose).rounded_rectangle((70, 10, 170, 350), radius=35, fill=(30, 30, 30, 255))

        self.assertIsNotNone(_shadow_from_pose(pose, 3.45).getchannel("A").getbbox())
        self.assertIsNotNone(_shadow_from_pose(pose, 4.50).getchannel("A").getbbox())
        self.assertIsNone(_shadow_from_pose(pose, 4.56).getchannel("A").getbbox())
        self.assertEqual(DURATION * FPS, round(DURATION * FPS))


if __name__ == "__main__":
    unittest.main()
