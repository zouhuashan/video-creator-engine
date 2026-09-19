import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ChildLookdevConfigTests(unittest.TestCase):
    def test_child_lookdev_contract(self):
        payload = json.loads((ROOT / "config/child-lookdev-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["lookdev_id"], "P28-02-CHILD-LOOKDEV-V1")
        self.assertEqual(payload["style_id"], "STYLE-REF-GUOFENG-DIALOGUE-001")
        self.assertTrue(payload["proportions"]["adult_face_reuse_forbidden"])
        self.assertGreaterEqual(payload["proportions"]["head_to_body_ratio_target"], 3.0)
        self.assertIn("double_bun", payload["hair"]["silhouette"])
        self.assertIn("human_visual_review", payload["quality_gate"]["requires"])
        self.assertEqual(payload["quality_gate"]["status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
