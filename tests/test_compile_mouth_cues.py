import json
import unittest
from pathlib import Path

from scripts.compile_mouth_cues import compile_cues


class MouthCueTests(unittest.TestCase):
    def test_compiles_speaker_lines_into_shot_cues(self):
        project = Path("projects/jinghua-yuan-series").resolve()
        result = compile_cues(project)
        self.assertIn("SHOT-S01E002-SC002-001", result["shots"])
        line = result["shots"]["SHOT-S01E002-SC002-001"][0]
        self.assertEqual(line["speaker_character_id"], "CHR-JHY-BAIHUA")
        self.assertGreaterEqual(len(line["mouth_cues"]), 3)
        self.assertEqual(line["mouth_cues"][0]["mouth"], "rest")
        self.assertEqual(len(result["timeline"]), 28)
        narration = next(item for item in result["timeline"] if item["kind"] == "NARRATION")
        self.assertIsNone(narration["speaker_character_id"])
        self.assertEqual(narration["mouth_cues"], [])
        self.assertEqual(result["timeline"][0]["subtitle"]["status"], "PLANNED")
        self.assertIsNone(result["timeline"][0]["audio"]["asset_id"])


if __name__ == "__main__":
    unittest.main()
