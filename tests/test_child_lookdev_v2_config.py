import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ChildLookdevV2ConfigTests(unittest.TestCase):
    def test_v2_contract_is_visual_iteration(self):
        payload = json.loads((ROOT / "config/child-lookdev-v2.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["lookdev_id"], "P28-02-CHILD-LOOKDEV-V2")
        self.assertEqual(payload["based_on"], "P28-02-CHILD-LOOKDEV-V1")
        self.assertIn("principled_node_materials", payload["upgrades"])
        self.assertIn("child_not_mascot_or_toy", payload["quality_gate"]["requires"])
        self.assertEqual(payload["quality_gate"]["status"], "PENDING")

if __name__ == "__main__":
    unittest.main()
