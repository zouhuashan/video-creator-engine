import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class ChildLookdevV5ConfigTests(unittest.TestCase):
    def test_v5_switches_to_mpfb_basemesh(self):
        payload=json.loads((ROOT/"config/child-lookdev-v5.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["modeling_strategy"],"mpfb_real_basemesh")
        self.assertEqual(payload["mpfb"]["package_id"],"mpfb")
        self.assertEqual(payload["mpfb"]["phenotype"]["age"],"child")
        self.assertIn("continuous_human_basemesh",payload["quality_gate"]["requires"])
        self.assertEqual(payload["quality_gate"]["status"],"PENDING")

if __name__=="__main__":
    unittest.main()
