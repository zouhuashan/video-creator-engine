import unittest
from pathlib import Path

from scripts.qc_episode_masters import parse_srt, validate_subtitles


class EpisodeMasterQCTests(unittest.TestCase):
    def test_all_episode_subtitles_are_monotonic_and_portrait_safe(self):
        root = Path("projects/jinghua-yuan-series/renders/episodes")
        paths = sorted(root.glob("s01e*-local-pilot-v1.srt"))
        self.assertEqual(len(paths), 5)
        for path in paths:
            result = validate_subtitles(path)
            self.assertEqual(result["status"], "PASS", path.name)
            self.assertLessEqual(result["max_line_chars"], 16)
            entries = parse_srt(path)
            self.assertTrue(entries)
            self.assertTrue(all(len(item["lines"]) <= 2 for item in entries))


if __name__ == "__main__":
    unittest.main()
