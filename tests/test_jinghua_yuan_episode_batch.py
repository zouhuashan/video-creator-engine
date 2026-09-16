import tempfile
import unittest
from pathlib import Path

from scripts.jinghua_yuan_episode_batch import EPISODES, build_scene_variant, write_subtitles


class JinghuaYuanEpisodeBatchTests(unittest.TestCase):
    def test_first_five_have_continuous_three_scene_specs(self):
        self.assertEqual(len(EPISODES), 5)
        self.assertEqual([episode["episode_id"] for episode in EPISODES], [f"episode-{index:02d}" for index in range(1, 6)])
        for episode in EPISODES:
            self.assertEqual(len(episode["scenes"]), 3)
            self.assertTrue(all(scene[1] for scene in episode["scenes"]))

    def test_subtitles_follow_crossfade_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "subtitles.srt"
            write_subtitles(path, ["第一镜", "第二镜", "第三镜"])
            content = path.read_text(encoding="utf-8")
        self.assertIn("00:00:00,000 --> 00:00:02,700", content)
        self.assertIn("00:00:05,400 --> 00:00:08,500", content)

    def test_scene_variant_keeps_vertical_format_and_writes_caption(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            output = Path(directory) / "scene.png"
            from PIL import Image

            Image.new("RGB", (100, 180), (40, 50, 60)).save(source)
            build_scene_variant(source, output, 1, 1, "测试镜头", (20, 40, 80))
            with Image.open(output) as image:
                self.assertEqual(image.size, (1080, 1920))
            self.assertGreater(output.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
