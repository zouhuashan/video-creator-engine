import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class FinalChildLookdevTests(unittest.TestCase):
    def test_final_child_lookdev_contract(self):
        payload=json.loads((ROOT/"config/final-child-lookdev-001.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["lookdev_id"],"FINAL-CHILD-LOOKDEV-001")
        self.assertEqual(payload["intent"],"final_visual_target_gate")
        self.assertEqual(payload["source_basemesh"],"P28-02-CHILD-LOOKDEV-V6")
        self.assertIn("reads_as_finished_guofeng_animation_child",payload["quality_gate"]["requires"])
        self.assertEqual(payload["quality_gate"]["status"],"PENDING")

if __name__=="__main__":
    unittest.main()
