import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class ChildLookdevV3ConfigTests(unittest.TestCase):
    def test_v3_targets_toy_like_failures(self):
        payload=json.loads((ROOT/"config/child-lookdev-v3.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["lookdev_id"],"P28-02-CHILD-LOOKDEV-V3")
        self.assertEqual(payload["based_on"],"P28-02-CHILD-LOOKDEV-V2")
        self.assertIn("flat_ribbon_hair_locks",payload["upgrades"])
        self.assertIn("drooping_wide_sleeves",payload["upgrades"])
        self.assertIn("reads_as_stylized_child_not_mascot",payload["quality_gate"]["requires"])
        self.assertEqual(payload["quality_gate"]["status"],"PENDING")

if __name__=="__main__":
    unittest.main()
