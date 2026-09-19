import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class ChildLookdevV4ConfigTests(unittest.TestCase):
    def test_v4_switches_modeling_strategy(self):
        payload=json.loads((ROOT/"config/child-lookdev-v4.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["lookdev_id"],"P28-02-CHILD-LOOKDEV-V4")
        self.assertEqual(payload["modeling_strategy"],"organic_curve_and_loft_mesh")
        self.assertIn("bezier_hair_strands",payload["upgrades"])
        self.assertIn("bell_sleeve_loft_mesh",payload["upgrades"])
        self.assertIn("body_no_longer_reads_as_primitive_stack",payload["quality_gate"]["requires"])
        self.assertEqual(payload["quality_gate"]["status"],"PENDING")

if __name__=="__main__":
    unittest.main()
