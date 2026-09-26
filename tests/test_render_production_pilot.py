from __future__ import annotations

import unittest

from PIL import Image, ImageChops, ImageDraw

from scripts.render_production_pilot import HEIGHT, WIDTH, _font, _subtitle, _vanishing_shadow


class ProductionPilotVisualTests(unittest.TestCase):
    def test_shadow_is_visible_then_fully_gone(self) -> None:
        reflection = Image.new("RGBA", (320, 280), (0, 0, 0, 0))
        draw = ImageDraw.Draw(reflection)
        draw.polygon(((145, 0), (175, 0), (245, 190), (75, 190)), fill=(0, 3, 12, 235))
        draw.ellipse((115, 178, 205, 268), fill=(0, 3, 12, 235))

        visible = _vanishing_shadow(3.10, reflection)
        gone = _vanishing_shadow(4.50, reflection)

        self.assertIsNotNone(visible.getchannel("A").getbbox())
        histogram = visible.getchannel("A").histogram()
        self.assertGreater(sum(histogram[41:]), 2_000)
        self.assertIsNone(gone.getchannel("A").getbbox())

    def test_subtitle_backdrop_is_composited_without_transparent_hole(self) -> None:
        frame = Image.new("RGBA", (WIDTH, HEIGHT), (70, 95, 120, 255))
        original = frame.copy()

        _subtitle(frame, 3.20, _font(42))

        self.assertEqual(frame.getchannel("A").getextrema(), (255, 255))
        self.assertIsNotNone(ImageChops.difference(frame.convert("RGB"), original.convert("RGB")).getbbox())


if __name__ == "__main__":
    unittest.main()
